"""
Phase 2 — Claude 종목 선별 자동화 (StockScanner)

장 중 n분 주기로 유니버스를 스캔하여 조건 충족 종목을 watchlist DB에 편입하고
Strategy1의 symbols 목록을 실시간 업데이트한다.

편입 조건: 단기 모멘텀 상승 + 거래량 급증 + 매수잔량 우세
이탈 조건: 모멘텀 소멸 (조건 동시 미달)
"""
import time
import threading
from datetime import datetime, timezone, timedelta

from core.toss_client import TossClient
from core import db
from strategies.strategy1_technical import is_market_open


def _check_volume_surge(client: TossClient, symbol: str, threshold: float) -> tuple[bool, float]:
    try:
        trades = client.get_trades(symbol, count=50)
        if len(trades) < 15:
            return True, 0.0
        volumes = [float(t["volume"]) for t in trades]
        recent = sum(volumes[:10])
        base   = sum(volumes[10:]) / (len(volumes) - 10) * 10
        ratio  = recent / base if base > 0 else 0.0
        return ratio >= threshold, round(ratio, 2)
    except Exception:
        return True, 0.0


def _check_orderbook_bias(client: TossClient, symbol: str, min_bid_ratio: float) -> tuple[bool, float]:
    try:
        ob = client.get_orderbook(symbol)
        result = ob.get("result", ob)
        bid_vol = sum(float(b["volume"]) for b in result.get("bids", []))
        ask_vol = sum(float(a["volume"]) for a in result.get("asks", []))
        total   = bid_vol + ask_vol
        ratio   = bid_vol / total if total > 0 else 0.5
        return ratio >= min_bid_ratio, round(ratio, 2)
    except Exception:
        return True, 0.0

KST = timezone(timedelta(hours=9))

# KOSPI 시총 상위 종목 (스캔 유니버스)
_KR_UNIVERSE = [
    "005930",  # 삼성전자
    "000660",  # SK하이닉스
    "005380",  # 현대차
    "000270",  # 기아
    "035420",  # NAVER
    "035720",  # 카카오
    "066570",  # LG전자
    "105560",  # KB금융
    "055550",  # 신한지주
    "086790",  # 하나금융지주
    "068270",  # 셀트리온
    "003550",  # LG
    "012330",  # 현대모비스
    "028260",  # 삼성물산
    "051910",  # LG화학
    "006400",  # 삼성SDI
    "032830",  # 삼성생명
    "017670",  # SK텔레콤
    "030200",  # KT
    "096770",  # SK이노베이션
]

# 미국 유니버스 (토스에서 거래 가능한 주요 종목)
_US_UNIVERSE = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
    "TSLA", "META", "NFLX", "AMD", "AVGO",
    "TSM",  "ORCL", "CRM",  "PLTR","SNOW",
    "JPM",  "V",    "MA",   "BRK.B","GS",
    "LLY",  "UNH",  "JNJ",  "ABBV","MRK",
    "XOM",  "CVX",  "QQQ",  "SPY", "SOXX",
]

DEFAULT_SCANNER_CONFIG = {
    "scan_interval_sec": 180,     # 스캔 주기 (초)
    "max_watchlist":     10,      # watchlist 최대 종목 수
    "momentum_min_pct":  0.3,     # 스캔 간격 동안 최소 상승률 (%)
    "volatility_min_pct": 0.2,    # 최소 변동성 (고가-저가 범위, 캔들 기준 %)
    "volume_surge_ratio": 1.5,
    "bid_ratio_min":      0.55,
    "min_score":          2,      # 편입 최소 점수 (0~4)
    "exit_score":         1,      # 이 점수 이하면 이탈
}


class StockScanner:
    """
    장 중 주기적 스캔으로 전략1 watchlist를 자동 관리.
    strategy.symbols를 직접 수정하여 전략1 폴링 루프와 실시간 연동.
    """

    def __init__(self, client: TossClient, strategy, universe_kr=None, universe_us=None, config=None):
        self.client   = client
        self.strategy = strategy   # Strategy1 인스턴스 (symbols 수정 대상)
        self.cfg      = {**DEFAULT_SCANNER_CONFIG, **(config or {})}

        self._universe: list[str] = (universe_kr or _KR_UNIVERSE) + (universe_us or _US_UNIVERSE)
        # symbol → price at last scan (모멘텀 계산용)
        self._last_prices: dict[str, float] = {}
        # 스캐너가 추가한 종목 집합 (수동 추가 종목과 구분)
        self._scanner_added: set[str] = set()
        self._stop_event = threading.Event()

    # ── 외부 인터페이스 ────────────────────────────────────────────────────────

    def start(self) -> threading.Thread:
        """백그라운드 스캔 스레드 시작."""
        t = threading.Thread(target=self._scan_loop, daemon=True, name="StockScanner")
        t.start()
        print(f"[scanner] 종목 스캐너 시작 (유니버스 {len(self._universe)}종목, {self.cfg['scan_interval_sec']}초 주기)")
        return t

    def stop(self):
        self._stop_event.set()

    # ── 내부 루프 ──────────────────────────────────────────────────────────────

    def _scan_loop(self):
        while not self._stop_event.is_set():
            try:
                self._scan()
            except Exception as e:
                print(f"[scanner] 스캔 오류: {e}")
            self._stop_event.wait(self.cfg["scan_interval_sec"])

    def _scan(self):
        now = datetime.now(KST)

        # 장 중인 종목만 필터
        active = [s for s in self._universe if is_market_open(self.client, s)]
        if not active:
            return

        # 현재가 일괄 조회 (1 API call)
        try:
            price_list = self.client.get_prices(active)
        except Exception as e:
            print(f"[scanner] 현재가 조회 실패: {e}")
            return
        price_map = {p["symbol"]: float(p["lastPrice"]) for p in price_list}

        candidates: list[tuple[str, float, str]] = []   # (symbol, score, reason)

        for symbol in active:
            price = price_map.get(symbol)
            if not price:
                continue

            score, reasons = self._score_symbol(symbol, price)

            if symbol in self._scanner_added:
                # 이탈 조건 확인
                if score <= self.cfg["exit_score"]:
                    self._remove(symbol, f"모멘텀 소멸 (점수 {score})")
            else:
                if score >= self.cfg["min_score"]:
                    candidates.append((symbol, score, ", ".join(reasons)))

            self._last_prices[symbol] = price

        # 후보 중 점수 높은 순으로 편입 (max_watchlist 초과 방지)
        candidates.sort(key=lambda x: x[1], reverse=True)
        current_wl = db.get_watchlist()
        remaining_slots = self.cfg["max_watchlist"] - len(current_wl)

        for symbol, score, reason in candidates[:remaining_slots]:
            if symbol not in self.strategy.symbols:
                self._add(symbol, score, reason)

        if candidates:
            top = candidates[0]
            print(f"[scanner] 스캔 완료 ({now.strftime('%H:%M:%S')}) — 후보 {len(candidates)}건, 편입 {min(len(candidates), max(0, remaining_slots))}건")

    def _score_symbol(self, symbol: str, price: float) -> tuple[float, list[str]]:
        """0~4점 스코어 계산. 조건별 +1점."""
        score   = 0
        reasons = []

        # 1. 단기 모멘텀: 이전 스캔 대비 상승률
        prev = self._last_prices.get(symbol, 0.0)
        if prev > 0:
            momentum_pct = (price - prev) / prev * 100
            if momentum_pct >= self.cfg["momentum_min_pct"]:
                score += 1
                reasons.append(f"모멘텀 +{momentum_pct:.2f}%")

        # 2. 단기 변동성 (캔들에서 고저 범위 확인)
        try:
            candles = self.client.get_candles(symbol, "1m", count=10)
            raw = candles.get("candles", candles) if isinstance(candles, dict) else candles
            if raw:
                highs  = [float(c["highPrice"])  for c in raw]
                lows   = [float(c["lowPrice"])   for c in raw]
                closes = [float(c["closePrice"]) for c in raw]
                avg_close = sum(closes) / len(closes)
                avg_range = sum(h - l for h, l in zip(highs, lows)) / len(raw)
                vol_pct   = avg_range / avg_close * 100 if avg_close else 0
                if vol_pct >= self.cfg["volatility_min_pct"]:
                    score += 1
                    reasons.append(f"변동성 {vol_pct:.2f}%")
        except Exception:
            pass

        # 3. 거래량 급증
        vol_ok, vol_ratio = _check_volume_surge(self.client, symbol, self.cfg["volume_surge_ratio"])
        if vol_ok and vol_ratio > 0:
            score += 1
            reasons.append(f"거래량 {vol_ratio:.1f}x")

        # 4. 매수잔량 우세
        bid_ok, bid_ratio = _check_orderbook_bias(self.client, symbol, self.cfg["bid_ratio_min"])
        if bid_ok:
            score += 1
            reasons.append(f"매수잔량 {bid_ratio:.0%}")

        return score, reasons

    def _add(self, symbol: str, score: float, reason: str):
        db.add_to_watchlist(symbol, reason=reason, score=score)
        if symbol not in self.strategy.symbols:
            self.strategy.symbols.append(symbol)
        self._scanner_added.add(symbol)
        print(f"[scanner] ▲ 편입: {symbol}  점수 {score}/4  ({reason})")

    def _remove(self, symbol: str, reason: str):
        db.remove_from_watchlist(symbol, reason=reason)
        self._scanner_added.discard(symbol)

        # 보유 중이면 청산 신호가 strategy1에서 먼저 처리 — 종목은 list에서만 제거
        if symbol in self.strategy._positions:
            print(f"[scanner] ▼ 이탈 예약 (보유 중): {symbol} — {reason}")
        else:
            if symbol in self.strategy.symbols:
                self.strategy.symbols.remove(symbol)
            print(f"[scanner] ▼ 이탈: {symbol} — {reason}")
