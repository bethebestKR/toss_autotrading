"""
전략 2 — 가치 분석 중장기

1. analyze_universe(symbols)  : 재무 데이터 수집 → Claude 가치 평가 → 매수 추천 반환
2. execute_buy(recommendation): 추천 종목 실제 매수 (사용자 확인 후)
3. run_monitor_once()         : 보유 포지션 목표가/손절 체크 (일 1~2회 호출)

보유 기간: 2주 ~ 3개월 (중장기)
손절: -7%  |  목표: +15% (config로 조정 가능)
"""
import json
import os
from datetime import datetime, timezone, timedelta

from core.toss_client import TossClient
from core.order_engine import OrderEngine
from core import db, discord_notifier
from core.financial_data import get_financials_batch, fmt_financials

KST = timezone(timedelta(hours=9))

# 기본 분석 유니버스 (KOSPI 대형주 + 미국 대형주)
DEFAULT_KR_UNIVERSE = [
    "005930",  # 삼성전자
    "000660",  # SK하이닉스
    "035420",  # NAVER
    "005380",  # 현대차
    "051910",  # LG화학
    "006400",  # 삼성SDI
    "035720",  # 카카오
    "000270",  # 기아
    "068270",  # 셀트리온
    "105560",  # KB금융
]
DEFAULT_US_UNIVERSE = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META",
    "NVDA", "TSLA", "BRK-B", "JPM", "JNJ",
]

DEFAULT_CONFIG = {
    "target_profit_pct":    15.0,   # 목표 수익률 (%)
    "stop_loss_pct":        7.0,    # 손절 기준 (%)
    "max_positions":        5,      # 동시 최대 보유 종목
    "max_position_pct":     0.20,   # 종목당 최대 자금 비율
    "claude_model":         "claude-sonnet-4-6",
    "financial_cache_days": 7,      # 재무 데이터 캐시 TTL
    "top_n":                3,      # Claude에게 추천 받을 최대 종목 수
}

_ANALYSIS_SYSTEM = """당신은 가치투자 전문 애널리스트입니다.
아래 기업들의 재무 데이터를 분석해 투자 매력도를 평가하고 최우선 매수 후보를 선정하세요.

평가 기준:
- 매출 성장률 > 10% 우대
- 영업이익률 > 10% 우대
- ROE > 15% 우대
- 부채비율 < 150% 선호
- PER: 업종 평균 대비 저평가 여부
- 순이익 증가 추세

응답 형식 (JSON 배열, top_n개 이내):
[
  {
    "symbol": "종목코드",
    "action": "BUY",
    "target_pct": 숫자(목표수익률%),
    "stop_pct": 숫자(손절기준%),
    "hold_weeks": 숫자(예상보유주수),
    "score": 숫자(100점 만점),
    "reason": "매수 근거 2~3줄"
  }
]
데이터가 부족하거나 투자 매력이 없는 종목은 목록에서 제외하세요.
응답은 반드시 JSON 배열만 출력하세요 (```json 블록 포함 금지).
"""


class Strategy2:
    def __init__(self, client: TossClient, config: dict = None, engine=None):
        self.client  = client
        self.engine  = engine if engine is not None else OrderEngine(client, strategy="strategy2")
        self.cfg     = {**DEFAULT_CONFIG, **(config or {})}
        # symbol → {buy_price, quantity, target_pct, stop_pct, bought_at}
        self._positions: dict[str, dict] = {}

        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("[경고] ANTHROPIC_API_KEY 없음 — Claude 분석 불가. .env를 확인하세요.")

    # ── 재무 분석 ─────────────────────────────────────────────────────────────

    def analyze_universe(self, symbols: list[str] = None) -> list[dict]:
        """
        재무 데이터 수집 → Claude 가치 평가 → 매수 추천 목록 반환.
        symbols 미지정 시 DEFAULT_KR_UNIVERSE + DEFAULT_US_UNIVERSE 사용.
        """
        universe = symbols or (DEFAULT_KR_UNIVERSE + DEFAULT_US_UNIVERSE)
        print(f"\n[strategy2] {len(universe)}개 종목 재무 데이터 수집 중...")

        fin_data = get_financials_batch(universe, cache_days=self.cfg["financial_cache_days"])
        if not fin_data:
            print("[strategy2] 재무 데이터를 가져오지 못했습니다.")
            return []

        print(f"[strategy2] {len(fin_data)}/{len(universe)}개 수집 완료. Claude 분석 중...")

        # 현재가 보완 (PER/PBR 계산용 — KR 종목)
        kr_symbols = [s for s in fin_data if fin_data[s]["market"] == "KR"]
        if kr_symbols:
            try:
                price_list = self.client.get_prices(kr_symbols[:200])
                for p in price_list:
                    sym = p["symbol"]
                    if sym in fin_data:
                        fin_data[sym]["current_price"] = float(p["lastPrice"])
            except Exception as e:
                print(f"[strategy2] 현재가 조회 실패: {e}")

        return self._ask_claude_analysis(fin_data)

    def _ask_claude_analysis(self, fin_data: dict[str, dict]) -> list[dict]:
        """Claude에게 재무 데이터 분석 요청 → 추천 목록 반환."""
        import anthropic
        body_parts = [fmt_financials(d) for d in fin_data.values()]
        user_msg   = "\n\n".join(body_parts)
        user_msg  += f"\n\n상위 {self.cfg['top_n']}개 이내로 추천해 주세요."

        try:
            client = anthropic.Anthropic()
            resp   = client.messages.create(
                model=self.cfg["claude_model"],
                max_tokens=1500,
                system=_ANALYSIS_SYSTEM,
                messages=[{"role": "user", "content": user_msg}],
            )
            raw = resp.content[0].text.strip()
        except Exception as e:
            print(f"[strategy2] Claude 호출 실패: {e}")
            return []

        try:
            recommendations = json.loads(raw)
            if not isinstance(recommendations, list):
                raise ValueError("JSON 배열이 아님")
        except Exception as e:
            print(f"[strategy2] Claude 응답 파싱 실패: {e}\n응답: {raw[:300]}")
            return []

        # fin_data에서 name 보완
        for rec in recommendations:
            sym = rec.get("symbol", "")
            if sym in fin_data:
                rec["name"] = fin_data[sym].get("name", sym)

        return recommendations

    # ── 매수 실행 ─────────────────────────────────────────────────────────────

    def execute_buy(self, rec: dict, price: float = None) -> bool:
        """
        추천 종목 매수 실행.
        rec: analyze_universe() 반환 항목 {symbol, target_pct, stop_pct, ...}
        price: None이면 현재가 자동 조회
        """
        symbol = rec["symbol"]
        if symbol in self._positions:
            print(f"[strategy2] {symbol} 이미 보유 중 — 건너뜀")
            return False
        if len(self._positions) >= self.cfg["max_positions"]:
            print(f"[strategy2] 최대 보유 종목 수({self.cfg['max_positions']}) 초과")
            return False

        if price is None:
            try:
                price_list = self.client.get_prices([symbol])
                price = float(price_list[0]["lastPrice"])
            except Exception as e:
                print(f"[strategy2] {symbol} 현재가 조회 실패: {e}")
                return False

        qty_str = self._calc_qty(symbol, price)
        result  = self.engine.buy(symbol=symbol, quantity=qty_str, current_price=price)
        if not result:
            return False

        target_pct = float(rec.get("target_pct", self.cfg["target_profit_pct"]))
        stop_pct   = float(rec.get("stop_pct",   self.cfg["stop_loss_pct"]))
        self._positions[symbol] = {
            "buy_price":  price,
            "quantity":   int(qty_str),
            "target_pct": target_pct,
            "stop_pct":   stop_pct,
            "bought_at":  datetime.now(KST).isoformat(),
            "reason":     rec.get("reason", ""),
        }
        print(f"[strategy2] {symbol} 매수 완료 — {price:,.0f} × {qty_str} | "
              f"목표 +{target_pct:.1f}% / 손절 -{stop_pct:.1f}%")
        discord_notifier.notify_buy(symbol, price, int(qty_str), stop_pct, target_pct)
        return True

    # ── 포지션 모니터링 ───────────────────────────────────────────────────────

    def run_monitor_once(self):
        """보유 포지션 목표가/손절 체크. 일 1~2회 또는 APScheduler로 호출."""
        if not self._positions:
            return

        symbols = list(self._positions.keys())
        try:
            price_list = self.client.get_prices(symbols)
            price_map  = {p["symbol"]: float(p["lastPrice"]) for p in price_list}
        except Exception as e:
            print(f"[strategy2] 현재가 조회 실패: {e}")
            return

        for symbol in list(self._positions.keys()):
            price = price_map.get(symbol)
            if price is None:
                continue
            pos = self._positions[symbol]
            pnl_pct = (price - pos["buy_price"]) / pos["buy_price"] * 100

            if pnl_pct >= pos["target_pct"]:
                print(f"[strategy2] {symbol} 목표 달성 +{pnl_pct:.1f}% — 매도")
                self._do_sell(symbol, price, f"목표 달성 {pnl_pct:+.1f}%")
            elif pnl_pct <= -pos["stop_pct"]:
                print(f"[strategy2] {symbol} 손절 {pnl_pct:.1f}% — 매도")
                self._do_sell(symbol, price, f"손절 {pnl_pct:+.1f}%")
            else:
                print(f"[strategy2] {symbol} 모니터링 중 — {pnl_pct:+.1f}% "
                      f"(목표 +{pos['target_pct']:.1f}% / 손절 -{pos['stop_pct']:.1f}%)")

    def _do_sell(self, symbol: str, price: float, reason: str):
        pos = self._positions.pop(symbol, None)
        if pos is None:
            return
        qty    = pos["quantity"]
        pnl_pct = (price - pos["buy_price"]) / pos["buy_price"] * 100
        self.engine.sell(symbol=symbol, quantity=str(qty), current_price=price)
        discord_notifier.notify_sell(symbol, price, pnl_pct, reason)

    def _calc_qty(self, symbol: str, price: float) -> str:
        try:
            if hasattr(self.engine, "cash"):
                buying_power = self.engine.cash
            else:
                currency     = "USD" if symbol.replace(".", "").replace("-", "").isalpha() else "KRW"
                buying_power = float(self.client.get_buying_power(currency=currency)["cashBuyingPower"])
            budget = buying_power * self.cfg["max_position_pct"]
            return str(max(1, int(budget / price)))
        except Exception:
            return "1"

    # ── 상태 조회 ─────────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        """대시보드/출력용 현재 상태 반환."""
        return {
            "strategy": "strategy2_fundamental",
            "positions": {
                sym: {
                    **pos,
                    "pnl_pct": None,   # 현재가 미조회 상태
                }
                for sym, pos in self._positions.items()
            },
        }

    def print_status(self):
        if not self._positions:
            print("[strategy2] 보유 포지션 없음")
            return
        print(f"\n[strategy2] 보유 포지션 ({len(self._positions)}개)")
        print(f"{'종목':<12} {'매수가':>10} {'수량':>6} {'목표':>7} {'손절':>7} {'매수일'}")
        print("-" * 60)
        for sym, pos in self._positions.items():
            print(f"{sym:<12} {pos['buy_price']:>10,.0f} {pos['quantity']:>6} "
                  f"{pos['target_pct']:>6.1f}% {pos['stop_pct']:>6.1f}% "
                  f"{pos['bought_at'][:10]}")
