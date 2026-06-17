import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://openapi.tossinvest.com"


class TossClient:
    def __init__(self):
        self.client_id = os.getenv("TOSS_CLIENT_ID")
        self.client_secret = os.getenv("TOSS_CLIENT_SECRET")
        self.account_seq = os.getenv("TOSS_ACCOUNT_SEQ")
        self._token: str | None = None
        self._token_expires_at: float = 0

    # ── 인증 ──────────────────────────────────────────────────────────────────

    def _ensure_token(self):
        if time.time() < self._token_expires_at - 60:
            return
        resp = requests.post(
            f"{BASE_URL}/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expires_at = time.time() + data["expires_in"]

    def _headers(self, with_account: bool = False) -> dict:
        self._ensure_token()
        h = {"Authorization": f"Bearer {self._token}"}
        if with_account:
            h["X-Tossinvest-Account"] = self.account_seq
        return h

    def _get(self, path: str, params: dict = None, with_account: bool = False) -> dict:
        return self._request("GET", path, params=params, with_account=with_account)

    def _post(self, path: str, body: dict = None, with_account: bool = False) -> dict:
        return self._request("POST", path, json=body, with_account=with_account)

    def _request(self, method: str, path: str, with_account: bool = False, **kwargs) -> dict:
        url = f"{BASE_URL}{path}"
        headers = self._headers(with_account=with_account)
        for attempt in range(3):
            resp = requests.request(method, url, headers=headers, **kwargs)
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 1))
                limit     = resp.headers.get("X-RateLimit-Limit", "?")
                remaining = resp.headers.get("X-RateLimit-Remaining", "?")
                print(f"[RateLimit] 429 — 한도:{limit} 남음:{remaining} {retry_after}초 대기 ({path})")
                time.sleep(retry_after)
                continue
            resp.raise_for_status()
            return resp.json()
        resp.raise_for_status()

    # ── 시세 데이터 ───────────────────────────────────────────────────────────

    def get_prices(self, symbols: list[str]) -> list[dict]:
        """현재가 조회 (최대 200종목)"""
        data = self._get("/api/v1/prices", params={"symbols": ",".join(symbols)})
        return data["result"]

    def get_candles(self, symbol: str, interval: str, count: int = 100, before: str = None, adjusted: bool = True) -> dict:
        """캔들 조회. interval: '1m' | '1d'. 응답: {candles, nextBefore}"""
        params = {"symbol": symbol, "interval": interval, "count": count, "adjusted": str(adjusted).lower()}
        if before:
            params["before"] = before
        data = self._get("/api/v1/candles", params=params)
        return data["result"]

    def get_orderbook(self, symbol: str) -> dict:
        """호가 조회"""
        data = self._get("/api/v1/orderbook", params={"symbol": symbol})
        return data["result"]

    def get_trades(self, symbol: str, count: int = 50) -> list[dict]:
        """최근 체결 내역"""
        data = self._get("/api/v1/trades", params={"symbol": symbol, "count": count})
        return data["result"]

    def get_price_limits(self, symbol: str) -> dict:
        """상/하한가 조회"""
        data = self._get("/api/v1/price-limits", params={"symbol": symbol})
        return data["result"]

    # ── 종목 정보 ─────────────────────────────────────────────────────────────

    def get_stocks(self, symbols: list[str]) -> list[dict]:
        """종목 기본 정보 (최대 200종목)"""
        data = self._get("/api/v1/stocks", params={"symbols": ",".join(symbols)})
        return data["result"]

    def get_stock_warnings(self, symbol: str) -> list[dict]:
        """매수 유의사항"""
        data = self._get(f"/api/v1/stocks/{symbol}/warnings")
        return data["result"]

    # ── 시장 정보 ─────────────────────────────────────────────────────────────

    def get_exchange_rate(self, base: str = "USD", quote: str = "KRW") -> dict:
        """환율 (1분 갱신, 참고용)"""
        data = self._get("/api/v1/exchange-rate", params={"baseCurrency": base, "quoteCurrency": quote})
        return data["result"]

    def get_market_calendar_kr(self, date: str = None) -> dict:
        """국내 장 운영 정보 (전일/당일/익일)"""
        params = {"date": date} if date else {}
        data = self._get("/api/v1/market-calendar/KR", params=params)
        return data["result"]

    def get_market_calendar_us(self, date: str = None) -> dict:
        """미국 장 운영 정보"""
        params = {"date": date} if date else {}
        data = self._get("/api/v1/market-calendar/US", params=params)
        return data["result"]

    # ── 계좌 / 자산 ───────────────────────────────────────────────────────────

    def get_accounts(self) -> list[dict]:
        """계좌 목록. accountSeq를 .env TOSS_ACCOUNT_SEQ에 설정해야 함"""
        data = self._get("/api/v1/accounts")
        return data["result"]

    def get_holdings(self, symbol: str = None) -> dict:
        """보유주식 조회"""
        params = {"symbol": symbol} if symbol else {}
        data = self._get("/api/v1/holdings", params=params, with_account=True)
        return data["result"]

    # ── 주문 정보 ─────────────────────────────────────────────────────────────

    def get_buying_power(self, currency: str = "KRW") -> dict:
        """매수 가능 금액"""
        data = self._get("/api/v1/buying-power", params={"currency": currency}, with_account=True)
        return data["result"]

    def get_sellable_quantity(self, symbol: str) -> dict:
        """판매 가능 수량"""
        data = self._get("/api/v1/sellable-quantity", params={"symbol": symbol}, with_account=True)
        return data["result"]

    def get_commissions(self) -> list[dict]:
        """수수료율 조회"""
        data = self._get("/api/v1/commissions", with_account=True)
        return data["result"]

    # ── 주문 ──────────────────────────────────────────────────────────────────

    def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: str = None,
        price: str = None,
        order_amount: str = None,
        client_order_id: str = None,
        time_in_force: str = "DAY",
    ) -> dict:
        """주문 생성. side: BUY|SELL, order_type: LIMIT|MARKET"""
        body = {"symbol": symbol, "side": side, "orderType": order_type, "timeInForce": time_in_force}
        if client_order_id:
            body["clientOrderId"] = client_order_id
        if quantity:
            body["quantity"] = quantity
        if price:
            body["price"] = price
        if order_amount:
            body["orderAmount"] = order_amount
        data = self._post("/api/v1/orders", body=body, with_account=True)
        return data["result"]

    def modify_order(self, order_id: str, order_type: str, price: str, quantity: str = None) -> dict:
        """주문 정정. 미국 주식은 quantity 전달 불가"""
        body = {"orderType": order_type, "price": price}
        if quantity:
            body["quantity"] = quantity
        data = self._post(f"/api/v1/orders/{order_id}/modify", body=body, with_account=True)
        return data["result"]

    def cancel_order(self, order_id: str) -> dict:
        """주문 취소"""
        data = self._post(f"/api/v1/orders/{order_id}/cancel", body={}, with_account=True)
        return data["result"]

    def get_orders(self, status: str, symbol: str = None, cursor: str = None, limit: int = 20) -> dict:
        """주문 목록. status: OPEN|CLOSED"""
        params = {"status": status, "limit": limit}
        if symbol:
            params["symbol"] = symbol
        if cursor:
            params["cursor"] = cursor
        data = self._get("/api/v1/orders", params=params, with_account=True)
        return data["result"]

    def get_order(self, order_id: str) -> dict:
        """주문 상세"""
        data = self._get(f"/api/v1/orders/{order_id}", with_account=True)
        return data["result"]
