# 토스증권 Open API 레퍼런스

- **버전**: 1.1.1
- **Base URL**: `https://openapi.tossinvest.com`
- **원문 JSON**: `https://openapi.tossinvest.com/openapi-docs/latest/openapi.json`
- **인증**: OAuth 2.0 Client Credentials Grant
- **토큰 유효기간**: 86400초 (1일), Refresh token 없음
- **클라이언트당 유효 토큰**: 1개 (재발급 시 이전 토큰 즉시 무효화)

---

## 공통

**요청 헤더**
```
Authorization: Bearer {access_token}           ← 모든 API (토큰 발급 제외)
X-Tossinvest-Account: {accountSeq}             ← 계좌/자산/주문 관련 API만
```

**공통 응답 envelope**
```json
{
  "result": {},
  "error": {
    "requestId": "string",
    "code": "string",
    "message": "string",
    "data": {}
  }
}
```

---

## 1. 인증

### POST /oauth2/token
**요청** (`application/x-www-form-urlencoded`, Authorization 헤더 불필요)
```
grant_type=client_credentials
client_id=c_01HXYZABCDEFG123456789
client_secret=s_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```
**응답**
```json
{
  "access_token": "eyJraWQi...",
  "token_type": "Bearer",
  "expires_in": 86400
}
```

---

## 2. 시세 데이터

### GET /api/v1/prices
현재가 조회 (최대 200건)

| 파라미터 | 필수 | 설명 |
|----------|------|------|
| symbols | O | 콤마 구분, 최대 200개. 예: `005930,AAPL` |

**응답**
```json
{
  "result": [
    { "symbol": "005930", "timestamp": "2026-03-25T09:30:00.123+09:00", "lastPrice": "72000", "currency": "KRW" },
    { "symbol": "AAPL",   "timestamp": "2026-03-25T22:30:00.456+09:00", "lastPrice": "185.70", "currency": "USD" }
  ]
}
```

---

### GET /api/v1/candles
캔들 차트 조회 (최대 200봉)

| 파라미터 | 필수 | 설명 |
|----------|------|------|
| symbol | O | 종목 심볼 |
| interval | O | `1m` (1분봉) \| `1d` (일봉) |
| count | - | 1~200, 기본값 100 |
| before | - | ISO 8601. 이 시각보다 이전 봉만 반환. 페이징에 이전 응답의 `nextBefore` 사용 |
| adjusted | - | 수정주가 여부, 기본값 true |

**응답**
```json
{
  "result": {
    "candles": [
      {
        "timestamp": "2026-03-25T09:32:00+09:00",
        "openPrice": "72000", "highPrice": "72100",
        "lowPrice": "71950", "closePrice": "72050",
        "volume": "15200", "currency": "KRW"
      }
    ],
    "nextBefore": "2026-03-25T09:31:00+09:00"
  }
}
```
> `nextBefore`가 `null`이면 마지막 페이지

---

### GET /api/v1/orderbook
호가 조회

| 파라미터 | 필수 | 설명 |
|----------|------|------|
| symbol | O | 종목 심볼 |

**응답**
```json
{
  "result": {
    "timestamp": "2026-03-25T09:30:00.123+09:00",
    "currency": "KRW",
    "asks": [{"price": "72300", "volume": "1200"}, {"price": "72200", "volume": "3400"}],
    "bids": [{"price": "72000", "volume": "5200"}, {"price": "71900", "volume": "4100"}]
  }
}
```

---

### GET /api/v1/trades
최근 체결 내역 조회 (당일)

| 파라미터 | 필수 | 설명 |
|----------|------|------|
| symbol | O | 종목 심볼 |
| count | - | 1~50, 기본값 50 |

**응답**
```json
{
  "result": [
    { "price": "72000", "volume": "120", "timestamp": "2026-03-25T09:30:42.000+09:00", "currency": "KRW" }
  ]
}
```

---

### GET /api/v1/price-limits
상/하한가 조회

| 파라미터 | 필수 | 설명 |
|----------|------|------|
| symbol | O | 종목 심볼 |

**응답**
```json
{
  "result": {
    "timestamp": "2026-03-25T09:30:00.123+09:00",
    "upperLimitPrice": "93000",
    "lowerLimitPrice": "50400",
    "currency": "KRW"
  }
}
```
> 미국 주식은 가격제한 없음 → `upperLimitPrice`, `lowerLimitPrice` 모두 `null`

---

## 3. 종목 정보

### GET /api/v1/stocks
종목 기본 정보 조회 (최대 200건)

| 파라미터 | 필수 | 설명 |
|----------|------|------|
| symbols | O | 콤마 구분, 최대 200개 |

**응답**
```json
{
  "result": [
    {
      "symbol": "005930", "name": "삼성전자", "englishName": "SamsungElec",
      "isinCode": "KR7005930003", "market": "KOSPI",
      "securityType": "STOCK",
      "isCommonShare": true, "status": "ACTIVE",
      "currency": "KRW", "listDate": "1975-06-11", "delistDate": null,
      "sharesOutstanding": "5919637922", "leverageFactor": null,
      "koreanMarketDetail": {
        "liquidationTrading": false, "nxtSupported": true,
        "krxTradingSuspended": false, "nxtTradingSuspended": false
      }
    },
    {
      "symbol": "AAPL", "name": "애플", "englishName": "APPLE INC",
      "isinCode": "US0378331005", "market": "NASDAQ",
      "securityType": "STOCK", "isCommonShare": true, "status": "ACTIVE",
      "currency": "USD", "listDate": "1980-12-12", "delistDate": null,
      "sharesOutstanding": "14702703000", "leverageFactor": null,
      "koreanMarketDetail": null
    }
  ]
}
```
> `securityType`: STOCK | ETF 등  
> `koreanMarketDetail`: 국내 종목만 존재, 미국 종목은 `null`

---

### GET /api/v1/stocks/{symbol}/warnings
매수 유의사항 조회

**응답**
```json
{
  "result": [
    { "warningType": "OVERHEATED", "exchange": "KRX", "startDate": "2026-03-20", "endDate": "2026-03-27" },
    { "warningType": "VI_STATIC",  "exchange": "KRX", "startDate": "2026-03-26", "endDate": null }
  ]
}
```
> `warningType`: LIQUIDATION_TRADING | OVERHEATED | INVESTMENT_WARNING | INVESTMENT_RISK | VI_STATIC | VI_DYNAMIC | VI_STATIC_AND_DYNAMIC | STOCK_WARRANTS  
> 유의사항 없으면 `result: []`

---

## 4. 시장 정보

### GET /api/v1/exchange-rate
환율 조회 (KRW ↔ USD, 1분 갱신, 참고용)

| 파라미터 | 필수 | 설명 |
|----------|------|------|
| baseCurrency | O | 기준 통화 (`KRW` \| `USD`) |
| quoteCurrency | O | 상대 통화 (`KRW` \| `USD`) |
| dateTime | - | 특정 시각 환율 (ISO 8601) |

**응답**
```json
{
  "result": {
    "baseCurrency": "USD", "quoteCurrency": "KRW",
    "rate": "1380.5", "midRate": "1375",
    "basisPoint": "40", "rateChangeType": "UP",
    "validFrom": "2026-03-25T09:30:00+09:00",
    "validUntil": "2026-03-25T09:31:00+09:00"
  }
}
```

---

### GET /api/v1/market-calendar/KR
국내 장 운영 정보 (전일/당일/익일 3영업일, KST 기준)

| 파라미터 | 필수 | 설명 |
|----------|------|------|
| date | - | 기준일 (YYYY-MM-DD). 미지정 시 오늘 |

**응답 구조**
```json
{
  "result": {
    "today": {
      "date": "2026-03-25",
      "integrated": {
        "preMarket":     { "startTime": "2026-03-25T08:00:00+09:00", "singlePriceAuctionStartTime": "2026-03-25T08:50:00+09:00", "endTime": "2026-03-25T09:00:00+09:00" },
        "regularMarket": { "startTime": "2026-03-25T09:00:00+09:00", "singlePriceAuctionStartTime": "2026-03-25T15:20:00+09:00", "endTime": "2026-03-25T15:30:00+09:00" },
        "afterMarket":   { "startTime": "2026-03-25T15:30:00+09:00", "singlePriceAuctionEndTime": "2026-03-25T15:40:00+09:00",   "endTime": "2026-03-25T20:00:00+09:00" }
      }
    },
    "previousBusinessDay": { ... },
    "nextBusinessDay": { ... }
  }
}
```
> 휴장일이면 `integrated: null`  
> 부분 휴장이면 해당 세션만 `null`

---

### GET /api/v1/market-calendar/US
미국 장 운영 정보

| 파라미터 | 필수 | 설명 |
|----------|------|------|
| date | - | 기준일 (미국 현지 날짜, YYYY-MM-DD) |

**응답 세션**: `dayMarket` | `preMarket` | `regularMarket` | `afterMarket`

---

## 5. 계좌

### GET /api/v1/accounts
계좌 목록 조회

**응답**
```json
{
  "result": [
    { "accountNo": "string", "accountSeq": "string", "accountType": "BROKERAGE" }
  ]
}
```
> 해지·휴면 계좌 제외, 계좌 없으면 `[]`  
> `accountSeq`를 이후 `X-Tossinvest-Account` 헤더에 사용

---

## 6. 자산

### GET /api/v1/holdings
보유 주식 조회 (국내 KR + 미국 US, 해외 옵션·채권 제외)

| 파라미터 | 필수 | 설명 |
|----------|------|------|
| symbol | - | 특정 종목만 조회 |

**응답**
```json
{
  "result": {
    "totalPurchaseAmount": { "krw": "1000000", "usd": "700" },
    "marketValue":         { "krw": "1050000", "usd": "735" },
    "profitLoss":          { "amount": { "krw": "50000", "usd": "35" }, "rate": "5.00" },
    "dailyProfitLoss":     { "amount": { "krw": "10000", "usd": "7" },  "rate": "0.96" },
    "items": [
      {
        "symbol": "005930", "name": "삼성전자",
        "marketCountry": "KR", "currency": "KRW",
        "quantity": "10", "lastPrice": "70000", "averagePurchasePrice": "65000",
        "marketValue":     { "krw": "700000" },
        "profitLoss":      { "amount": { "krw": "50000" }, "rate": "7.69" },
        "dailyProfitLoss": { "amount": { "krw": "5000" },  "rate": "0.72" },
        "cost": { "commission": "350", "tax": "0" }
      }
    ]
  }
}
```

---

## 7. 주문 정보 (사전 조회)

### GET /api/v1/buying-power
매수 가능 금액 조회 (미수 제외 현금 기준)

| 파라미터 | 필수 | 설명 |
|----------|------|------|
| currency | O | `KRW` \| `USD` |

**응답**
```json
{ "result": { "currency": "KRW", "cashBuyingPower": "5000000" } }
```

---

### GET /api/v1/sellable-quantity
판매 가능 수량 조회

| 파라미터 | 필수 | 설명 |
|----------|------|------|
| symbol | O | 종목 심볼 |

**응답**
```json
{ "result": { "sellableQuantity": "100" } }
```
> 미국 주식은 소수점 가능 (예: `"5.5"`)

---

### GET /api/v1/commissions
매매 수수료율 조회

**응답**
```json
{
  "result": [
    { "marketCountry": "KR", "commissionRate": "0.015", "startDate": "2026-01-01", "endDate": "2026-12-31" },
    { "marketCountry": "US", "commissionRate": "0.1",   "startDate": null,         "endDate": "2026-06-30" }
  ]
}
```

---

## 8. 주문

### POST /api/v1/orders
주문 생성

**요청 (수량 기반 — 국내/미국 공통)**
```json
{
  "clientOrderId": "my-order-001",
  "symbol": "005930",
  "side": "BUY",
  "orderType": "LIMIT",
  "timeInForce": "DAY",
  "quantity": "10",
  "price": "70000"
}
```

**요청 (금액 기반 — 미국 정규장만)**
```json
{
  "clientOrderId": "my-order-002",
  "symbol": "AAPL",
  "side": "BUY",
  "orderType": "MARKET",
  "orderAmount": "1000"
}
```

| 필드 | 필수 | 설명 |
|------|------|------|
| clientOrderId | - | 클라이언트 지정 ID (중복 방지) |
| symbol | O | 종목 심볼 |
| side | O | `BUY` \| `SELL` |
| orderType | O | `LIMIT` (지정가) \| `MARKET` (시장가) |
| timeInForce | - | `DAY` (기본) \| `CLS` (미국 지정가 장마감) |
| quantity | O* | 주문 수량. `orderAmount` 없을 때 필수 |
| orderAmount | O* | 주문 금액(USD). 미국 전용, `quantity` 없을 때 필수 |
| price | O* | 주문 가격. `LIMIT`일 때 필수 |

**응답**
```json
{ "result": { "orderId": "string", "clientOrderId": "string" } }
```

---

### POST /api/v1/orders/{orderId}/modify
주문 정정

**요청**
```json
{ "orderType": "LIMIT", "quantity": "15", "price": "71000" }
```

| 필드 | 설명 |
|------|------|
| orderType | `LIMIT` 고정 |
| quantity | KR 주식: 필수 (양의 정수). **US 주식: 전달 불가** |
| price | 변경할 가격 |

**응답**
```json
{ "result": { "orderId": "string" } }
```

**주요 에러 코드**

| 코드 | 상황 |
|------|------|
| `already-filled` | 이미 체결 |
| `already-canceled` | 이미 취소 |
| `already-modified` | 이미 정정됨 |
| `already-processing` | 처리 중 (retryAfterSeconds 확인) |
| `modify-restricted` | 정정 불가 주문 |
| `us-modify-quantity-not-supported` | 미국 주식 수량 정정 시도 |
| `max-order-amount-exceeded` | 30억 초과 (KR) |

---

### POST /api/v1/orders/{orderId}/cancel
주문 취소

**요청**: 본문 불필요 (빈 `{}` 또는 생략)

**응답**
```json
{ "result": { "orderId": "string" } }
```

**주요 에러 코드**

| 코드 | 상황 |
|------|------|
| `already-filled` | 이미 체결 |
| `already-canceled` | 이미 취소 |
| `already-processing` | 처리 중 |
| `cancel-restricted` | 취소 불가 주문 |

---

## 9. 주문 조회

### GET /api/v1/orders
주문 목록 조회

| 파라미터 | 필수 | 설명 |
|----------|------|------|
| status | O | `OPEN` (미체결 전량 반환) \| `CLOSED` (페이징) |
| symbol | - | 종목 필터 |
| from | - | 시작일 |
| to | - | 종료일 |
| cursor | - | 페이징 커서 (CLOSED만) |
| limit | - | 1~100, 기본 20 (CLOSED만) |

**응답**
```json
{
  "result": {
    "orders": [
      {
        "orderId": "string", "symbol": "005930",
        "side": "BUY", "orderType": "LIMIT", "timeInForce": "DAY",
        "status": "FILLED",
        "price": "70000", "quantity": "10", "orderAmount": "700000", "currency": "KRW",
        "orderedAt": "string", "canceledAt": null,
        "execution": {
          "filledQuantity": "10", "averageFilledPrice": "70000",
          "filledAmount": "700000", "commission": "350", "tax": "0",
          "filledAt": "string", "settlementDate": "string"
        }
      }
    ],
    "nextCursor": "string",
    "hasNext": false
  }
}
```

---

### GET /api/v1/orders/{orderId}
주문 상세 조회 (모든 상태의 단건)

---

## Rate Limit 그룹

| 그룹 | 해당 API |
|------|----------|
| AUTH | POST /oauth2/token |
| MARKET_DATA | prices, orderbook, trades, price-limits |
| MARKET_DATA_CHART | candles |
| STOCK | stocks, stocks/{symbol}/warnings |
| MARKET_INFO | exchange-rate, market-calendar/KR, market-calendar/US |
| ACCOUNT | accounts |
| ASSET | holdings |
| ORDER_INFO | buying-power, sellable-quantity, commissions |
| ORDER_HISTORY | GET /orders, GET /orders/{orderId} |
| ORDER | POST /orders, modify, cancel |

실제 한도 값은 응답 헤더 확인

---

## 설계 시 주의사항

- **캔들 간격**: `1m`, `1d`만 지원. 5분봉/시간봉 없음
- **웹소켓**: 미지원 (추후 예정). 현재는 폴링 필수
- **종목 정보 폴링**: 영업일 단위 갱신 → 화면·세션 진입 시 1회 캐싱 권장
- **환율**: 참고용 표시 환율 (실제 거래 적용 환율과 다를 수 있음)
- **미국 주식 주문 정정**: 가격만 변경 가능, 수량 변경 불가
- **금액 기반 주문**: 미국 주식 + 정규장만 가능
- **토큰**: 클라이언트당 1개, 재발급 시 이전 토큰 즉시 무효화
- **1억원 이상 주문**: `confirmHighValueOrder` 필드 확인 필요 (에러 코드 `confirm-high-value-required`)
- **국내 최대 주문금액**: 30억원 (KRW)
