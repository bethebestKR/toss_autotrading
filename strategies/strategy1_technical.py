"""
전략 1 — Claude AI 직접 판단 (캔들 기반)

- 매 1초: 현재가 조회 → 보유 포지션 스톱로스 체크
- 매 decision_interval초: 최대 10종목 1분봉 수집 → Claude Sonnet에 일괄 판단 요청 (비동기)
- Claude가 BUY/SELL/HOLD 직접 결정
- 거래 종료 시: Claude가 결과 분석 → data/claude_strategy.md에 규칙 누적
- 손절(-2%) / 급락(5%) / 슬리피지: Claude 우회 — 즉시 실행 (안전망)
"""
import os
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone, timedelta

from core.toss_client import TossClient
from core.order_engine import OrderEngine
from core import db
from core import discord_notifier

KST = timezone(timedelta(hours=9))

_calendar_cache: dict[str, tuple] = {}
_CALENDAR_TTL = 60

# ── 동적 손절/익절 클램핑 범위 ────────────────────────────────────────────────
_SL_MIN, _SL_MAX = 0.5, 5.0   # 손절 허용 범위 (%)
_TP_MIN, _TP_MAX = 1.0, 10.0  # 익절 허용 범위 (%)

def _clamp(val, lo: float, hi: float, default: float) -> float:
    try:
        return max(lo, min(hi, float(val)))
    except (TypeError, ValueError):
        return default


DEFAULT_CONFIG = {
    "quantity":           "1",
    "max_position_pct":   0.20,
    "stop_loss_pct":      2.0,
    "take_profit_pct":    3.0,
    "crash_pct":          5.0,
    "slippage_pct":       1.0,
    "slippage_ticks":     5,
    "use_claude":         True,
    "claude_model":       "claude-sonnet-4-6",
    "claude_min_confidence": 0.65,
    "decision_interval":  30,   # 몇 초(틱)마다 Claude 배치 결정
    "max_symbols":        10,   # Claude에 한 번에 넘길 최대 종목 수
    "closing_buffer_min": 10,  # 장 마감 N분 전 신규 매수 차단 + 보유 포지션 강제 청산
}


# ── 시장 시간 체크 ────────────────────────────────────────────────────────────

def _get_calendar(client: TossClient, market: str) -> dict:
    now_ts = time.time()
    cached = _calendar_cache.get(market)
    if cached and now_ts < cached[1]:
        return cached[0]
    result = client.get_market_calendar_us() if market == "us" else client.get_market_calendar_kr()
    _calendar_cache[market] = (result, now_ts + _CALENDAR_TTL)
    return result


def _in_session(session: dict | None, now: datetime) -> bool:
    if not session:
        return False
    start = datetime.fromisoformat(session["startTime"])
    end   = datetime.fromisoformat(session["endTime"])
    return start <= now <= end


def is_market_open(client: TossClient, symbol: str) -> bool:
    now = datetime.now(KST)
    try:
        if _is_us(symbol):
            cal   = _get_calendar(client, "us")
            today = cal["today"]
            return any(_in_session(today.get(s), now) for s in ("preMarket", "regularMarket", "afterMarket"))
        else:
            cal        = _get_calendar(client, "kr")
            integrated = cal["today"].get("integrated")
            if not integrated:
                return False
            return any(_in_session(integrated.get(s), now) for s in ("preMarket", "regularMarket", "afterMarket"))
    except Exception:
        return False


def _is_us(symbol: str) -> bool:
    return symbol.replace(".", "").replace("-", "").isalpha()


def _is_opening_period(symbol: str) -> bool:
    """장 시작 직후 15분 내이면 True — 갭 오픈 충격 구간 매수 차단."""
    now = datetime.now(KST).time()
    if not _is_us(symbol):
        from datetime import time as _t
        return _t(9, 0) <= now < _t(9, 15)
    return False  # 미국은 서머타임 영향으로 단순 시간 비교 불가 — 추후 개선


def _is_closing_soon(client: TossClient, symbol: str, buffer_min: int) -> bool:
    """정규장 마감 buffer_min분 전이면 True — 익일 갭다운 방지 강제 청산 기준."""
    now = datetime.now(KST)
    try:
        if _is_us(symbol):
            cal     = _get_calendar(client, "us")
            regular = cal["today"].get("regularMarket")
        else:
            cal     = _get_calendar(client, "kr")
            regular = cal["today"].get("integrated", {}).get("regularMarket")

        if not regular or not regular.get("endTime"):
            return False

        end       = datetime.fromisoformat(regular["endTime"])
        remaining = (end - now).total_seconds()
        return 0 <= remaining <= buffer_min * 60
    except Exception:
        return False


def _fetch_market_trend(client: TossClient, symbols: list[str]) -> dict:
    """KODEX200(KR) / SPY(US) 최근 5분봉으로 시장 방향 판단."""
    has_kr = any(not _is_us(s) for s in symbols)
    has_us = any(_is_us(s) for s in symbols)

    def _direction(candle_data: dict) -> str:
        candles = candle_data.get("candles", [])
        if len(candles) < 2:
            return "불명"
        first = float(candles[0].get("closePrice", 0) or 0)
        last  = float(candles[-1].get("closePrice", 0) or 0)
        if first == 0:
            return "불명"
        chg = (last - first) / first * 100
        if chg > 0.1:
            return f"상승 ({chg:+.2f}%)"
        if chg < -0.1:
            return f"하락 ({chg:+.2f}%)"
        return "횡보"

    trend: dict = {}
    if has_kr:
        try:
            trend["KOSPI"] = _direction(client.get_candles("069500", "1m", 5))
        except Exception:
            trend["KOSPI"] = "불명"
    if has_us:
        try:
            trend["SP500"] = _direction(client.get_candles("SPY", "1m", 5))
        except Exception:
            trend["SP500"] = "불명"
    return trend


# ── Strategy1 ─────────────────────────────────────────────────────────────────

class Strategy1:
    """
    Claude AI가 1분봉 캔들 데이터를 직접 보고 매수/매도를 결정하는 전략.
    손절·급락·슬리피지는 Python이 직접 처리 (Claude 우회).
    """

    def __init__(self, client: TossClient, symbols: list[str], config: dict = None, engine=None):
        self.client  = client
        self.engine  = engine if engine is not None else OrderEngine(client, strategy="strategy1")
        self.symbols = symbols
        self.cfg     = {**DEFAULT_CONFIG, **(config or {})}

        # symbol → {"order_id", "buy_price", "quantity", "ticks_since_buy", "candle_snapshot"}
        self._positions: dict[str, dict] = {}
        self._prev_prices: dict[str, float] = {}
        self._session_realized_pnl: float = 0.0
        self._emergency_stop: bool = False

        # Claude 비동기 배치 결정
        self._executor = ThreadPoolExecutor(max_workers=6, thread_name_prefix="claude")
        self._decision_future: Future | None = None
        self._decision_tick: int = 0
        self._last_market_context: dict = {}
        self._trade_buffer: list[dict] = []         # 배치 학습용 거래 버퍼
        self._batch_size: int = self.cfg.get("batch_learn_size", 20)
        self._status_notify_tick: int = 0
        self._status_notify_interval: int = self.cfg.get("discord_status_interval", 300)

        if self.cfg.get("use_claude", True) and not os.environ.get("ANTHROPIC_API_KEY"):
            print("[경고] use_claude=True이지만 ANTHROPIC_API_KEY가 없습니다. .env를 확인하세요.")
            self.cfg["use_claude"] = False

    def _sync_symbols(self):
        for s in self.symbols:
            if s not in self._prev_prices:
                self._prev_prices[s] = 0.0

    # ── 메인 루프 ────────────────────────────────────────────────────────────

    def run_once(self):
        """1초마다 호출."""
        if self._emergency_stop:
            self._liquidate_all()
            return

        self._sync_symbols()

        active = [s for s in self.symbols if is_market_open(self.client, s)]
        if not active:
            self._update_status({})
            return

        try:
            price_list = self.client.get_prices(active)
        except Exception as e:
            print(f"[strategy1] 현재가 조회 오류: {e}")
            self._update_status({})
            return

        price_map = {p["symbol"]: float(p["lastPrice"]) for p in price_list}

        # 완료된 Claude 배치 결정 처리 (non-blocking)
        self._check_decision_future(price_map)

        # 보유 포지션 스톱로스·이상감지 (매 틱)
        for symbol in list(self._positions.keys()):
            if self._emergency_stop:
                break
            if symbol in price_map:
                self._check_position(symbol, price_map[symbol])

        # 장 마감 N분 전 — 보유 포지션 강제 청산
        closing_min = self.cfg["closing_buffer_min"]
        for symbol in list(self._positions.keys()):
            if _is_closing_soon(self.client, symbol, closing_min):
                if symbol in price_map:
                    print(f"[strategy1] {symbol} 장 마감 {closing_min}분 전 — 강제 청산")
                    self._do_sell(symbol, price_map[symbol], f"장 마감 {closing_min}분 전 강제 청산")

        # decision_interval초마다 Claude 배치 결정 제출
        self._decision_tick += 1
        if (self._decision_tick >= self.cfg["decision_interval"]
                and self._decision_future is None
                and self.cfg.get("use_claude", True)):
            self._decision_tick = 0
            candidates = [s for s in active if s not in self._positions]
            held       = list(self._positions.keys())
            to_analyze = list(dict.fromkeys(candidates + held))[:self.cfg["max_symbols"]]
            if to_analyze:
                self._decision_future = self._executor.submit(
                    self._fetch_and_decide, to_analyze
                )

        self._update_status(price_map)

    # ── Claude 배치 결정 ──────────────────────────────────────────────────────

    def _fetch_and_decide(self, symbols: list[str]) -> tuple[list[dict], dict]:
        """executor에서 실행. 캔들 + 호가 + 시장방향 수집 → Claude 판단 → (decisions, snapshots) 반환."""
        from core.claude_trader import load_strategy_rules, ask_trade_decision, fmt_candles
        from concurrent.futures import ThreadPoolExecutor as _TPE

        candles_by_symbol: dict = {}
        orderbooks_by_symbol: dict = {}
        trades_by_symbol: dict = {}

        # Phase 1 — 캔들 (MARKET_DATA_CHART 그룹, 한도 5)
        # max_workers=4 로 동시 콜을 한도 미만으로 제한
        with _TPE(max_workers=4) as ex:
            candle_futs = {s: ex.submit(self.client.get_candles, s, "1m", 30) for s in symbols}
            for s, f in candle_futs.items():
                try:
                    candles_by_symbol[s] = f.result(timeout=15)
                except Exception as e:
                    print(f"[strategy1] {s} 캔들 조회 실패: {e}")

        # Phase 2 — 호가·체결 (MARKET_DATA 그룹, 한도 10)
        # max_workers=4 → 최대 4콜 동시, prices 폴링(1콜) 여유분 확보
        with _TPE(max_workers=4) as ex:
            ob_futs    = {s: ex.submit(self.client.get_orderbook, s) for s in symbols}
            trade_futs = {s: ex.submit(self.client.get_trades, s, 50) for s in symbols}
            for s, f in ob_futs.items():
                try:
                    orderbooks_by_symbol[s] = f.result(timeout=10)
                except Exception:
                    pass
            for s, f in trade_futs.items():
                try:
                    trades_by_symbol[s] = f.result(timeout=10)
                except Exception:
                    pass

        # Phase 3 — 시장 방향 (MARKET_DATA_CHART 그룹, 2콜 — 캔들과 분리해 여유 확보)
        try:
            market_context = _fetch_market_trend(self.client, symbols)
        except Exception:
            market_context = {}

        if not candles_by_symbol:
            return [], {}, {}

        snapshots = {s: fmt_candles(s, data) for s, data in candles_by_symbol.items()}
        strategy_rules = load_strategy_rules()
        decisions = ask_trade_decision(
            candles_by_symbol=candles_by_symbol,
            strategy_rules=strategy_rules,
            model=self.cfg.get("claude_model", "claude-sonnet-4-6"),
            orderbooks_by_symbol=orderbooks_by_symbol,
            market_context=market_context,
            trades_by_symbol=trades_by_symbol,
        )
        return decisions, snapshots, market_context

    def _check_decision_future(self, price_map: dict):
        """완료된 Claude 배치 결정을 처리한다. non-blocking."""
        if self._decision_future is None or not self._decision_future.done():
            return

        try:
            decisions, snapshots, market_context = self._decision_future.result()
            self._last_market_context = market_context
        except Exception as e:
            print(f"[Claude] 배치 결정 오류: {e}")
            self._decision_future = None
            return

        # 하락장 감지 시 confidence 기준 +0.15 자동 상향 (3번)
        ctx = self._last_market_context
        kr_falling = "하락" in ctx.get("KOSPI", "")
        us_falling = "하락" in ctx.get("SP500", "")
        base_conf = self.cfg["claude_min_confidence"]

        for d in decisions:
            symbol  = d.get("symbol", "")
            action  = d.get("action", "HOLD")
            reason  = d.get("reason", "")
            conf    = float(d.get("confidence", 0.0))

            # 해당 종목에 적용할 시장 방향 상향 여부
            market_falling = us_falling if _is_us(symbol) else kr_falling
            min_conf = base_conf + (0.15 if market_falling else 0.0)

            print(f"[Claude] {symbol} → {action} (확신도 {conf:.0%}, 기준 {min_conf:.0%}): {reason}")

            if action == "BUY" and conf >= min_conf:
                if symbol not in self._positions and symbol in price_map:
                    if _is_opening_period(symbol):
                        print(f"[strategy1] {symbol} 장 시작 쿨다운 — BUY 건너뜀")
                        continue
                    if _is_closing_soon(self.client, symbol, self.cfg["closing_buffer_min"]):
                        print(f"[strategy1] {symbol} 장 마감 임박 — BUY 차단")
                        continue
                    # 동적 손절/익절 클램핑 (2번)
                    sl = _clamp(d.get("stop_loss"),  _SL_MIN, _SL_MAX, self.cfg["stop_loss_pct"])
                    tp = _clamp(d.get("take_profit"), _TP_MIN, _TP_MAX, self.cfg["take_profit_pct"])
                    qty_str = self._calc_quantity(symbol, price_map[symbol])
                    self._do_buy(symbol, price_map[symbol], qty_str, snapshots.get(symbol, ""), sl, tp)

            elif action == "SELL" and symbol in self._positions:
                if symbol in price_map:
                    self._do_sell(symbol, price_map[symbol], f"Claude: {reason}")

        self._decision_future = None

    # ── 포지션 관리 ───────────────────────────────────────────────────────────

    def _check_position(self, symbol: str, price: float):
        """보유 포지션 이상감지 + 손절 체크 (매 틱)."""
        pos = self._positions[symbol]
        buy_price = pos["buy_price"]
        pos["ticks_since_buy"] = pos.get("ticks_since_buy", 0) + 1
        ticks = pos["ticks_since_buy"]

        prev = self._prev_prices.get(symbol, 0.0)
        self._prev_prices[symbol] = price

        if self._check_anomaly(symbol, price, prev, buy_price, ticks):
            self._emergency_stop = True
            return

        change_pct = (price - buy_price) / buy_price * 100
        sl_pct = pos.get("stop_loss_pct",   self.cfg["stop_loss_pct"])
        tp_pct = pos.get("take_profit_pct", self.cfg["take_profit_pct"])
        if change_pct <= -sl_pct:
            print(f"[strategy1] {symbol} 손절 — {change_pct:+.2f}% (기준 -{sl_pct:.1f}%, Python 즉시)")
            self._do_sell(symbol, price, f"손절 {change_pct:+.2f}%")
        elif change_pct >= tp_pct:
            print(f"[strategy1] {symbol} 익절 — {change_pct:+.2f}% (기준 +{tp_pct:.1f}%, Python 즉시)")
            self._do_sell(symbol, price, f"익절 {change_pct:+.2f}%")

    def _calc_quantity(self, symbol: str, price: float) -> str:
        try:
            if hasattr(self.engine, 'cash'):
                buying_power = self.engine.cash
            else:
                currency = "USD" if _is_us(symbol) else "KRW"
                buying_power = float(self.client.get_buying_power(currency=currency)["cashBuyingPower"])
            budget = buying_power * self.cfg["max_position_pct"] / max(1, len(self.symbols))
            qty = max(1, int(budget / price))
            return str(qty)
        except Exception:
            return self.cfg["quantity"]

    def _check_anomaly(self, symbol: str, price: float, prev_price: float,
                       buy_price: float, ticks_since_buy: int) -> bool:
        if prev_price > 0:
            tick_drop = (prev_price - price) / prev_price * 100
            if tick_drop >= self.cfg["crash_pct"]:
                print(f"[ALERT] {symbol} 급락 감지 — -{tick_drop:.1f}% (기준 -{self.cfg['crash_pct']}%)")
                return True
        if ticks_since_buy <= self.cfg["slippage_ticks"] and buy_price > 0:
            slip = (buy_price - price) / buy_price * 100
            if slip >= self.cfg["slippage_pct"]:
                print(f"[ALERT] {symbol} 슬리피지 — -{slip:.1f}% ({ticks_since_buy}틱)")
                return True
        return False

    def _liquidate_all(self):
        if not self._positions:
            return
        print("[ALERT] 비상 정지 — 전 포지션 청산 중...")
        discord_notifier.notify_emergency("비상 정지 — 전 포지션 강제 청산")
        try:
            syms = list(self._positions.keys())
            price_list = self.client.get_prices(syms) if not hasattr(self.engine, 'cash') else []
            price_map = {p["symbol"]: float(p["lastPrice"]) for p in price_list}
        except Exception:
            price_map = {}

        for symbol in list(self._positions.keys()):
            pos = self._positions[symbol]
            cur = price_map.get(symbol, pos["buy_price"])
            qty = str(pos.get("quantity", 1))
            self._session_realized_pnl += (cur - pos["buy_price"]) * int(qty)
            self.engine.sell(symbol=symbol, quantity=qty, current_price=cur)
            del self._positions[symbol]
            print(f"[ALERT] {symbol} 청산 완료")

    def _do_buy(self, symbol: str, price: float, qty_str: str, candle_snapshot: str = "",
                stop_loss_pct: float = None, take_profit_pct: float = None):
        result = self.engine.buy(symbol=symbol, quantity=qty_str, current_price=price)
        if result:
            order_id = result["orderId"]
            if not hasattr(self.engine, 'cash'):
                db.update_order_signal(
                    order_id=order_id,
                    signal_type="claude_batch",
                    entry_rsi=None,
                    entry_ema_gap=None,
                    volume_ratio=None,
                    bid_ratio=None,
                )
            sl = stop_loss_pct  if stop_loss_pct  is not None else self.cfg["stop_loss_pct"]
            tp = take_profit_pct if take_profit_pct is not None else self.cfg["take_profit_pct"]
            self._positions[symbol] = {
                "order_id":        order_id,
                "buy_price":       price,
                "quantity":        int(qty_str),
                "ticks_since_buy": 0,
                "candle_snapshot": candle_snapshot,
                "stop_loss_pct":   sl,
                "take_profit_pct": tp,
            }
            print(f"[strategy1] {symbol} 매수 완료 — {price:,.2f} × {qty_str}주 | 손절:{sl:.1f}% 익절:{tp:.1f}%")
            discord_notifier.notify_buy(symbol, price, int(qty_str), sl, tp)

    def _do_sell(self, symbol: str, price: float, reason: str):
        if symbol not in self._positions:
            return
        pos = self._positions[symbol]
        qty = pos.get("quantity", 1)
        pnl_pct = (price - pos["buy_price"]) / pos["buy_price"] * 100

        print(f"[strategy1] {symbol} 매도 — {reason} ({pnl_pct:+.2f}%)")
        discord_notifier.notify_sell(symbol, price, pnl_pct, reason)
        self._session_realized_pnl += (price - pos["buy_price"]) * qty
        self.engine.sell(symbol=symbol, quantity=str(qty), current_price=price)

        # 배치 학습 버퍼에 거래 기록
        self._trade_buffer.append({
            "symbol":          symbol,
            "buy_price":       pos["buy_price"],
            "sell_price":      price,
            "pnl_pct":         pnl_pct,
            "exit_reason":     reason,
            "candle_snapshot": pos.get("candle_snapshot", ""),
        })
        print(f"[학습] 버퍼 {len(self._trade_buffer)}/{self._batch_size}건")

        if len(self._trade_buffer) >= self._batch_size:
            batch = self._trade_buffer.copy()
            self._trade_buffer.clear()
            self._executor.submit(self._batch_analyze_and_save, batch)

        del self._positions[symbol]

    def _batch_analyze_and_save(self, trade_records: list[dict]):
        """N건 거래 결과를 Claude에게 일괄 분석시켜 규칙 저장. executor에서 실행."""
        from core.claude_trader import load_strategy_rules, append_strategy_rule, ask_batch_analyze_trades
        strategy_rules = load_strategy_rules()
        result = ask_batch_analyze_trades(
            trade_records=trade_records,
            strategy_rules=strategy_rules,
            model=self.cfg.get("claude_model", "claude-sonnet-4-6"),
        )
        if result:
            category, rule_text = result
            append_strategy_rule(category, rule_text)
            print(f"[학습] {len(trade_records)}건 배치 분석 완료 → [{category}] 규칙 저장")

    # ── 대시보드 ─────────────────────────────────────────────────────────────

    def _update_status(self, price_map: dict):
        from core import status_server
        from core.db import get_recent_orders as _db_recent_orders

        def get_recent_orders(limit=10):
            if hasattr(self.engine, 'trade_log'):
                return self.engine.get_recent_orders(limit=limit)
            return _db_recent_orders(limit=limit)

        positions: dict = {}
        watching: dict  = {}
        interval = self.cfg["decision_interval"]
        decision_progress = min(100, int(self._decision_tick * 100 / interval))
        pending_claude = self._decision_future is not None and not self._decision_future.done()

        for symbol in self.symbols:
            price = price_map.get(symbol)
            if symbol in self._positions:
                pos = self._positions[symbol]
                buy_price = pos["buy_price"]
                change_pct = round((price - buy_price) / buy_price * 100, 2) if price else 0.0
                sl_pct = pos.get("stop_loss_pct",   self.cfg["stop_loss_pct"])
                tp_pct = pos.get("take_profit_pct", self.cfg["take_profit_pct"])
                positions[symbol] = {
                    "buy_price":         buy_price,
                    "current_price":     price,
                    "change_pct":        change_pct,
                    "take_profit_price": round(buy_price * (1 + tp_pct / 100), 2),
                    "stop_loss_price":   round(buy_price * (1 - sl_pct / 100), 2),
                    "signal_text":       "보유 중",
                }
            else:
                if pending_claude:
                    signal_text = "Claude 분석 중..."
                else:
                    signal_text = f"다음 분석까지 {interval - self._decision_tick}초"
                watching[symbol] = {
                    "current_price": price,
                    "market_open":   price is not None,
                    "signal_text":   signal_text,
                    "decision_pct":  decision_progress,
                }

        unrealized_pnl = sum(
            (price_map.get(sym, pos["buy_price"]) - pos["buy_price"]) * pos.get("quantity", 1)
            for sym, pos in self._positions.items()
        )
        total_pnl     = self._session_realized_pnl + unrealized_pnl
        paper_balance = round(self.engine.cash) if hasattr(self.engine, 'cash') else None

        pnl_summary = {
            "realized":   round(self._session_realized_pnl),
            "unrealized": round(unrealized_pnl),
            "total":      round(total_pnl),
            "balance":    paper_balance,
        }
        status_server.update({
            "updated_at":    datetime.now(KST).strftime("%H:%M:%S"),
            "positions":     positions,
            "watching":      watching,
            "recent_orders": get_recent_orders(limit=10),
            "pnl_summary":   pnl_summary,
        })

        self._status_notify_tick += 1
        if self._status_notify_tick >= self._status_notify_interval:
            self._status_notify_tick = 0
            discord_notifier.notify_status(positions, pnl_summary)
