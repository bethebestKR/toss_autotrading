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
- `data/` — SQLite DB 파일 (trading.db)
- `main.py` — 진입점 + APScheduler

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
