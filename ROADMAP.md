# 작업 로드맵

세션이 초기화돼도 이 파일을 보면 현재 상태와 다음 할 일을 바로 파악할 수 있다.

---

## ✅ 완료

| 작업 | 목적 |
|------|------|
| 프로젝트 폴더 구조 생성 | 코드 배치 기준 확립 |
| `core/toss_client.py` | 토스 API 전 엔드포인트 래퍼. 토큰 자동갱신, 429 retry |
| `core/db.py` | 주문·보유·수익률·watchlist·재무캐시 SQLite 저장 |
| `core/order_engine.py` | 전략 → 실제 주문 실행. 매수가능금액/판매가능수량 사전 체크 |
| `core/paper_engine.py` | 가상 현금으로 매수/매도 시뮬레이션 (OrderEngine 동일 인터페이스) |
| `core/status_server.py` | 대시보드용 HTTP 상태 서버 (port 8765) |
| `core/stock_universe.py` | 한글명 → 종목코드 변환, KRX 전종목 캐시 |
| `core/claude_trader.py` | Claude AI 판단 모듈. 캔들 → BUY/SELL/HOLD, 거래결과 → 규칙 추출 |
| `core/discord_notifier.py` | 매수·매도·상태·비상정지 Discord 웹훅 알림 |
| `core/financial_data.py` | KR(DART API) + US(yfinance) 재무 데이터 수집, SQLite 캐시(TTL 7일) |
| `.venv` + 패키지 설치 | 가상환경 격리, 의존성 고정 |
| API 연결 테스트 (`main.py`) | 계좌 조회 정상 동작 확인 ✓ |
| CLAUDE.md 폴더별 분리 | 세션 토큰 절약 |
| **전략 1 — 기술적 단타** `strategy1_technical.py` | Claude가 1분봉 직접 판단, 자가학습, 장 마감 강제 청산 |
| **전략 1** — StockScanner `stock_scanner.py` | 모멘텀·거래량·호가 스코어링으로 watchlist 자동 편입·이탈 |
| **전략 1** — TradeAnalyzer `trade_analyzer.py` | 승률·손익비·RSI별 성과 분석, 파라미터 조정 제안 |
| **전략 2** — `financial_data.py` + `strategy2_fundamental.py` 기반 구현 | 재무 데이터 자동 수집 → Claude 가치 평가 → 추천 매수 |

---

## 🔜 다음 할 일 (순서대로)

### 1. 전략 1 — 기술적 단타 (`strategies/strategy1_technical.py`) ✅ 구조 완성

**최종 목표**: 사용자 개입 없이 Claude가 종목을 선별하고, Python이 자동매매하며, 거래 데이터로 지속 학습·개선.

#### Phase 1~4 ✅ 완료

- [x] Claude AI 직접 판단 아키텍처 (캔들 → 일괄 BUY/SELL/HOLD)
- [x] 비동기 배치 결정 (ThreadPoolExecutor, 폴링 루프 비블로킹)
- [x] 동적 손절/익절 (ATR 기반 Claude 제안, Python 즉시 처리)
- [x] 장 마감 N분 전 강제 청산, 장 시작 직후 쿨다운
- [x] 자가학습: 20건 버퍼 → Claude 배치 분석 → `data/claude_strategy.md` 규칙 누적
- [x] 하락장 신뢰도 기준 자동 상향 (+0.15)
- [x] StockScanner — 모멘텀·거래량·호가 4점 스코어링, watchlist 자동 편입/이탈
- [x] TradeAnalyzer — 승률·손익비·보유시간·RSI별 성과 리포트, 파라미터 제안
- [x] Discord 알림 (매수·매도·상태·비상정지)
- [x] 대시보드 (`dashboard.html`, port 8765)

#### 남은 항목

- [ ] 실거래 데이터 장기 축적 → 학습 규칙 품질 검증
- [ ] `claude_strategy.md` 규칙 상한 초과 시 정리 배치 (섹션당 30건 제한)
- [ ] 미국 장 시작 쿨다운 (서머타임 대응)

---

### 2. 전략 2 — 가치 분석 중장기 (`strategies/strategy2_fundamental.py`) 🔧 진행 중

**목적**: 재무 데이터 자동 수집 → Claude 가치 평가 → 상위 N종목 매수 → 2주~3개월 보유.

**방식** (DART API + yfinance):
- KR: `dart-fss`로 corp_code 조회 + DART REST API(`fnlttSinglAcntAll`)로 연간 재무제표 수집
- US: `yfinance`로 income_stmt, balance_sheet, info 수집
- Claude에게 매출성장률·영업이익률·ROE·부채비율·PER·PBR 전달 → 투자 가치 평가
- 추천 종목 매수 → 목표가(+15%) / 손절(-7%) 도달 시 자동 청산

#### 완료된 항목

- [x] `core/financial_data.py` — KR/US 재무 데이터 수집, SQLite 캐시(TTL 7일)
- [x] `core/db.py` — `financial_cache` 테이블 + `get/set_financial_cache()` 헬퍼
- [x] `strategies/strategy2_fundamental.py` — `Strategy2` 클래스 기본 구현
  - `analyze_universe(symbols)` → Claude 분석 → 추천 목록 (JSON)
  - `execute_buy(rec)` → 승인 후 매수 실행
  - `run_monitor_once()` → 목표가/손절 체크
  - 기본 유니버스: KOSPI 대형주 10 + 미국 대형주 10

#### 남은 항목

- [ ] **DART_API_KEY 발급** — [opendart.fss.or.kr](https://opendart.fss.or.kr) 에서 무료 발급 후 `.env`에 입력 (선행 조건)
- [ ] `main.py` / `paper_trade.py`에 `strategy2` 실행 옵션 추가 (예: 종목 입력 시 `fund` 입력)
- [ ] KR 종목 PER/PBR 보완 — 현재가 + DART 주식수 데이터 연산 (현재 `None`)
- [ ] 분석 결과 인터랙티브 흐름 — 추천 목록 출력 → 사용자가 종목 선택 → 매수 실행
- [ ] 포지션 일별 모니터링 자동화 (APScheduler 연계)

---

### 3. 전략 3 — 퀀트팩터 장기 (`strategies/strategy3_quant.py`) 🔜

**목적**: 팩터 복합 점수로 상위 N종목 선별, 분기 리밸런싱.

**방식**:
- 모멘텀: 토스 API 일봉 캔들 6~12개월 수익률 계산
- Value/Quality: `core/financial_data.py`로 자동 수집 (전략2와 공유)
- 복합 점수(모멘텀 + ROE + PER + 영업이익률) → 상위 N종목 보유
- 분기 첫 영업일 자동 리밸런싱

구현 항목:
- [ ] 토스 API 일봉 기반 모멘텀 팩터 계산 (6M, 12M 수익률)
- [ ] 복합 점수 산출 및 종목 선별 (`strategy3_quant.py`)
- [ ] 분기 첫 영업일 자동 리밸런싱 로직
- [ ] `main.py` 통합

---

### 4. 스케줄러 + 수익률 비교 (`main.py` 완성)

**목적**: 3전략을 각자 스케줄에 따라 자동 실행하고 성과를 비교.

구현 항목:
- [ ] APScheduler 전략별 job 등록
  - 전략1: 장중 1초 폴링 + 30초 배치 판단
  - 전략2: 주 1~2회 재무 분석 실행 + 매일 포지션 모니터링
  - 전략3: 분기 첫 영업일 리밸런싱
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
- 실행 (전략1): `python main.py`
- 실행 (페이퍼): `python paper_trade.py`
- DART API 키 발급: [opendart.fss.or.kr](https://opendart.fss.or.kr) → 인증키 신청
