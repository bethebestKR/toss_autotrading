import os
import sys
import time
import threading
from dotenv import load_dotenv

from core.db import init_db
from core.toss_client import TossClient
from core.stock_universe import search, update_kr_stocks
from core import status_server
from strategies.strategy1_technical import Strategy1
from strategies.stock_scanner import StockScanner
from strategies.trade_analyzer import print_report, suggest_params, generate_report

load_dotenv()


def _pick_symbol(query: str) -> str | None:
    """검색어로 종목 선택. 단건이면 자동 선택, 복수이면 번호 선택."""
    results = search(query)
    if not results:
        print(f"  ✗ '{query}' 검색 결과 없음")
        return None

    if len(results) == 1:
        r = results[0]
        print(f"  ✓ {r['name']} ({r['symbol']}, {r['market']}) 추가")
        return r['symbol']

    print(f"  검색 결과 {len(results)}건:")
    for i, r in enumerate(results, 1):
        print(f"    [{i}] {r['name']} ({r['symbol']}, {r['market']})")
    print(f"    [0] 취소")
    while True:
        try:
            choice = int(input("  선택 번호: ").strip())
        except (ValueError, EOFError):
            print("  숫자를 입력하세요.")
            continue
        if choice == 0:
            return None
        if 1 <= choice <= len(results):
            r = results[choice - 1]
            print(f"  ✓ {r['name']} ({r['symbol']}, {r['market']}) 추가")
            return r['symbol']
        print(f"  1~{len(results)} 사이 숫자를 입력하세요.")


def select_symbols_interactive() -> tuple[list[str], bool]:
    """실행 전 종목 선택. 빈 엔터면 스캐너 모드 진입 여부 묻기."""
    print("\n=== 종목 선택 ===")
    print("한글 이름·영문명·종목코드 입력 (빈 엔터 → 완료, 'scan' → 스캐너 자동 선별 모드, 'krx' → 국내 종목 업데이트)\n")

    symbols: list[str] = []
    scanner_mode = False

    while True:
        try:
            raw = input("종목 입력 > ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not raw:
            break

        if raw.lower() == 'scan':
            scanner_mode = True
            print("  ✓ 스캐너 모드 활성화 — 장 중 자동으로 종목을 선별합니다")
            break

        if raw.lower() == 'krx':
            update_kr_stocks()
            continue

        if raw.lower() in ('list', '목록'):
            print(f"  현재 선택: {', '.join(symbols) or '없음'}")
            continue

        symbol = _pick_symbol(raw)
        if symbol and symbol not in symbols:
            symbols.append(symbol)
        elif symbol in symbols:
            print(f"  이미 추가된 종목: {symbol}")

    if not symbols and not scanner_mode:
        symbols = [s.strip() for s in os.getenv("STRATEGY1_SYMBOLS", "005930").split(",")]
        print(f"  입력 없음 — .env 기본값 사용: {symbols}")

    return symbols, scanner_mode


def _input_listener(strategy: Strategy1):
    """실행 중 명령어 처리 (백그라운드 스레드)."""
    cmds = "add <종목> | remove <종목> | list | report [일수] | suggest | watchlog | 엔터 무시"
    print(f"\n[실행 중 명령어] {cmds}\n")

    while True:
        try:
            raw = input().strip()
        except EOFError:
            break

        if not raw:
            continue

        parts = raw.split(maxsplit=1)
        cmd   = parts[0].lower()

        if cmd in ('add', '추가') and len(parts) == 2:
            symbol = _pick_symbol(parts[1])
            if symbol:
                if symbol not in strategy.symbols:
                    strategy.symbols.append(symbol)
                    print(f"  → {symbol} 추가됨. 현재: {strategy.symbols}")
                else:
                    print(f"  이미 있음: {symbol}")

        elif cmd in ('remove', '삭제', '제거') and len(parts) == 2:
            results = search(parts[1])
            if results:
                symbol = results[0]['symbol']
                if symbol in strategy.symbols:
                    strategy.symbols.remove(symbol)
                    print(f"  → {symbol} 제거됨. 현재: {strategy.symbols}")
                else:
                    print(f"  목록에 없음: {symbol}")
            else:
                print(f"  종목 없음: {parts[1]}")

        elif cmd in ('list', '목록'):
            print(f"  현재 종목: {strategy.symbols}")

        elif cmd == 'report':
            days = int(parts[1]) if len(parts) == 2 else 30
            print_report("strategy1", days=days)

        elif cmd == 'suggest':
            report = generate_report("strategy1", days=30)
            sug    = suggest_params(report, strategy.cfg)
            print("\n[파라미터 조정 제안]")
            for k, v in sug.items():
                print(f"  {k}: {v}")
            print()

        elif cmd == 'watchlog':
            from core import db as _db
            logs = _db.get_watchlist_log(limit=10)
            print("\n[watchlist 변경 이력]")
            for l in logs:
                print(f"  {l['logged_at']}  {l['action']:6s}  {l['symbol']}  점수 {l['score'] or '-'}  ({l['reason'] or '-'})")
            print()

        elif cmd == 'stop':
            print("  [비상정지 수동 발동]")
            strategy._emergency_stop = True

        else:
            print(f"  명령어: {cmds}")


def main():
    init_db()
    status_server.start(port=8765)
    client = TossClient()

    accounts = client.get_accounts()
    print("계좌:", accounts)

    symbols, scanner_mode = select_symbols_interactive()
    print(f"\n전략1 대상 종목: {symbols or '(스캐너가 자동 선별)'}")

    strategy = Strategy1(client=client, symbols=symbols)

    claude_on = strategy.cfg.get("use_claude", False)
    if claude_on:
        print(f"  [Claude AI] 활성화 — {strategy.cfg.get('claude_model')}")
        print(f"  [Claude AI] 매수/매도 신호 발생 시 Claude가 최종 판단 (손절은 즉시 실행)")
    else:
        print("  [Claude AI] 비활성화 — Python 규칙으로만 매매")

    # Phase 2 — 스캐너 모드
    if scanner_mode:
        scanner = StockScanner(client=client, strategy=strategy)
        scanner.start()

    listener = threading.Thread(target=_input_listener, args=(strategy,), daemon=True)
    listener.start()

    print("전략1 시작 (Ctrl+C로 종료)\n")
    try:
        while True:
            strategy.run_once()
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n종료")
        # Phase 3 — 종료 시 자동 분석 리포트
        print_report("strategy1", days=1)
        sys.exit(0)


if __name__ == "__main__":
    main()
