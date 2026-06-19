# strategies/

3가지 매매 전략. 각 전략은 `core/order_engine.py`의 `OrderEngine`으로 주문을 실행한다.
**전략 1**: 토스 API만 사용 (캔들·호가·체결 데이터).
**전략 2·3**: 재무 데이터는 `core/financial_data.py` 경유 (KR: DART API / US: yfinance).

## 전략 1 — Claude AI 직접 판단 (`strategy1_technical.py`) ✅ Phase 1~4 완료

- 목적: 1분봉 캔들 데이터를 Claude Sonnet이 직접 보고 매수/매도 종목·시점 결정
- 매 1초: `get_prices()`로 현재가 폴링 → 보유 포지션 손절/이상감지 체크
- 매 60초(기본): 최대 10종목의 1분봉 30개를 병렬 수집 → Claude에 일괄 판단 요청
- Claude가 BUY/SELL/HOLD + 근거 + 확신도 반환 → confidence ≥ 0.6이면 실행
- 손절(-2%) / 급락(5%) / 슬리피지: Claude 우회 — Python 즉시 처리 (안전망)
- 거래 종료 시: Claude가 결과 분석 → `data/claude_strategy.md`에 규칙 누적 (자가학습)
- 대상: 국내(숫자 코드) + 미국(알파벳 티커) 동시 지원

### Claude AI가 하는 역할

| 상황 | 주기 | Claude에게 전달하는 것 | Claude 결정 |
|------|------|----------------------|------------|
| 정기 배치 판단 | 60초마다 | 최대 10종목 × 1분봉 30개 OHLCV + 전략 규칙 | BUY/SELL/HOLD + 근거 + 확신도 |
| 거래 결과 분석 | 거래 종료 시 | 매수가·매도가·수익률·매수 시점 캔들 스냅샷 | 새 전략 규칙 1건 추출 → 파일 저장 |
| 손절(-2%) | **Python이 직접 처리** | Claude에 묻지 않음 | 즉시 강제 청산 |
| 급락(5%) / 슬리피지 | **Python이 직접 처리** | Claude에 묻지 않음 | 비상 정지 → 전 포지션 청산 |

### 비동기 구조 (ThreadPoolExecutor)

- Claude API 호출은 `ThreadPoolExecutor(max_workers=6)`로 백그라운드 실행
- 폴링 루프(1초)를 **절대 막지 않는다**
- `_decision_future` — 배치 판단 Future (완료 시 `_check_decision_future()`에서 처리)
- 캔들 수집도 내부 `ThreadPoolExecutor`로 10종목 병렬 호출

### 내부 구조 (`Strategy1` 클래스)

- `self._positions` — 보유 포지션 `{symbol: {order_id, buy_price, quantity, ticks_since_buy, candle_snapshot}}`
- `self._prev_prices` — 전 틱 가격 (급락 감지용)
- `self._emergency_stop` — True이면 run_once()에서 전 포지션 즉시 청산 후 리턴
- `self._executor` — ThreadPoolExecutor (Claude API 비동기 호출)
- `self._decision_future` — 배치 판단 Future
- `self._decision_tick` — 마지막 배치 판단 후 경과 틱 수
- `run_once()` — 1초마다 호출. 비상정지 → 현재가 조회 → `_check_decision_future()` → 포지션 스톱로스 → 60초마다 배치 제출
- `_fetch_and_decide(symbols)` — executor에서 실행. 캔들 병렬 수집 + Claude 호출 → (decisions, snapshots) 반환
- `_check_decision_future(price_map)` — 완료된 Future 처리. BUY→`_do_buy`, SELL→`_do_sell`
- `_check_position(symbol, price)` — 이상감지 + 손절 체크 (매 틱)
- `_do_buy(symbol, price, qty_str, candle_snapshot)` — 매수 실행 + 포지션 등록
- `_do_sell(symbol, price, reason)` — 매도 실행 + `_analyze_and_save()` 비동기 제출
- `_analyze_and_save(...)` — 거래 결과 Claude 분석 → `claude_strategy.md` 규칙 추가
- `_calc_quantity(symbol, price)` — 매수가능금액 × max_position_pct / 종목 수 → 동적 수량
- `_check_anomaly(...)` — 급락(단일 틱 -5%) / 슬리피지(매수 후 5틱 내 -1%) 이상 감지
- `_liquidate_all()` — 비상정지 시 전 포지션 시장가 청산
- `_update_status(price_map)` — `core.status_server.update()`로 대시보드 상태 갱신

### DEFAULT_CONFIG 주요 키

| 키 | 기본값 | 설명 |
|----|--------|------|
| `max_position_pct` | 0.20 | 종목당 최대 배분 비율 |
| `stop_loss_pct` | 2.0 | 손절 임계값 (%) — Claude 우회 |
| `take_profit_pct` | 4.0 | 익절 임계값 (%) — 참고용 |
| `crash_pct` | 5.0 | 단일 틱 급락 감지 (%) |
| `slippage_pct` | 1.0 | 매수 직후 슬리피지 감지 (%) |
| `slippage_ticks` | 5 | 슬리피지 감시 구간 (틱) |
| `use_claude` | True | False 시 Claude 호출 안 함 |
| `claude_model` | `claude-sonnet-4-6` | Claude 모델 (Sonnet) |
| `claude_min_confidence` | 0.6 | 이 미만이면 HOLD로 처리 |
| `decision_interval` | 60 | Claude 배치 판단 주기 (초) |
| `max_symbols` | 10 | 배치당 최대 종목 수 |

### 환경 설정

`.env` 파일에 `ANTHROPIC_API_KEY=sk-ant-...` 추가 필요.
없으면 시작 시 경고 출력 + `use_claude` 자동 False 전환.

### 자가 학습 전략 파일

`data/claude_strategy.md` — **20건 거래가 버퍼에 쌓이면** Claude가 일괄 분석 → 규칙 1건 추출·누적.
다음 배치 판단 시 system prompt에 포함되어 과거 학습 반영.
버퍼 크기: `batch_learn_size` config 키 (기본 20).

> **TODO (데이터 충분히 쌓인 후 처리)**: `claude_strategy.md`가 길어질수록 Claude 호출 토큰이 증가하고
> `cache_control: ephemeral` 캐시가 파일 변경마다 무효화된다.
> 대응 방안: 규칙 수 상한(예: 섹션당 30건) 초과 시 Claude가 기존 규칙 중 신뢰도 낮은 것을 제거·통합하는
> "규칙 정리 배치" 실행. 또는 규칙 파일을 요약 버전(top-N)과 전체 버전으로 분리.
> 실거래 데이터가 충분히 쌓인 이후 구현 예정.

구조:
```
## 매수 규칙 (BUY)   — [B001][신뢰도: 높음] ...
## 매도 규칙 (SELL)  — [S001] ...
## 회피 패턴 (AVOID) — [A001] ...
```

---

## `core/claude_trader.py` — Claude AI 판단 모듈

- Lazy-init: `ANTHROPIC_API_KEY` 없으면 import 시점에 오류 안 남
- `load_strategy_rules()` — `data/claude_strategy.md` 읽기 (없으면 템플릿 생성)
- `append_strategy_rule(category, rule_text)` — BUY/SELL/AVOID 섹션에 규칙 추가
- `fmt_candles(symbol, candle_data)` — 토스 API 캔들 dict → Claude용 텍스트 (최근 30봉)
- `ask_trade_decision(candles_by_symbol, strategy_rules, model)` → `list[{symbol, action, reason, confidence}]`
- `ask_analyze_trade(symbol, buy_price, sell_price, pnl_pct, exit_reason, candle_snapshot, strategy_rules, model)` → `(category, rule_text) | None`
- 캔들 필드명: `openPrice` / `highPrice` / `lowPrice` / `closePrice` / `volume` / `timestamp`

---

## Phase 2 보조 모듈 — `stock_scanner.py` ✅

- `StockScanner(client, strategy, config)` — 3분 주기 백그라운드 스캔
- 유니버스: `_KR_UNIVERSE` (KOSPI 상위 20) + `_US_UNIVERSE` (미국 주요 30)
- 스코어링 (0~4점): 모멘텀 + 변동성 + 거래량 급증 + 매수잔량 → 2점 이상이면 편입
- `_check_volume_surge`, `_check_orderbook_bias` — stock_scanner.py 내부 함수 (strategy1과 분리)
- `start()` — 백그라운드 스레드 시작, `stop()` — 정지
- watchlist 변경은 `core/db.py`의 `watchlist`, `watchlist_log` 테이블에 기록
- `main.py` 또는 `paper_trade.py` 실행 후 `scan` 입력 시 활성화

---

## Phase 3 보조 모듈 — `trade_analyzer.py` ✅

- `generate_report(strategy, days, paper_log)` — 승률·손익비·RSI별 통계 dict 반환
- `print_report(...)` — 콘솔 포맷 출력
- `suggest_params(report, current_config)` — 파라미터 조정 제안 dict 반환
- 실행 중 명령어: `report [일수]`, `suggest`
- 페이퍼 트레이딩 종료 시 자동 실행

---

## 전략 2 — 가치 분석 중장기 (`strategy2_fundamental.py`) ✅ 구현 완료

- 목적: DART/yfinance 재무 데이터 → Claude 가치 평가 → 상위 N종목 매수 → 2주~3개월 보유
- 데이터: `core/financial_data.py`의 `get_financials_batch()`로 KR/US 동시 수집
- KR: dart-fss corp_code 조회 + DART REST API `fnlttSinglAcntAll` (연결>개별 우선)
- US: yfinance `income_stmt`, `balance_sheet`, `info`
- 분석 지표: 매출성장률, 영업이익률, 순이익률, ROE, 부채비율, PER, PBR
- Claude 출력: symbol, action, target_pct, stop_pct, hold_weeks, score, reason (JSON 배열)
- 포지션 모니터링: `run_monitor_once()` — 목표(+15%)/손절(-7%) 체크
- 필요 환경변수: `DART_API_KEY` (.env에 추가 필요)

### `Strategy2` 클래스 주요 메서드

| 메서드 | 설명 |
|--------|------|
| `analyze_universe(symbols)` | 재무 수집 → Claude 분석 → 추천 목록 반환 |
| `execute_buy(rec, price)` | 추천 항목 매수 실행 (사용자 확인 후 호출) |
| `run_monitor_once()` | 보유 포지션 목표가/손절 체크 |
| `print_status()` | 보유 현황 콘솔 출력 |

### DEFAULT_CONFIG

| 키 | 기본값 | 설명 |
|----|--------|------|
| `target_profit_pct` | 15.0 | 목표 수익률 (%) |
| `stop_loss_pct` | 7.0 | 손절 기준 (%) |
| `max_positions` | 5 | 동시 최대 보유 종목 수 |
| `max_position_pct` | 0.20 | 종목당 최대 자금 비율 |
| `financial_cache_days` | 7 | 재무 데이터 캐시 TTL (일) |
| `top_n` | 3 | Claude 추천 최대 종목 수 |

---

## `core/financial_data.py` — 재무 데이터 수집 모듈 ✅

- `get_financials(symbol, cache_days=7)` → dict | None
- `get_financials_batch(symbols, cache_days=7)` → {symbol: dict}
- `fmt_financials(data)` → Claude 프롬프트용 텍스트
- 캐시: `data/trading.db`의 `financial_cache` 테이블

출력 표준 필드:
`symbol, name, market, currency, revenue, revenue_prev, revenue_growth,
operating_income, net_income, total_equity, total_assets, total_liabilities,
operating_margin, net_margin, roe, debt_ratio, per, pbr, market_cap,
fiscal_year, as_of, source`

---

## 전략 3 — 퀀트팩터 장기 (`strategy3_quant.py`) 🔜

- 목적: 팩터 복합 점수로 상위 N종목 선별, 분기 리밸런싱
- 모멘텀: 토스 API 일봉 캔들 6~12개월 수익률
- Value/Quality: `core/financial_data.py`로 자동 수집 (strategy2와 공유)
