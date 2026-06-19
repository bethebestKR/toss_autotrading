/andrej-karpathy-skills:karpathy-guidelines

# 토스 자동매매 프로젝트

국내(KOSPI/KOSDAQ) + 미국(NYSE/NASDAQ) 자동매매. 로컬 우선, 추후 서버 배포.
언어: Python / DB: SQLite / 스케줄러: APScheduler / 가상환경: `.venv/`

## 현재 상태 및 할 일

`ROADMAP.md` 참고 — 완료된 작업, 다음 할 일, 각 작업의 목적이 정리되어 있다.

---

## 폴더 구조

### `core/` — 공통 인프라 (각 모듈 상세는 `core/CLAUDE.md` 참고)

| 파일 | 역할 |
|------|------|
| `toss_client.py` | 토스증권 Open API 래퍼. OAuth2 토큰 자동갱신, 429 retry |
| `order_engine.py` | 실제 주문 실행 (매수가능금액·판매가능수량 사전 체크) |
| `paper_engine.py` | 페이퍼 트레이딩 엔진 (OrderEngine 동일 인터페이스) |
| `db.py` | SQLite 헬퍼. 테이블: orders, holdings, performance, watchlist, watchlist_log, financial_cache |
| `status_server.py` | 대시보드용 HTTP 상태 서버 (port 8765) |
| `stock_universe.py` | 한글명 → 종목코드 변환, KRX 전종목 캐시 |
| `claude_trader.py` | Claude AI 판단 모듈 (캔들 → BUY/SELL/HOLD, 자가학습 규칙 관리) |
| `discord_notifier.py` | 매수·매도·상태·비상정지 Discord 웹훅 알림 |
| `financial_data.py` | KR(DART API) + US(yfinance) 재무 데이터 수집 + SQLite 캐시(TTL 7일) |

### `strategies/` — 매매 전략 (각 전략 상세는 `strategies/CLAUDE.md` 참고)

| 파일 | 역할 | 상태 |
|------|------|------|
| `strategy1_technical.py` | Claude AI 직접 판단, 단타 (1분봉 기반) | ✅ 완료 |
| `stock_scanner.py` | 모멘텀·거래량·호가 스코어링으로 watchlist 자동 관리 | ✅ 완료 |
| `trade_analyzer.py` | 승률·손익비·RSI별 성과 분석, 파라미터 제안 | ✅ 완료 |
| `strategy2_fundamental.py` | 재무 데이터 → Claude 가치 평가 → 중장기 보유 | 🔧 기반 완성, 통합 진행 중 |
| `strategy3_quant.py` | 팩터 복합 점수 → 상위 N종목 분기 리밸런싱 | 🔜 미구현 |

### 기타

| 경로 | 역할 |
|------|------|
| `docs/` | 토스 API 레퍼런스 (`docs/CLAUDE.md` 참고) |
| `data/trading.db` | SQLite DB (주문·보유·수익률·watchlist·재무캐시) |
| `data/kr_stocks.csv` | KRX 전종목 캐시 |
| `data/claude_strategy.md` | 전략1 자가학습 규칙 누적 파일 |
| `data/paper_report_*.json` | 페이퍼 트레이딩 종료 시 자동 저장 리포트 |
| `main.py` | 실거래 진입점. 종목 선택 후 1초 폴링 |
| `paper_trade.py` | 페이퍼 트레이딩 진입점. Ctrl+C 시 리포트 저장 |
| `dashboard.html` | 실시간 대시보드. 브라우저에서 직접 열기 (`localhost:8765/status` 1초 폴링) |

---

## 환경 변수 (`.env`)

| 변수 | 필수 여부 | 설명 |
|------|-----------|------|
| `TOSS_CLIENT_ID` | 필수 | 토스증권 Open API 클라이언트 ID |
| `TOSS_CLIENT_SECRET` | 필수 | 토스증권 Open API 시크릿 |
| `TOSS_ACCOUNT_SEQ` | 필수 | 계좌 식별자 |
| `ANTHROPIC_API_KEY` | 전략1·2 필수 | Claude AI 호출 (없으면 자동 비활성화) |
| `DART_API_KEY` | 전략2·3 필수 | DART 재무 데이터 ([opendart.fss.or.kr](https://opendart.fss.or.kr) 무료 발급) |
| `DISCORD_WEBHOOK_URL` | 선택 | 매매 알림 웹훅 (없으면 알림 건너뜀) |

---

## 작업 완료 보고 (필수)

**모든 작업이 완료될 때마다** Notion MCP 도구를 사용해 **날짜별 페이지 하나**에 내용을 누적한다.

- **parent page_id**: `3815c6f2c23d805faa2fef8713a67829`
- **페이지 제목**: `YYYY-MM-DD` (오늘 날짜만, 작업명 없음)

### 절차

1. `mcp__claude_ai_Notion__notion-fetch`로 부모 페이지(`3815c6f2c23d805faa2fef8713a67829`)를 조회해 오늘 날짜(`YYYY-MM-DD`) 페이지가 이미 있는지 확인
2. **없으면** `mcp__claude_ai_Notion__notion-create-pages`로 제목 `YYYY-MM-DD` 페이지 신규 생성 후 내용 작성
3. **있으면** `mcp__claude_ai_Notion__notion-update-page`(`command: insert_content`, `position: end`)로 기존 페이지 끝에 내용 추가

추가할 내용 형식 (Notion 콜아웃 블록 사용):
```
> [!success] <작업 제목 한 줄 요약>
> 
> **작업 요약**
> <무엇을 구현/수정했는지 2~5줄>
> 
> **변경 파일**
> - `경로/파일명` — 변경 내용 한 줄
> 
> **결과**: <테스트 결과, 실행 확인, 에러 없음 등 한 줄>
```

- 각 작업은 `> [!success]` 콜아웃 하나로 표현한다 (구분선 `---` 없이)
- 작업 간 빈 줄 하나로만 구분
- 콜아웃 내부는 `**굵은 글씨**`로 섹션 제목, 내용은 그 아래에 이어 작성

> 작업이 중단되거나 진행 중인 경우에는 보고하지 않는다. 명확히 완료된 작업에만 작성한다.

---

## Git Hooks

`.git/hooks/pre-push` — push 직전 자동 실행되는 스크립트.

- `scripts/update_readme.py`를 호출해 README.md의 동적 섹션(마지막 업데이트 시각, 총 커밋 수, 마지막 커밋 메시지) 갱신
- README가 변경됐으면 `chore: README 자동 업데이트` 커밋을 자동 생성한 뒤 push 진행
- `.git/hooks/`는 git 추적 대상이 아님 — clone 후 새 환경 세팅 시 훅을 다시 복사하고 `chmod +x` 해야 한다

훅을 수동으로 다시 설치할 경우:
```bash
cp scripts/pre-push-hook .git/hooks/pre-push
chmod +x .git/hooks/pre-push
```

> README의 동적 섹션은 `<!-- DYNAMIC:xxx --> ... <!-- /DYNAMIC -->` 패턴으로 표시돼 있다. 직접 수정하지 말 것 — push 시 덮어씌워진다.

---

## GitHub 푸시 규칙

- **명시적으로 요청할 때만** push한다. 작업 완료 후 자동으로 push하지 않는다.
- push 요청 시, 마지막 push 이후 완료된 작업들을 `git log`로 파악해 커밋 메시지에 정리해서 올린다.
- 커밋 author 이메일: `vtr1844@naver.com` / 계정: `bethebestKR`
- remote: `https://github.com/bethebestKR/toss_autotrading.git`
