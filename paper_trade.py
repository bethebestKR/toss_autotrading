"""
페이퍼 트레이딩 실행 파일.
실제 주문 없이 가상 금액으로 전략1을 테스트한다.
종료(Ctrl+C) 시 data/paper_report_YYYY-MM-DD_HH-MM.json 저장.

--test : 장 시간 체크 우회 (장 외 시간 테스트용). warmup 20틱으로 단축.
"""
import argparse
import os
import sys
import json
import time
import threading
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

from core.db import init_db
from core.toss_client import TossClient
from core.paper_engine import PaperEngine
from core.stock_universe import search
from core import status_server
from main import select_symbols_interactive, _input_listener
from strategies.strategy1_technical import Strategy1
from strategies.stock_scanner import StockScanner
from strategies.trade_analyzer import print_report, suggest_params, generate_report

load_dotenv()

KST = timezone(timedelta(hours=9))


def _ask_cash() -> float:
    print("\n=== 페이퍼 트레이딩 ===")
    raw = input("가상 투자금액 입력 (기본 10,000,000원, 엔터 시 기본값): ").strip()
    if not raw:
        return 10_000_000
    try:
        val = float(raw.replace(",", "").replace("만", "0000").replace("원", ""))
        return val
    except ValueError:
        print("  숫자를 인식할 수 없습니다. 기본값 10,000,000원 사용.")
        return 10_000_000


def _status_printer(strategy: Strategy1, engine: PaperEngine, interval: int = 10):
    """10초마다 현재 상태 출력 (백그라운드 스레드)."""
    while True:
        time.sleep(interval)
        try:
            cur_prices = {}
            if strategy.symbols:
                price_list = strategy.client.get_prices(strategy.symbols)
                cur_prices = {p["symbol"]: float(p["lastPrice"]) for p in price_list}
        except Exception:
            pass

        report = engine.get_report(cur_prices)
        now = datetime.now(KST).strftime("%H:%M:%S")

        lines = [
            f"\n[{now}] ── 페이퍼 트레이딩 현황 ──",
            f"  잔액:      {report['final_cash']:>15,.0f} 원",
            f"  실현 손익: {report['total_pnl']:>+15,.0f} 원  ({report['total_return_pct']:+.2f}%)",
            f"  거래 횟수: {report['total_trades']}회  승률 {report['win_rate_pct']:.1f}%",
        ]
        if report["open_positions"]:
            lines.append("  보유 포지션:")
            for p in report["open_positions"]:
                lines.append(f"    {p['symbol']:8s}  {p['quantity']}주  미실현 {p['upnl']:+,.0f}원 ({p['upnl_pct']:+.2f}%)")
        print("\n".join(lines))


def _save_report(engine: PaperEngine, strategy: Strategy1) -> str:
    try:
        price_list = strategy.client.get_prices(strategy.symbols)
        cur_prices = {p["symbol"]: float(p["lastPrice"]) for p in price_list}
    except Exception:
        cur_prices = {}

    report = engine.get_report(cur_prices)
    report["symbols"] = strategy.symbols
    report["run_date"] = datetime.now(KST).strftime("%Y-%m-%d")
    report["run_end"]  = datetime.now(KST).isoformat()

    os.makedirs("data", exist_ok=True)
    filename = f"data/paper_report_{datetime.now(KST).strftime('%Y-%m-%d_%H-%M')}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return filename


def _print_final(engine: PaperEngine, strategy: Strategy1):
    try:
        price_list = strategy.client.get_prices(strategy.symbols)
        cur_prices = {p["symbol"]: float(p["lastPrice"]) for p in price_list}
    except Exception:
        cur_prices = {}

    r = engine.get_report(cur_prices)

    print("\n" + "="*50)
    print("  페이퍼 트레이딩 최종 결과")
    print("="*50)
    print(f"  종목:      {', '.join(strategy.symbols)}")
    print(f"  초기 자금: {r['initial_cash']:>15,.0f} 원")
    print(f"  최종 잔액: {r['final_cash']:>15,.0f} 원")
    print(f"  실현 손익: {r['total_pnl']:>+15,.0f} 원  ({r['total_return_pct']:+.2f}%)")
    print(f"  거래 횟수: {r['total_trades']}회  (승 {r['wins']} / 패 {r['losses']}  승률 {r['win_rate_pct']:.1f}%)")
    if r["trade_log"]:
        print("\n  거래 내역:")
        for t in r["trade_log"]:
            sign = "+" if t["pnl"] >= 0 else ""
            print(f"    {t['symbol']:8s}  매수 {t['buy_price']:,.2f} → 매도 {t['sell_price']:,.2f}  {sign}{t['pnl']:,.0f}원 ({sign}{t['pnl_pct']:.2f}%)")
    if r["open_positions"]:
        print("\n  미청산 포지션:")
        for p in r["open_positions"]:
            print(f"    {p['symbol']:8s}  {p['quantity']}주  미실현 {p['upnl']:+,.0f}원 ({p['upnl_pct']:+.2f}%)")
    print("="*50)


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--test", action="store_true", help="장 시간 체크 우회 (장 외 시간 테스트용)")
    parser.add_argument("--duration", type=int, default=0, help="N초 후 자동 종료 (0=무제한)")
    parser.add_argument("--scan", action="store_true", help="스캐너 자동 선별 모드 (종목 입력 생략)")
    parser.add_argument("--cash", type=float, default=0, help="가상 투자금액 (0이면 대화형 입력)")
    args, _ = parser.parse_known_args()

    if args.test:
        import strategies.strategy1_technical as _s1
        import strategies.stock_scanner as _sc
        _s1.is_market_open = lambda *a, **kw: True
        _sc.is_market_open = lambda *a, **kw: True
        print("[TEST MODE] 장 시간 체크 우회 — 항상 장 중으로 처리합니다\n")

    init_db()
    status_server.start(port=8765)
    client = TossClient()

    virtual_cash = args.cash if args.cash > 0 else _ask_cash()
    print(f"\n가상 투자금: {virtual_cash:,.0f}원\n")

    if args.scan:
        symbols, scanner_mode = [], True
        print("스캐너 모드 — 종목 자동 선별")
    else:
        symbols, scanner_mode = select_symbols_interactive()
    print(f"\n대상 종목: {symbols or '(스캐너가 자동 선별)'}")

    # --test: 20초마다 Claude 결정 (기본 60초 단축)
    test_config = {"decision_interval": 20} if args.test else {}
    engine   = PaperEngine(virtual_cash=virtual_cash)
    strategy = Strategy1(client=client, symbols=symbols, engine=engine, config=test_config)

    claude_on = strategy.cfg.get("use_claude", False)
    claude_model = strategy.cfg.get("claude_model", "")
    if claude_on:
        print(f"  [Claude AI] 활성화 — 모델: {claude_model}")
        print(f"  [Claude AI] 매수/매도 신호 발생 시 Claude가 최종 판단합니다")
        print(f"  [Claude AI] 손절(-{strategy.cfg['stop_loss_pct']}%)은 Claude 우회 즉시 실행")
    else:
        print("  [Claude AI] 비활성화 — Python 규칙으로만 매매합니다")

    if scanner_mode:
        scanner_cfg = {"debug": args.test, "scan_interval_sec": 30 if args.test else 180}
        scanner = StockScanner(client=client, strategy=strategy, config=scanner_cfg)
        scanner.start()

    # 백그라운드: 10초마다 상태 출력
    threading.Thread(target=_status_printer, args=(strategy, engine), daemon=True).start()
    # 백그라운드: 실행 중 종목 추가/제거
    threading.Thread(target=_input_listener, args=(strategy,), daemon=True).start()

    deadline = (time.time() + args.duration) if args.duration > 0 else None
    if deadline:
        print(f"\n페이퍼 트레이딩 시작 ({args.duration}초 후 자동 종료)\n")
    else:
        print("\n페이퍼 트레이딩 시작 (Ctrl+C로 종료 및 리포트 저장)\n")
    try:
        while True:
            if deadline and time.time() >= deadline:
                print(f"\n[자동 종료] {args.duration}초 경과")
                break
            strategy.run_once()
            time.sleep(1)
    except KeyboardInterrupt:
        pass

    _print_final(engine, strategy)

    # Phase 3 — 페이퍼 트레이딩 통계 분석
    if engine.trade_log:
        print_report(paper_log=engine.trade_log)
        report = generate_report(paper_log=engine.trade_log)
        sug = suggest_params(report, strategy.cfg)
        if sug:
            print("[파라미터 조정 제안]")
            for k, v in sug.items():
                print(f"  {k}: {v}")

    path = _save_report(engine, strategy)
    print(f"\n리포트 저장됨: {path}")
    print("노션에 올리려면 Claude에게 '노션에 올려줘'라고 하세요.")
    sys.exit(0)


if __name__ == "__main__":
    main()
