# strategies/

3가지 매매 전략. 각 전략은 `core/order_engine.py`의 `OrderEngine`으로 주문을 실행한다.
**외부 재무 데이터 API(DART, yfinance 등)는 사용하지 않는다. 토스 API만 사용.**

## 전략 1 — 기술적 단타 (`strategy1_technical.py`) ← 현재 개발 중

- 목적: 1초 틱 기반 단기 매매
- 데이터: `get_prices()`로 1초마다 현재가 폴링 → 내부 deque에 누적
- 지표: pandas-ta — EMA5 / EMA20 / RSI14
- 매수 조건: EMA5/EMA20 골든크로스 + RSI < 65
- 매도 조건: 데드크로스 OR RSI > 75 OR 손절(-2%) OR 익절(+4%)
- 워밍업: `warmup_ticks=60` 틱 쌓이기 전까지 신호 무시
- 대상: 국내(숫자 코드) + 미국(알파벳 티커) 동시 지원

### 내부 구조 (`Strategy1` 클래스)

- `self._ticks` — symbol별 가격 deque (maxlen = warmup_ticks + 30)
- `self._positions` — 보유 포지션 `{symbol: {order_id, buy_price}}`
- `self._last_signals` — 마지막 계산된 신호 캐시 (dashboard용)
- `run_once()` — 1초마다 호출. 활성 종목 현재가 일괄 조회 → `_process()` → `_update_status()`
- `_process(symbol, price)` — 틱 누적 + 신호 계산 + 매수/매도 실행. 신호를 `_last_signals`에 저장
- `_update_status(price_map)` — `core.status_server.update()`로 대시보드 상태 갱신. 장 마감 시에도 호출됨

### 모듈 레벨 헬퍼

- `_safe_float(v)` — numpy/pandas 스칼라를 Python float로 변환. NaN은 None 반환 (JSON 직렬화 안전)
- `_calc_signals(prices)` — EMA5/EMA20/RSI14 계산 + 골든크로스/데드크로스 판별
- `_in_session(session, now)` — 단일 세션 dict의 startTime~endTime 범위 체크
- `is_market_open(client, symbol)` — preMarket / regularMarket / afterMarket 세 세션 중 하나라도 해당하면 True (결과 60초 캐시)
  - 미국 (KST): 프리마켓 17:00~22:30 / 정규장 22:30~05:00 / 애프터마켓 05:00~08:50
  - 국내 (KST): 프리마켓 08:00~09:00 / 정규장 09:00~15:30 / 애프터마켓 15:30~20:00

### 대시보드 연동

- `run_once()` 끝에서 항상 `_update_status()` 호출 → `localhost:8765/status` 실시간 갱신
- `main.py`와 `paper_trade.py` 모두 `status_server.start(8765)` 기동 → `dashboard.html`로 확인 가능

## 전략 2 — 가치 분석 중장기 (`strategy2_fundamental.py`)

- 목적: 기업 공시 문서(사업보고서 등) 분석 → 가치 종목 추천 → 2주 이상 보유
- 방식: 사용자가 재무 문서를 직접 제공 → Claude가 분석 → 종목 추천 → 사용자 승인 후 토스 API 매수
- 분석 지표: 매출성장률, 영업이익률, 순이익, ROE, 부채비율
- 외부 API 없음. 문서 입력 + 토스 API만 사용

## 전략 3 — 퀀트팩터 장기 (`strategy3_quant.py`)

- 목적: 팩터 복합 점수로 상위 N종목 선별, 분기 리밸런싱
- 방식:
  - 모멘텀: 토스 API 일봉 캔들로 직접 계산
  - Value/Quality: 사용자가 제공한 재무 문서에서 추출
- 외부 API 없음. 토스 API 시세 + 문서 입력 방식
