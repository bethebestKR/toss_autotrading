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


def select_symbols_interactive() -> list[str]:
    """실행 전 종목 선택 프롬프트."""
    print("\n=== 종목 선택 ===")
    print("한글 이름, 영문 이름, 또는 종목코드 입력 (빈 엔터 → 완료, 'krx' → 국내 종목 업데이트)\n")

    symbols: list[str] = []

    while True:
        try:
            raw = input("종목 입력 > ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not raw:
            break

        if raw.lower() == 'krx':
            update_kr_stocks()
            continue

        if raw.lower() in ('list', '목록'):
            if symbols:
                print(f"  현재 선택: {', '.join(symbols)}")
            else:
                print("  선택된 종목 없음")
            continue

        symbol = _pick_symbol(raw)
        if symbol and symbol not in symbols:
            symbols.append(symbol)
        elif symbol in symbols:
            print(f"  이미 추가된 종목: {symbol}")

    if not symbols:
        # .env 기본값 사용
        symbols = [s.strip() for s in os.getenv("STRATEGY1_SYMBOLS", "005930").split(",")]
        print(f"  입력 없음 — .env 기본값 사용: {symbols}")

    return symbols


def _input_listener(strategy: Strategy1):
    """실행 중 종목 추가/제거 입력 처리 (백그라운드 스레드)."""
    print("\n[실행 중 명령어] add <종목명> | remove <종목명> | list | 엔터 무시\n")
    while True:
        try:
            raw = input().strip()
        except EOFError:
            break

        if not raw:
            continue

        parts = raw.split(maxsplit=1)
        cmd = parts[0].lower()

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

        else:
            print("  명령어: add <종목명> | remove <종목명> | list")


def main():
    init_db()
    status_server.start(port=8765)
    client = TossClient()

    accounts = client.get_accounts()
    print("계좌:", accounts)

    symbols = select_symbols_interactive()
    print(f"\n전략1 대상 종목: {symbols}")

    strategy = Strategy1(client=client, symbols=symbols)

    listener = threading.Thread(target=_input_listener, args=(strategy,), daemon=True)
    listener.start()

    print("전략1 시작 (Ctrl+C로 종료)\n")
    try:
        while True:
            strategy.run_once()
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n종료")
        sys.exit(0)


if __name__ == "__main__":
    main()
