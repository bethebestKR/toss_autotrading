# core/

공통 인프라 모듈. 3가지 전략이 모두 이 모듈을 사용한다.

## 파일

- `toss_client.py` — 토스증권 Open API 래퍼
  - `TossClient` 클래스. OAuth2 토큰 자동 발급·갱신 (만료 60초 전 재발급)
  - 429 응답 시 Retry-After 헤더 기준 대기 후 최대 3회 재시도
  - 계좌 필요 API는 `with_account=True` 전달 → `X-Tossinvest-Account` 헤더 자동 추가

- `order_engine.py` — 주문 실행
  - `OrderEngine(client, strategy)` 생성 후 `buy()` / `sell()` / `cancel()` 호출
  - 매수 전 `get_buying_power()`, 매도 전 `get_sellable_quantity()` 자동 체크
  - 주문 결과는 `core/db.py`의 `save_order()`로 자동 저장

- `db.py` — SQLite 연결 및 헬퍼
  - `init_db()` — 앱 시작 시 1회 호출. 테이블 없으면 자동 생성
  - 테이블: `orders` / `holdings` / `performance`
  - DB 경로: `data/trading.db`

## API 주의사항

- 토큰은 클라이언트당 1개. 재발급 시 이전 토큰 즉시 무효화
- 미국 주식 주문 정정은 가격만 가능 (수량 변경 불가)
- 캔들은 `1m` / `1d`만 지원
