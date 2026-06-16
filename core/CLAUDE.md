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
  - `get_recent_orders(limit)` — 최근 주문 내역 반환 (dashboard용)

- `status_server.py` — 대시보드용 HTTP 상태 서버
  - `start(port=8765)` — 백그라운드 스레드로 HTTP 서버 기동 (main.py에서 1회 호출)
  - `update(data)` — 전략이 매 틱마다 현재 상태(포지션·신호·최근거래)를 갱신
  - `GET /status` → JSON 반환. CORS 허용(dashboard.html이 file://에서 직접 fetch 가능)

- `stock_universe.py` — 종목 검색 (한글명 → 코드 변환)
  - `search(query)` — 한글명·영문명·종목코드 통합 검색, 최대 10건 반환
  - 국내: KRX에서 KOSPI/KOSDAQ 전종목 다운로드 → `data/kr_stocks.csv` 캐시 (60초 TTL 없음, 파일 있으면 재사용)
  - 미국: `_US_STOCKS` 정적 매핑 (~90종목). 목록에 없는 미국 티커 패턴 입력 시 `US (미확인)`으로 fallback
  - `update_kr_stocks()` — KRX 강제 재다운로드 (실행 중 `krx` 입력 시 호출)

- `paper_engine.py` — 페이퍼 트레이딩 엔진 (OrderEngine과 동일 인터페이스)
  - `PaperEngine(virtual_cash, strategy)` — 가상 현금으로 매수/매도 시뮬레이션
  - `buy()` / `sell()` — `current_price` 파라미터로 체결가 계산. 실제 API 호출 없음
  - `get_report(current_prices)` — 총 손익, 승률, 미실현 손익, 거래 내역 반환
  - Strategy1의 `engine=` 파라미터에 주입해서 사용

## API 주의사항

- 토큰은 클라이언트당 1개. 재발급 시 이전 토큰 즉시 무효화
- 미국 주식 주문 정정은 가격만 가능 (수량 변경 불가)
- 캔들은 `1m` / `1d`만 지원
