# docs/

## API 레퍼런스 파일

- `toss_api_reference.md` — 정리된 레퍼런스. 엔드포인트, 요청/응답 예시, 에러 코드
- `../openapi.json` — 원문 스펙. 위 파일에 없는 세부 스키마나 엣지 케이스는 여기서 확인

## API 핵심 제약

- 캔들: `1m`, `1d`만 지원 (5분봉·시간봉 없음)
- 웹소켓 미지원 → 폴링으로 가격 조회
- 재무제표 미제공 → 전략 2·3은 dart-fss / yfinance 별도 사용
- Base URL: `https://openapi.tossinvest.com`
