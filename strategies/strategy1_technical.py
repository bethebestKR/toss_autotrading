"""
전략 1 — 기술적 단타 (1초 틱 기반)

- 매 1초마다 get_prices()로 전 종목 현재가 수집 → 내부 시계열 누적
- EMA5(5초) / EMA20(20초) / RSI14 크로스 신호로 매수/매도
- 손절 -2% / 익절 +4%
"""
import time
from collections import deque
from datetime import datetime, timezone, timedelta

import pandas as pd
import pandas_ta as ta

from core.toss_client import TossClient
from core.order_engine import OrderEngine

KST = timezone(timedelta(hours=9))

# market_calendar 캐시: {"kr": (result, expires_at), "us": (result, expires_at)}
_calendar_cache: dict[str, tuple] = {}
_CALENDAR_TTL = 60  # 초

DEFAULT_CONFIG = {
    "quantity": "1",
    "stop_loss_pct": 2.0,
    "take_profit_pct": 4.0,
    "warmup_ticks": 60,        # 신호 판단 시작 전 최소 누적 틱 수
    "volume_surge_ratio": 1.5, # 최근 거래량이 평균 대비 몇 배 이상이어야 통과
    "bid_ratio_min": 0.55,     # 매수잔량 / 전체잔량 최소 비율
}


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


def _safe_float(v) -> float | None:
    """numpy/pandas 스칼라 → Python float 변환. NaN은 None."""
    try:
        f = float(v)
        return None if f != f else round(f, 2)
    except (TypeError, ValueError):
        return None


def _check_volume_surge(client: TossClient, symbol: str, threshold: float) -> tuple[bool, float]:
    """
    최근 체결 거래량이 과거 대비 threshold배 이상인지 확인.
    trades API 50건: 최근 10건 vs 나머지 40건 평균 비교.
    Returns: (통과여부, 실제비율)
    """
    try:
        trades = client.get_trades(symbol, count=50)
        if len(trades) < 15:
            return True, 0.0  # 데이터 부족 → 필터 통과
        volumes = [float(t["volume"]) for t in trades]
        recent  = sum(volumes[:10])
        base    = sum(volumes[10:]) / (len(volumes) - 10) * 10  # 동일 건수 기준 정규화
        ratio   = recent / base if base > 0 else 0.0
        return ratio >= threshold, round(ratio, 2)
    except Exception:
        return True, 0.0  # 오류 → 필터 통과


def _check_orderbook_bias(client: TossClient, symbol: str, min_bid_ratio: float) -> tuple[bool, float]:
    """
    매수잔량 / 전체잔량 비율이 min_bid_ratio 이상인지 확인.
    Returns: (통과여부, 실제비율)
    """
    try:
        ob = client.get_orderbook(symbol)
        result = ob.get("result", ob)
        bid_vol = sum(float(b["volume"]) for b in result.get("bids", []))
        ask_vol = sum(float(a["volume"]) for a in result.get("asks", []))
        total   = bid_vol + ask_vol
        ratio   = bid_vol / total if total > 0 else 0.5
        return ratio >= min_bid_ratio, round(ratio, 2)
    except Exception:
        return True, 0.0  # 오류 → 필터 통과


def _calc_signals(prices: list[float]) -> dict:
    """가격 시계열로 EMA5/EMA20/RSI14 및 크로스 신호 계산."""
    s = pd.Series(prices)
    ema5  = ta.ema(s, length=5)
    ema20 = ta.ema(s, length=20)
    rsi   = ta.rsi(s, length=14)

    golden_cross = (ema5.iloc[-1] > ema20.iloc[-1]) and (ema5.iloc[-2] <= ema20.iloc[-2])
    dead_cross   = (ema5.iloc[-1] < ema20.iloc[-1]) and (ema5.iloc[-2] >= ema20.iloc[-2])

    return {
        "ema5":         ema5.iloc[-1],
        "ema20":        ema20.iloc[-1],
        "rsi":          rsi.iloc[-1],
        "golden_cross": golden_cross,
        "dead_cross":   dead_cross,
        "last_price":   prices[-1],
    }


class Strategy1:
    """
    기술적 단타 전략 (1초 틱).
    - 매수: EMA5/EMA20 골든크로스 + RSI < 65
    - 매도: 데드크로스 OR RSI > 75 OR 손절/익절
    """

    def __init__(self, client: TossClient, symbols: list[str], config: dict = None, engine=None):
        self.client  = client
        self.engine  = engine if engine is not None else OrderEngine(client, strategy="strategy1")
        self.symbols = symbols
        self.cfg     = {**DEFAULT_CONFIG, **(config or {})}

        warmup = self.cfg["warmup_ticks"] + 30
        # symbol → deque of float prices
        self._ticks: dict[str, deque] = {s: deque(maxlen=warmup) for s in symbols}
        # symbol → {"order_id": str, "buy_price": float}
        self._positions: dict[str, dict] = {}
        # symbol → last computed signals dict
        self._last_signals: dict[str, dict] = {}
        # 이번 세션 실현 손익 누적
        self._session_realized_pnl: float = 0.0

    def _sync_symbols(self):
        """symbols 목록이 런타임에 변경됐을 때 틱 버퍼 동기화."""
        for s in self.symbols:
            if s not in self._ticks:
                warmup = self.cfg["warmup_ticks"] + 30
                self._ticks[s] = deque(maxlen=warmup)

    def run_once(self):
        """1초마다 호출. 전 종목 현재가를 한 번에 조회 후 각 종목 처리."""
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

        for symbol in active:
            if symbol not in price_map:
                continue
            try:
                self._process(symbol, price_map[symbol])
            except Exception as e:
                print(f"[strategy1] {symbol} 처리 오류: {e}")

        self._update_status(price_map)

    def _process(self, symbol: str, price: float):
        self._ticks[symbol].append(price)

        if len(self._ticks[symbol]) < self.cfg["warmup_ticks"]:
            return

        sig = _calc_signals(list(self._ticks[symbol]))
        self._last_signals[symbol] = sig

        in_position = symbol in self._positions

        if not in_position:
            if sig["golden_cross"] and sig["rsi"] < 65:
                # 필터 1: 거래량 급증
                vol_ok, vol_ratio = _check_volume_surge(
                    self.client, symbol, self.cfg["volume_surge_ratio"]
                )
                # 필터 2: 매수잔량 우세
                bid_ok, bid_ratio = _check_orderbook_bias(
                    self.client, symbol, self.cfg["bid_ratio_min"]
                )

                if not vol_ok:
                    print(f"[strategy1] {symbol} 매수 차단 — 거래량 부족 (비율 {vol_ratio:.2f}x, 기준 {self.cfg['volume_surge_ratio']}x)")
                elif not bid_ok:
                    print(f"[strategy1] {symbol} 매수 차단 — 매수잔량 부족 (비율 {bid_ratio:.2f}, 기준 {self.cfg['bid_ratio_min']})")
                else:
                    print(f"[strategy1] {symbol} 매수 신호 통과 — 거래량 {vol_ratio:.2f}x, 매수잔량 {bid_ratio:.0%}")
                    result = self.engine.buy(symbol=symbol, quantity=self.cfg["quantity"], current_price=price)
                    if result:
                        self._positions[symbol] = {
                            "order_id": result["orderId"],
                            "buy_price": price,
                        }
        else:
            buy_price  = self._positions[symbol]["buy_price"]
            change_pct = (price - buy_price) / buy_price * 100

            sell, reason = False, ""

            if sig["dead_cross"]:
                sell, reason = True, "데드크로스"
            elif sig["rsi"] > 75:
                sell, reason = True, f"RSI 과열({sig['rsi']:.1f})"
            elif change_pct <= -self.cfg["stop_loss_pct"]:
                sell, reason = True, f"손절({change_pct:.2f}%)"
            elif change_pct >= self.cfg["take_profit_pct"]:
                sell, reason = True, f"익절({change_pct:.2f}%)"

            if sell:
                print(f"[strategy1] {symbol} 매도 사유: {reason}")
                qty = int(self.cfg["quantity"])
                self._session_realized_pnl += (price - buy_price) * qty
                self.engine.sell(symbol=symbol, quantity=self.cfg["quantity"], current_price=price)
                del self._positions[symbol]

    def _update_status(self, price_map: dict):
        from core import status_server
        from core.db import get_recent_orders as _db_recent_orders

        def get_recent_orders(limit=10):
            if hasattr(self.engine, 'trade_log'):  # PaperEngine
                return self.engine.get_recent_orders(limit=limit)
            return _db_recent_orders(limit=limit)

        positions: dict = {}
        watching: dict = {}
        warmup = self.cfg["warmup_ticks"]
        tp_pct = self.cfg["take_profit_pct"]
        sl_pct = self.cfg["stop_loss_pct"]

        for symbol in self.symbols:
            price = price_map.get(symbol)
            ticks = self._ticks.get(symbol, deque())
            warmup_pct = min(100, int(len(ticks) * 100 / warmup))
            sig = self._last_signals.get(symbol)

            if sig:
                rsi_val = _safe_float(sig["rsi"])
                if sig["golden_cross"]:
                    signal_text = "골든크로스 (매수 신호)"
                elif sig["dead_cross"]:
                    signal_text = "데드크로스 (매도 신호)"
                elif rsi_val and rsi_val > 75:
                    signal_text = f"RSI 과열 ({rsi_val:.1f})"
                else:
                    signal_text = "관망 중"
                signals = {
                    "ema5":         _safe_float(sig["ema5"]),
                    "ema20":        _safe_float(sig["ema20"]),
                    "rsi":          _safe_float(sig["rsi"]),
                    "golden_cross": bool(sig["golden_cross"]),
                    "dead_cross":   bool(sig["dead_cross"]),
                }
            else:
                signal_text = f"워밍업 중 ({warmup_pct}%)"
                signals = {}

            if symbol in self._positions:
                pos = self._positions[symbol]
                buy_price = pos["buy_price"]
                change_pct = round((price - buy_price) / buy_price * 100, 2) if price is not None else 0.0
                positions[symbol] = {
                    "buy_price":         buy_price,
                    "current_price":     price,
                    "change_pct":        change_pct,
                    "take_profit_price": round(buy_price * (1 + tp_pct / 100), 2),
                    "stop_loss_price":   round(buy_price * (1 - sl_pct / 100), 2),
                    "signals":           signals,
                    "signal_text":       signal_text,
                }
            else:
                watching[symbol] = {
                    "current_price": price,
                    "warmup_pct":    warmup_pct,
                    "market_open":   price is not None,
                    "signals":       signals,
                    "signal_text":   signal_text,
                }

        qty = int(self.cfg["quantity"])
        unrealized_pnl = sum(
            (price_map.get(sym, pos["buy_price"]) - pos["buy_price"]) * qty
            for sym, pos in self._positions.items()
        )
        total_pnl = self._session_realized_pnl + unrealized_pnl

        paper_balance = round(self.engine.cash) if hasattr(self.engine, 'cash') else None

        status_server.update({
            "updated_at":    datetime.now(KST).strftime("%H:%M:%S"),
            "positions":     positions,
            "watching":      watching,
            "recent_orders": get_recent_orders(limit=10),
            "pnl_summary": {
                "realized":   round(self._session_realized_pnl),
                "unrealized": round(unrealized_pnl),
                "total":      round(total_pnl),
                "balance":    paper_balance,
            },
        })
