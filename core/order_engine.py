from core.toss_client import TossClient
from core import db


class OrderEngine:
    def __init__(self, client: TossClient, strategy: str):
        self.client = client
        self.strategy = strategy

    def buy(self, symbol: str, quantity: str, price: str = None, current_price: float = None) -> dict | None:
        """
        지정가(price 전달 시) 또는 시장가로 매수.
        매수 가능 금액 부족 시 None 반환.
        """
        currency = "USD" if self._is_us(symbol) else "KRW"
        power = self.client.get_buying_power(currency=currency)
        if float(power["cashBuyingPower"]) <= 0:
            print(f"[{self.strategy}] 매수 가능 금액 없음 ({currency})")
            return None

        order_type = "LIMIT" if price else "MARKET"
        result = self.client.create_order(
            symbol=symbol,
            side="BUY",
            order_type=order_type,
            quantity=quantity,
            price=price,
        )
        db.save_order(
            strategy=self.strategy,
            order_id=result["orderId"],
            symbol=symbol,
            side="BUY",
            order_type=order_type,
            quantity=quantity,
            price=price,
        )
        print(f"[{self.strategy}] 매수 주문 → {symbol} {quantity}주 @ {price or '시장가'} (orderId: {result['orderId']})")
        return result

    def sell(self, symbol: str, quantity: str = None, price: str = None, current_price: float = None) -> dict | None:
        """
        지정가(price 전달 시) 또는 시장가로 매도.
        quantity 미전달 시 판매 가능 수량 전량 매도.
        """
        if quantity is None:
            sq = self.client.get_sellable_quantity(symbol)
            quantity = sq["sellableQuantity"]
        if float(quantity) <= 0:
            print(f"[{self.strategy}] 판매 가능 수량 없음 ({symbol})")
            return None

        order_type = "LIMIT" if price else "MARKET"
        result = self.client.create_order(
            symbol=symbol,
            side="SELL",
            order_type=order_type,
            quantity=quantity,
            price=price,
        )
        db.save_order(
            strategy=self.strategy,
            order_id=result["orderId"],
            symbol=symbol,
            side="SELL",
            order_type=order_type,
            quantity=quantity,
            price=price,
        )
        print(f"[{self.strategy}] 매도 주문 → {symbol} {quantity}주 @ {price or '시장가'} (orderId: {result['orderId']})")
        return result

    def cancel(self, order_id: str) -> dict:
        result = self.client.cancel_order(order_id)
        db.update_order_status(order_id, "CANCELED")
        print(f"[{self.strategy}] 주문 취소 → orderId: {order_id}")
        return result

    def _is_us(self, symbol: str) -> bool:
        return symbol.isalpha()
