/andrej-karpathy-skills:karpathy-guidelines

# 토스 자동매매 프로젝트

국내(KOSPI/KOSDAQ) + 미국(NYSE/NASDAQ) 자동매매. 로컬 우선, 추후 서버 배포.
언어: Python / DB: SQLite / 스케줄러: APScheduler / 가상환경: `.venv/`

## 현재 상태 및 할 일

`ROADMAP.md` 참고 — 완료된 작업, 다음 할 일, 각 작업의 목적이 정리되어 있다.

## 폴더 구조

- `core/` — API 클라이언트, 주문 엔진, DB (각 CLAUDE.md 참고)
- `strategies/` — 3가지 매매 전략 (각 CLAUDE.md 참고)
- `docs/` — API 레퍼런스 (각 CLAUDE.md 참고)
- `data/` — SQLite DB 파일 (trading.db), KRX 종목 캐시 (kr_stocks.csv), 페이퍼 리포트 JSON
- `main.py` — 실거래 진입점. 실행 전 한글 종목 선택, 1초 폴링
- `paper_trade.py` — 페이퍼 트레이딩 진입점. 가상 금액 입력 → 종목 선택 → 시뮬레이션. Ctrl+C 시 `data/paper_report_YYYY-MM-DD_HH-MM.json` 저장
- `dashboard.html` — 실시간 대시보드. 브라우저에서 직접 열기. `localhost:8765/status` 1초 폴링 → 포지션·신호·최근거래 표시

## 작업 완료 보고 (필수)

**모든 작업이 완료될 때마다** Notion MCP 도구를 사용해 **날짜별 페이지 하나**에 내용을 누적한다.

- **parent page_id**: `3815c6f2c23d805faa2fef8713a67829`
- **페이지 제목**: `YYYY-MM-DD` (오늘 날짜만, 작업명 없음)

### 절차

1. `mcp__claude_ai_Notion__notion-fetch`로 부모 페이지(`3815c6f2c23d805faa2fef8713a67829`)를 조회해 오늘 날짜(`YYYY-MM-DD`) 페이지가 이미 있는지 확인
2. **없으면** `mcp__claude_ai_Notion__notion-create-pages`로 제목 `YYYY-MM-DD` 페이지 신규 생성 후 내용 작성
3. **있으면** `mcp__claude_ai_Notion__notion-update-page`(`command: insert_content`, `position: end`)로 기존 페이지 끝에 내용 추가

추가할 내용 형식:
```
---
## <작업 제목 한 줄 요약>

### 작업 요약
<무엇을 구현/수정했는지 2~5줄>

### 변경 파일
- `경로/파일명` — 변경 내용 한 줄

### 결과 / 검증
<테스트 결과, 실행 확인, 에러 없음 등>
```

> 작업이 중단되거나 진행 중인 경우에는 보고하지 않는다. 명확히 완료된 작업에만 작성한다.

## Git Hooks

`.git/hooks/pre-push` — push 직전 자동 실행되는 스크립트.

- `scripts/update_readme.py`를 호출해 README.md의 동적 섹션(마지막 업데이트 시각, 총 커밋 수, 마지막 커밋 메시지) 갱신
- README가 변경됐으면 `chore: README 자동 업데이트` 커밋을 자동 생성한 뒤 push 진행
- `.git/hooks/`는 git 추적 대상이 아님 — clone 후 새 환경 세팅 시 훅을 다시 복사하고 `chmod +x` 해야 한다

훅을 수동으로 다시 설치할 경우:
```bash
cp scripts/pre-push-hook .git/hooks/pre-push  # 훅 파일을 scripts/에 백업해두는 경우
chmod +x .git/hooks/pre-push
```

> README의 동적 섹션은 `<!-- DYNAMIC:xxx --> ... <!-- /DYNAMIC -->` 패턴으로 표시돼 있다. 직접 수정하지 말 것 — push 시 덮어씌워진다.

## GitHub 푸시 규칙

- **명시적으로 요청할 때만** push한다. 작업 완료 후 자동으로 push하지 않는다.
- push 요청 시, 마지막 push 이후 완료된 작업들을 `git log`로 파악해 커밋 메시지에 정리해서 올린다.
- 커밋 author 이메일: `vtr1844@naver.com` / 계정: `bethebestKR`
- remote: `https://github.com/bethebestKR/toss_autotrading.git`
