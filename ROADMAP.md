# 작업 로드맵

세션이 초기화돼도 이 파일을 보면 현재 상태와 다음 할 일을 바로 파악할 수 있다.

---

## ✅ 완료

| 작업 | 목적 |
|------|------|
| 프로젝트 폴더 구조 생성 | 코드 배치 기준 확립 |
| `core/toss_client.py` | 토스 API 전 엔드포인트 래퍼. 토큰 자동갱신, 429 retry |
| `core/db.py` | 주문·보유·수익률 SQLite 저장 |
| `core/order_engine.py` | 전략 → 실제 주문 실행. 매수가능금액/판매가능수량 사전 체크 |
| `.venv` + 패키지 설치 | 가상환경 격리, 의존성 고정 |
| API 연결 테스트 (`main.py`) | 계좌 조회 정상 동작 확인 ✓ |
| CLAUDE.md 폴더별 분리 | 세션 토큰 절약 |

---

## 🔜 다음 할 일 (순서대로)

### 1. 전략 1 — 기술적 단타 (`strategies/strategy1_technical.py`) ← 실행 중

**최종 목표**: 사용자 개입 없이 Claude가 종목을 선별하고, Python이 자동매매하며, 거래 데이터로 지속 학습·개선.

---

#### Phase 1 — Claude AI 실시간 판단 자동매매 ✅ 완료
**목적**: 사용자가 종목을 입력하면 Claude AI가 기술적 지표를 보고 매수/매도를 판단.

- [x] 장 시간 체크 (국내/미국 `market_calendar` 활용)
- [x] 캔들 데이터 수집 및 pandas-ta 지표 계산 (EMA5/EMA20 + RSI14)
- [x] 골든크로스+RSI 신호 → Claude AI에게 매수 판단 요청 → BUY면 실행
- [x] 손절(-2%): Claude 우회 — 즉시 강제 청산 (안전망)
- [x] Claude 호출은 비동기(ThreadPoolExecutor) — 폴링 루프(1초) 블로킹 없음
- [x] 포지션 사이징: 매수가능금액 × `max_position_pct` / 종목 수 → 동적 수량 계산
- [x] 비상 정지: 단일 틱 급락(5%) / 슬리피지(5틱 내 -1%) 감지 → 전 포지션 청산
- [ ] 실거래 데이터 DB 축적 및 수익률 확인 (장 중 실행 필요)

---

#### Phase 4 — Claude AI 직접 판단 아키텍처 전환 ✅ 완료
**목적**: Python이 사전 필터링 후 Claude에게 승인 받는 구조 → Claude가 원시 캔들 데이터를 직접 보고 종목·시점을 판단. 거래 결과를 자가학습해 전략 파일에 누적.

- [x] `core/claude_trader.py` 전면 재작성
  - `ask_trade_decision(candles_by_symbol, strategy_rules)` — 10종목 1분봉 → 일괄 BUY/SELL/HOLD
  - `ask_analyze_trade(...)` — 거래 결과 분석 → 규칙 추출
  - `load_strategy_rules()` / `append_strategy_rule(category, rule)` — 전략 파일 관리
  - `fmt_candles(symbol, data)` — 토스 API 캔들 → Claude용 텍스트
- [x] `strategies/strategy1_technical.py` 리팩토링
  - EMA/RSI/크로스 신호 로직 제거 (pandas-ta 의존성 제거)
  - 60초마다 10종목 캔들 병렬 수집 → Claude Sonnet 일괄 판단 (비동기)
  - 거래 종료 시 `_analyze_and_save()` 비동기 제출 → 전략 파일 업데이트
  - 스톱로스·급락·슬리피지는 Python 직접 처리 유지
- [x] `data/claude_strategy.md` — 자가학습 전략 규칙 파일 (BUY/SELL/AVOID 섹션)
- [x] `strategies/stock_scanner.py` — strategy1 의존성 제거 (`_check_volume_surge` 등 내부화)
- [x] `paper_trade.py` — scan 모드 지원 추가, `--test`/`--duration` 옵션 추가
- [ ] 미장 실거래 데이터로 학습 규칙 누적 검증

---

#### Phase 2 — Claude 종목 선별 자동화 ✅ 완료
**목적**: 사용자가 종목을 직접 입력하지 않아도 됨. `strategies/stock_scanner.py`

- [x] 스캔 유니버스: KOSPI 시총 상위 20 + US 주요 30종목 (`_KR_UNIVERSE`, `_US_UNIVERSE`)
- [x] 3분 주기 분봉 스캔: 모멘텀(0.3%↑) + 변동성(1m 캔들 범위) + 거래량 급증 + 매수잔량 (0~4점)
- [x] 조건 충족 시 `watchlist` DB 테이블 편입 → `strategy.symbols` 실시간 반영
- [x] 모멘텀 소멸 시 즉시 이탈 (보유 중이면 청산 후 제거)
- [x] 편입/이탈 사유·점수·지표값 `watchlist_log` DB 기록
- [x] `scan_interval_sec`, `max_watchlist` 파라미터화
- [x] 포지션 사이징 연계: Phase 1 `_calc_quantity()` 공유

**실행**: `python main.py` → 종목 입력 프롬프트에서 `scan` 입력

---

#### Phase 3 — 데이터 피드백 & 학습 ✅ 완료
**목적**: 과거 매매 데이터를 바탕으로 전략 파라미터를 개선. `strategies/trade_analyzer.py`

- [x] 거래 결과 자동 태깅: 매수 시 `signal_type`, `entry_rsi`, `entry_ema_gap`, `volume_ratio`, `bid_ratio` DB 저장
- [x] 분석 리포트: 승률·손익비·평균 보유시간·RSI 구간별 성과 집계 (`print_report()`)
- [x] 파라미터 조정 제안: 승률/손익비/RSI 구간 분석 기반 규칙 제안 (`suggest_params()`)
- [x] 페이퍼 트레이딩 종료 시 자동 분석 출력
- [x] 실행 중 `report [일수]`, `suggest` 명령어로 즉시 조회
- [ ] 백테스트 연계: 제안 파라미터를 페이퍼로 검증 (추후)

---

### 2. 전략 2 — 가치 분석 중장기 (`strategies/strategy2_fundamental.py`)
**목적**: 기업이 공개한 재무 문서(사업보고서, 분기보고서 등)를 직접 입력받아 분석하고,
가치 있는 종목을 추천한다. 추천된 종목은 토스 API로 2주 이상 보유.

**방식 (외부 API 없음, 토스 API만 사용)**:
- 사용자가 기업 공시 문서(PDF, 텍스트 등)를 직접 제공
- Claude가 매출성장률, 영업이익률, 순이익, ROE, 부채비율 등을 읽고 가치 평가
- 투자 가치 있는 종목 추천 → 사용자 승인 후 토스 API로 매수
- 매수 후 목표가/손절가 기준으로 모니터링

구현 항목:
- [ ] 문서 입력 인터페이스 (파일 경로 또는 텍스트 붙여넣기)
- [ ] 재무 지표 추출 및 종목 평가 로직
- [ ] 추천 종목 출력 → 사용자 확인 후 주문
- [ ] 보유 종목 목표가/손절가 모니터링

---

### 3. 전략 3 — 퀀트팩터 장기 (`strategies/strategy3_quant.py`)
**목적**: 토스 API 시세 데이터만으로 계산 가능한 팩터(모멘텀, 변동성 등)와
사용자가 제공하는 재무 문서를 결합해 상위 N종목을 선별하고 분기 리밸런싱.

**방식 (외부 API 없음, 토스 API만 사용)**:
- 모멘텀: 토스 API 일봉 캔들로 6~12개월 수익률 계산
- Value/Quality: 사용자가 제공한 재무 문서에서 PER, ROE 등 추출
- 복합 점수 계산 → 상위 N종목 보유, 분기 리밸런싱

구현 항목:
- [ ] 토스 API 일봉 기반 모멘텀 팩터 계산
- [ ] 문서 기반 Value/Quality 팩터 입력
- [ ] 복합 점수 산출 및 종목 선별
- [ ] 분기 첫 영업일 자동 리밸런싱

---

### 4. 스케줄러 + 수익률 비교 (`main.py` 완성)
**목적**: 3전략을 각자 스케줄에 따라 자동 실행하고 성과를 비교.

구현 항목:
- [ ] APScheduler 전략별 job 등록
  - 전략1: 장중 1분 간격
  - 전략2·3: 사용자 트리거 (문서 제공 시)
- [ ] 전략별 누적 수익률 비교 출력

---

### 5. (추후) 서버 배포
**목적**: 로컬에서 검증된 시스템을 서버에 올려 24시간 무중단 운영.

- [ ] PostgreSQL 전환 (SQLite → PostgreSQL)
- [ ] 서버 환경 설정 (Docker 또는 systemd)
- [ ] 로그 모니터링

---

## 참고

- 토스 API 레퍼런스: `docs/toss_api_reference.md`
- 원문 스펙: `openapi.json`
- 가상환경 활성화: `source .venv/bin/activate`
- 실행: `python main.py`
