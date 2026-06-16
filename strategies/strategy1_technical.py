import os
import time
from datetime import datetime, timezone, timedelta

import pandas as pd
import pandas_ta as ta

from core.toss_client import TossClient
from core.order_engine import OrderEngine

KST = timezone(timedelta(hours=9))

# 종목당 설정값
DEFAULT_CONFIG = {
    "quantity": "1",       # 1회 주문 수량
    "stop_loss_pct": 2.0,  # 손절 % (매수가 대비 하락)
    "take_profit_pct": 4.0, # 익절 %
}


def get_candles_df(client: TossClient, symbol: str, interval: str = "1m", count: int = 60) -> pd.DataFrame:
    """캔들 데이터를 DataFrame으로 반환. 오래된 것부터 정렬."""
    result = client.get_candles(symbol=symbol, interval=interval, count=count)
    candles = result["candles"]
    df = pd.DataFrame(candles)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    for col in ["openPrice", "highPrice", "lowPrice", "closePrice", "volume"]:
        df[col] = pd.to_numeric(df[col])
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def calc_signals(df: pd.DataFrame) -> pd.DataFrame:
    """EMA5, EMA20, RSI14 계산 후 매수/매도 신호 추가."""
    df["ema5"]  = ta.ema(df["closePrice"], length=5)
    df["ema20"] = ta.ema(df["closePrice"], length=20)
    df["rsi"]   = ta.rsi(df["closePrice"], length=14)

    # 골든크로스: 직전 봉에서 ema5 < ema20 이었다가 현재 봉에서 ema5 > ema20
    df["golden_cross"] = (df["ema5"] > df["ema20"]) & (df["ema5"].shift(1) <= df["ema20"].shift(1))
    # 데드크로스: 반대
    df["dead_cross"]   = (df["ema5"] < df["ema20"]) & (df["ema5"].shift(1) >= df["ema20"].shift(1))
    return df


def is_market_open(client: TossClient, symbol: str) -> bool:
    """현재 정규장 운영 중인지 확인."""
    now = datetime.now(KST)
    try:
        if _is_us(symbol):
            cal = client.get_market_calendar_us()
            session = cal["today"].get("regularMarket")
        else:
            cal = client.get_market_calendar_kr()
            integrated = cal["today"].get("integrated")
            session = integrated.get("regularMarket") if integrated else None

        if not session:
            return False

        start = datetime.fromisoformat(session["startTime"])
        end   = datetime.fromisoformat(session["endTime"])
        return start <= now <= end
    except Exception:
        return False


def _is_us(symbol: str) -> bool:
    return symbol.isalpha()


class Strategy1:
    """
    기술적 단타 전략.
    - 매수: EMA5/EMA20 골든크로스 + RSI < 65
    - 매도: EMA5/EMA20 데드크로스 OR RSI > 75 OR 손절/익절 도달
    """

    def __init__(self, client: TossClient, symbols: list[str], config: dict = None):
        self.client  = client
        self.engine  = OrderEngine(client, strategy="strategy1")
        self.symbols = symbols
        self.cfg     = {**DEFAULT_CONFIG, **(config or {})}
        # symbol → {"order_id": str, "buy_price": float}
        self._positions: dict[str, dict] = {}

    def run_once(self):
        """1분마다 호출. 각 종목에 대해 신호 확인 후 주문."""
        for symbol in self.symbols:
            try:
                self._process(symbol)
            except Exception as e:
                print(f"[strategy1] {symbol} 처리 오류: {e}")

    def _process(self, symbol: str):
        if not is_market_open(self.client, symbol):
            return

        df = get_candles_df(self.client, symbol, interval="1m", count=60)
        if len(df) < 25:  # EMA20 계산에 최소 20봉 필요
            return

        df = calc_signals(df)
        last = df.iloc[-1]

        in_position = symbol in self._positions

        if not in_position:
            # 매수 조건: 골든크로스 + RSI 과열 아님
            if last["golden_cross"] and last["rsi"] < 65:
                result = self.engine.buy(symbol=symbol, quantity=self.cfg["quantity"])
                if result:
                    self._positions[symbol] = {
                        "order_id": result["orderId"],
                        "buy_price": float(last["closePrice"]),
                    }
        else:
            buy_price  = self._positions[symbol]["buy_price"]
            cur_price  = float(last["closePrice"])
            change_pct = (cur_price - buy_price) / buy_price * 100

            sell = False
            reason = ""

            if last["dead_cross"]:
                sell, reason = True, "데드크로스"
            elif last["rsi"] > 75:
                sell, reason = True, f"RSI 과열({last['rsi']:.1f})"
            elif change_pct <= -self.cfg["stop_loss_pct"]:
                sell, reason = True, f"손절({change_pct:.2f}%)"
            elif change_pct >= self.cfg["take_profit_pct"]:
                sell, reason = True, f"익절({change_pct:.2f}%)"

            if sell:
                print(f"[strategy1] {symbol} 매도 사유: {reason}")
                self.engine.sell(symbol=symbol, quantity=self.cfg["quantity"])
                del self._positions[symbol]
