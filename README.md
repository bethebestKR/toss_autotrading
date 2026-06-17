# 토스증권 AI 자동매매 시스템

> Claude AI가 직접 캔들을 읽고 매매 판단 · 자가학습까지 수행하는 국내/미국 주식 자동매매 봇

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python)
![Claude](https://img.shields.io/badge/Claude-Sonnet_4.6-blueviolet?logo=anthropic)
![SQLite](https://img.shields.io/badge/DB-SQLite-lightgrey?logo=sqlite)
![License](https://img.shields.io/badge/license-private-red)

| 항목 | 값 |
|------|-----|
| 마지막 업데이트 | <!-- DYNAMIC:last_updated -->2026-06-18 01:22 KST<!-- /DYNAMIC --> |
| 총 커밋 수 | <!-- DYNAMIC:commit_count -->4<!-- /DYNAMIC --> |
| 마지막 커밋 | <!-- DYNAMIC:last_commit -->docs: 포트폴리오 README 추가 및 push 시 자동 업데이트 훅 설정<!-- /DYNAMIC --> |

---

## 프로젝트 개요

토스증권 Open API를 활용한 완전 자동매매 시스템.
사람이 종목을 고르거나 매매 시점을 결정할 필요 없이, **Claude AI가 실시간 캔들 데이터를 직접 분석해 매수·매도를 결정**한다.
거래가 끝날 때마다 결과를 분석해 스스로 전략 규칙을 누적(자가학습)한다.

---

## 구현된 기능 (포트폴리오)

### Phase 1 — Claude AI 실시간 매매 판단 ✅

> `strategies/strategy1_technical.py` · `core/claude_trader.py`

- 매 60초마다 최대 10종목의 1분봉(30개) 데이터를 병렬 수집
- **Claude Sonnet**에 종목별 OHLCV를 일괄 전달 → BUY / SELL / HOLD + 확신도 반환
- 확신도(confidence) ≥ 0.6인 신호만 실행
- 손절(-2%), 급락(-5%), 슬리피지(-1% / 5틱) — Claude 우회, Python 즉시 처리
- `ThreadPoolExecutor`로 Claude 호출을 비동기 처리 → 1초 폴링 루프 비블로킹
- 포지션 사이징: `매수가능금액 × max_position_pct / 종목 수` 동적 계산

### Phase 2 — 자율 종목 선별 (StockScanner) ✅

> `strategies/stock_scanner.py`

- 유니버스: KOSPI 상위 20종목 + 미국 주요 30종목
- 3분 주기 백그라운드 스캔 (메인 루프와 독립 스레드)
- 편입 조건 (0~4점 스코어링):
  - 단기 모멘텀 +0.3% 이상
  - 1분봉 변동성 범위
  - 최근 거래량 급증 비율
  - 매수잔량 우세 여부
- 2점 이상 → `watchlist` DB 편입 → 전략의 종목 리스트 실시간 반영
- 모멘텀 소멸 시 즉시 이탈 (보유 중이면 청산 후 제거)
- 편입/이탈 사유·점수 `watchlist_log` 테이블에 전량 기록
- 실행: `python main.py` → 종목 프롬프트에 `scan` 입력

### Phase 3 — 거래 데이터 피드백 & 학습 (TradeAnalyzer) ✅

> `strategies/trade_analyzer.py`

- DB에 쌓인 매매 내역 자동 분석
- 출력 지표: 승률, 손익비, 평균 보유 시간, 신호 유형별/RSI 구간별 성과
- 파라미터 조정 제안: 승률·손익비 분석 기반 규칙 자동 제안
- 페이퍼 트레이딩 종료 시 자동 실행
- 실행 중 `report [일수]` / `suggest` 명령어로 즉시 조회

### Phase 4 — Claude 자가학습 전략 파일 ✅

> `core/claude_trader.py` · `data/claude_strategy.md`

- 거래 종료마다 매수가·매도가·수익률·캔들 스냅샷을 Claude에 전달
- Claude가 규칙 1건 추출 → `data/claude_strategy.md`에 누적
- 규칙 구조: `BUY / SELL / AVOID` 섹션, `[B001][신뢰도: 높음]` 형식
- 버퍼 20건 초과 시 일괄 분석 배치 실행
- 다음 배치 판단 시 규칙 파일을 system prompt에 포함 → 과거 학습 자동 반영

### 페이퍼 트레이딩 ✅

> `paper_trade.py` · `core/paper_engine.py`

- 가상 현금 입력 → 종목 선택(직접 입력 또는 `scan` 모드) → 시뮬레이션
- 실제 API 호출 없이 `OrderEngine`과 동일한 인터페이스
- Ctrl+C 종료 시 `data/paper_report_YYYY-MM-DD_HH-MM.json` 자동 저장
- 종료 시 TradeAnalyzer 자동 실행 → 승률·손익비 콘솔 출력
- `--test` / `--duration` 옵션으로 CI/자동화 지원

### 실시간 대시보드 ✅

> `dashboard.html` · `core/status_server.py`

- 브라우저에서 직접 열기 (`file://`)
- `localhost:8765/status` 1초 폴링 → 포지션·신호·최근 거래 실시간 표시
- CORS 허용, 백그라운드 HTTP 서버 자동 기동

### 인프라 ✅

> `core/`

| 모듈 | 역할 |
|------|------|
| `toss_client.py` | 토스증권 Open API 전 엔드포인트 래퍼. OAuth2 자동 갱신, 429 retry |
| `order_engine.py` | 매수/매도/취소 실행. 매수가능금액·판매가능수량 사전 체크 |
| `db.py` | SQLite 스키마 관리. orders·holdings·watchlist·watchlist_log 테이블 |
| `paper_engine.py` | 가상 매매 엔진 (OrderEngine 동일 인터페이스) |
| `status_server.py` | 대시보드용 HTTP 상태 서버 |
| `stock_universe.py` | 한글명 → 종목코드 변환. KRX 전종목 캐시 |

---

## 아키텍처

```
main.py / paper_trade.py
    │
    ├─ Strategy1 (1초 폴링)
    │       ├─ TossClient ──→ 현재가·캔들·호가 조회
    │       ├─ ClaudeTrader ──→ BUY/SELL/HOLD 판단 (비동기)
    │       │       └─ data/claude_strategy.md (자가학습 규칙)
    │       ├─ OrderEngine / PaperEngine ──→ 주문 실행
    │       └─ DB (SQLite) ──→ orders·holdings 기록
    │
    ├─ StockScanner (3분 주기, 독립 스레드)
    │       └─ watchlist DB ──→ Strategy1 symbols 실시간 반영
    │
    ├─ TradeAnalyzer (종료 시 / 명령어)
    │       └─ DB 집계 → 승률·손익비·파라미터 제안
    │
    └─ StatusServer (백그라운드)
            └─ dashboard.html ──→ 1초 폴링 실시간 UI
```

---

## 기술 스택

| 분류 | 사용 기술 |
|------|----------|
| 언어 | Python 3.11+ |
| AI | Anthropic Claude Sonnet 4.6 |
| 증권 API | 토스증권 Open API (OAuth2) |
| DB | SQLite (via `sqlite3`) |
| 비동기 | `ThreadPoolExecutor` |
| 스케줄링 | 폴링 루프 + `time.sleep` |
| 대시보드 | 순수 HTML/JS (`fetch` 폴링) |

---

## 실행 방법

```bash
# 가상환경 활성화
source .venv/bin/activate

# 실거래
python main.py

# 페이퍼 트레이딩
python paper_trade.py

# 대시보드: 브라우저에서 dashboard.html 열기
```

`.env` 파일에 아래 키 필요:
```
TOSS_APP_KEY=...
TOSS_APP_SECRET=...
ANTHROPIC_API_KEY=sk-ant-...
```

---

## 로드맵

| 전략 | 상태 |
|------|------|
| 전략 1 — Claude AI 기술적 단타 (Phase 1~4) | ✅ 완료 |
| 전략 2 — 가치 분석 중장기 (재무문서 기반) | 🔜 예정 |
| 전략 3 — 퀀트팩터 장기 (모멘텀·밸류 복합) | 🔜 예정 |
| APScheduler 3전략 통합 스케줄링 | 🔜 예정 |
| 서버 배포 (Docker / PostgreSQL) | 🔜 추후 |
