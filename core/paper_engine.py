"""
페이퍼 트레이딩 엔진. OrderEngine과 동일한 인터페이스.
실제 API 주문 없이 가상 현금으로 매수/매도를 시뮬레이션한다.
"""
import time
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
_order_counter = 0


def _new_order_id() -> str:
    global _order_counter
    _order_counter += 1
    return f"PAPER-{_order_counter:04d}"


class PaperEngine:
    def __init__(self, virtual_cash: float, strategy: str = "strategy1"):
        self.strategy     = strategy
        self.initial_cash = virtual_cash
        self.cash         = virtual_cash
        # symbol → {quantity, buy_price, buy_time}
        self.positions: dict[str, dict] = {}
        # 완료된 거래 기록
        self.trade_log: list[dict] = []

    def buy(self, symbol: str, quantity: str, price: str = None, current_price: float = None) -> dict | None:
        qty   = int(quantity)
        cost  = (current_price or 0) * qty

        if cost <= 0:
            print(f"[paper] {symbol} 매수 실패: current_price 없음")
            return None
        if self.cash < cost:
            print(f"[paper] {symbol} 잔액 부족 (필요 {cost:,.0f} / 보유 {self.cash:,.0f})")
            return None

        self.cash -= cost
        self.positions[symbol] = {
            "quantity":  qty,
            "buy_price": current_price,
            "buy_time":  datetime.now(KST).isoformat(),
        }
        order_id = _new_order_id()
        print(f"[paper] 매수 → {symbol} {qty}주 @ {current_price:,.2f}  (잔액 {self.cash:,.0f})")
        return {"orderId": order_id}

    def sell(self, symbol: str, quantity: str = None, price: str = None, current_price: float = None) -> dict | None:
        if symbol not in self.positions:
            print(f"[paper] {symbol} 포지션 없음")
            return None

        pos = self.positions[symbol]
        qty = int(quantity) if quantity else pos["quantity"]

        if current_price is None or current_price <= 0:
            print(f"[paper] {symbol} 매도 실패: current_price 없음")
            return None

        proceeds   = current_price * qty
        buy_cost   = pos["buy_price"] * qty
        pnl        = proceeds - buy_cost
        pnl_pct    = pnl / buy_cost * 100

        self.cash += proceeds
        del self.positions[symbol]

        record = {
            "symbol":    symbol,
            "quantity":  qty,
            "buy_price": pos["buy_price"],
            "sell_price": current_price,
            "buy_time":  pos["buy_time"],
            "sell_time": datetime.now(KST).isoformat(),
            "pnl":       round(pnl, 2),
            "pnl_pct":   round(pnl_pct, 2),
        }
        self.trade_log.append(record)

        sign = "+" if pnl >= 0 else ""
        print(f"[paper] 매도 → {symbol} {qty}주 @ {current_price:,.2f}  {sign}{pnl:,.0f}원 ({sign}{pnl_pct:.2f}%)  (잔액 {self.cash:,.0f})")
        return {"orderId": _new_order_id()}

    def cancel(self, order_id: str) -> dict:
        return {"orderId": order_id}

    def get_recent_orders(self, limit: int = 10) -> list[dict]:
        """db.get_recent_orders()와 동일한 포맷으로 최근 주문 반환."""
        orders = []
        for sym, pos in self.positions.items():
            orders.append({
                "created_at": pos["buy_time"],
                "symbol": sym,
                "side": "BUY",
                "price": str(pos["buy_price"]),
                "quantity": str(pos["quantity"]),
                "status": "OPEN",
                "pnl": None,
                "pnl_pct": None,
            })
        for t in self.trade_log:
            orders.append({
                "created_at": t["buy_time"],
                "symbol": t["symbol"],
                "side": "BUY",
                "price": str(t["buy_price"]),
                "quantity": str(t["quantity"]),
                "status": "FILLED",
                "pnl": None,
                "pnl_pct": None,
            })
            orders.append({
                "created_at": t["sell_time"],
                "symbol": t["symbol"],
                "side": "SELL",
                "price": str(t["sell_price"]),
                "quantity": str(t["quantity"]),
                "status": "FILLED",
                "pnl": t["pnl"],
                "pnl_pct": t["pnl_pct"],
            })
        orders.sort(key=lambda x: x["created_at"], reverse=True)
        return orders[:limit]

    def get_report(self, current_prices: dict[str, float] = None) -> dict:
        """거래 결과 리포트 생성."""
        current_prices = current_prices or {}

        total_trades = len(self.trade_log)
        wins  = sum(1 for t in self.trade_log if t["pnl"] > 0)
        win_rate = (wins / total_trades * 100) if total_trades else 0
        total_pnl = sum(t["pnl"] for t in self.trade_log)

        # 미실현 손익
        unrealized = []
        for sym, pos in self.positions.items():
            cur = current_prices.get(sym)
            if cur:
                upnl = (cur - pos["buy_price"]) * pos["quantity"]
                upnl_pct = (cur - pos["buy_price"]) / pos["buy_price"] * 100
                unrealized.append({
                    "symbol":    sym,
                    "quantity":  pos["quantity"],
                    "buy_price": pos["buy_price"],
                    "cur_price": cur,
                    "upnl":      round(upnl, 2),
                    "upnl_pct":  round(upnl_pct, 2),
                })

        return {
            "initial_cash":  self.initial_cash,
            "final_cash":    round(self.cash, 2),
            "total_pnl":     round(total_pnl, 2),
            "total_return_pct": round(total_pnl / self.initial_cash * 100, 2),
            "total_trades":  total_trades,
            "wins":          wins,
            "losses":        total_trades - wins,
            "win_rate_pct":  round(win_rate, 2),
            "open_positions": unrealized,
            "trade_log":     self.trade_log,
        }
