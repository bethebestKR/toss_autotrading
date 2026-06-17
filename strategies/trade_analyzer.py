"""
Phase 3 — 데이터 피드백 & 학습 (TradeAnalyzer)

DB에 쌓인 매매 내역을 분석해 성과 통계와 파라미터 조정 제안을 출력한다.
generate_report() — 통계 출력
suggest_params()   — 현재 config 기준 조정 제안 반환
"""
from __future__ import annotations

from core import db


# ── 유틸 ──────────────────────────────────────────────────────────────────────

def _pair_trades(orders: list[dict]) -> list[dict]:
    """
    BUY/SELL 주문을 symbol 단위로 시간순 매칭.
    한 종목에 BUY → SELL → BUY → SELL ... 순으로 페어링.
    """
    # symbol → pending BUY 스택
    pending: dict[str, list[dict]] = {}
    paired: list[dict] = []

    for o in sorted(orders, key=lambda x: x["created_at"]):
        sym = o["symbol"]
        if o["side"] == "BUY":
            pending.setdefault(sym, []).append(o)
        elif o["side"] == "SELL" and pending.get(sym):
            buy = pending[sym].pop(0)
            try:
                buy_price  = float(buy["price"] or 0)
                sell_price = float(o["price"]   or 0)
                qty        = int(buy["quantity"] or 1)
                pnl        = (sell_price - buy_price) * qty
                hold_sec   = _sec_diff(buy["created_at"], o["created_at"])
            except (TypeError, ValueError):
                continue
            if buy_price <= 0 or sell_price <= 0:
                continue
            paired.append({
                "symbol":       sym,
                "buy_time":     buy["created_at"],
                "sell_time":    o["created_at"],
                "buy_price":    buy_price,
                "sell_price":   sell_price,
                "quantity":     qty,
                "pnl":          round(pnl, 2),
                "pnl_pct":      round((sell_price - buy_price) / buy_price * 100, 2),
                "hold_sec":     hold_sec,
                "signal_type":  buy.get("signal_type"),
                "entry_rsi":    buy.get("entry_rsi"),
                "entry_ema_gap": buy.get("entry_ema_gap"),
                "volume_ratio": buy.get("volume_ratio"),
                "bid_ratio":    buy.get("bid_ratio"),
            })

    return paired


def _sec_diff(t1: str, t2: str) -> int:
    from datetime import datetime
    fmt = "%Y-%m-%d %H:%M:%S"
    try:
        return int((datetime.strptime(t2, fmt) - datetime.strptime(t1, fmt)).total_seconds())
    except Exception:
        return 0


def _fmt_sec(sec: int) -> str:
    if sec < 60:
        return f"{sec}초"
    if sec < 3600:
        return f"{sec // 60}분 {sec % 60}초"
    return f"{sec // 3600}시간 {(sec % 3600) // 60}분"


# ── 핵심 API ──────────────────────────────────────────────────────────────────

def generate_report(strategy: str = "strategy1", days: int = 30, paper_log: list[dict] = None) -> dict:
    """
    DB(실거래) 또는 paper_log(페이퍼)에서 통계 계산 후 반환.
    paper_log: PaperEngine.trade_log 형식 [{"symbol","pnl","pnl_pct","buy_price","sell_price","quantity","buy_time","sell_time"}, ...]
    """
    if paper_log is not None:
        trades = [
            {**t, "signal_type": None, "entry_rsi": None,
             "entry_ema_gap": None, "volume_ratio": None, "bid_ratio": None,
             "hold_sec": _sec_diff(t["buy_time"], t["sell_time"])}
            for t in paper_log
        ]
    else:
        orders = db.get_orders_for_analysis(strategy, days)
        trades = _pair_trades(orders)

    if not trades:
        return {"trades": 0}

    wins   = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]

    gross_profit = sum(t["pnl"] for t in wins)
    gross_loss   = abs(sum(t["pnl"] for t in losses))
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else float("inf")

    avg_hold  = int(sum(t["hold_sec"] for t in trades) / len(trades))
    avg_pnl   = round(sum(t["pnl"] for t in trades) / len(trades), 2)
    avg_win   = round(sum(t["pnl"] for t in wins) / len(wins), 2) if wins else 0
    avg_loss  = round(sum(t["pnl"] for t in losses) / len(losses), 2) if losses else 0

    # RSI 구간별 승률
    rsi_stats: dict[str, dict] = {}
    for t in trades:
        rsi = t.get("entry_rsi")
        if rsi is None:
            bucket = "N/A"
        elif rsi < 50:
            bucket = "RSI<50"
        elif rsi < 60:
            bucket = "50≤RSI<60"
        elif rsi < 65:
            bucket = "60≤RSI<65"
        else:
            bucket = "RSI≥65"
        s = rsi_stats.setdefault(bucket, {"win": 0, "loss": 0, "pnl": 0.0})
        if t["pnl"] > 0:
            s["win"] += 1
        else:
            s["loss"] += 1
        s["pnl"] += t["pnl"]

    return {
        "trades":         len(trades),
        "wins":           len(wins),
        "losses":         len(losses),
        "win_rate_pct":   round(len(wins) / len(trades) * 100, 1),
        "total_pnl":      round(sum(t["pnl"] for t in trades), 2),
        "avg_pnl":        avg_pnl,
        "avg_win":        avg_win,
        "avg_loss":       avg_loss,
        "profit_factor":  profit_factor,
        "avg_hold_sec":   avg_hold,
        "rsi_stats":      rsi_stats,
        "trades_detail":  trades,
    }


def suggest_params(report: dict, current_config: dict) -> dict[str, str]:
    """
    분석 결과 기반 파라미터 조정 제안 반환.
    {파라미터명: "현재값 → 제안값 (근거)"} 형식.
    """
    if report.get("trades", 0) < 5:
        return {"note": "거래 건수 부족 (최소 5건 필요)"}

    suggestions: dict[str, str] = {}
    wr   = report["win_rate_pct"]
    pf   = report["profit_factor"]
    rsi  = report.get("rsi_stats", {})
    avg_hold = report.get("avg_hold_sec", 0)

    # 승률 < 40%: RSI 임계값 낮추거나 워밍업 확대
    if wr < 40:
        cur = current_config.get("warmup_ticks", 60)
        suggestions["warmup_ticks"] = f"{cur} → {cur + 20}  (승률 {wr}% — 신호 노이즈 감소)"

    # 이익/손실 비율: 손실이 크면 손절폭 축소
    if pf < 1.0 and report["avg_loss"] < 0:
        cur = current_config.get("stop_loss_pct", 2.0)
        new = round(cur * 0.75, 1)
        suggestions["stop_loss_pct"] = f"{cur} → {new}  (손익비 {pf} — 손절 강화)"

    # 익절 목표 낮추기: 평균 보유 30초 미만이면 신호가 너무 빠름
    if avg_hold < 30 and report["avg_pnl"] < 0:
        cur = current_config.get("take_profit_pct", 4.0)
        new = round(cur * 0.75, 1)
        suggestions["take_profit_pct"] = f"{cur} → {new}  (평균 보유 {avg_hold}초 — 익절 조기화)"

    # RSI 구간별: 60≤RSI<65 구간이 손실이면 RSI 진입 기준 낮추기
    high_rsi = rsi.get("60≤RSI<65", {})
    if high_rsi and high_rsi.get("pnl", 0) < 0 and (high_rsi["win"] + high_rsi["loss"]) >= 3:
        suggestions["rsi_buy_threshold"] = "65 → 60  (RSI 60~65 진입 구간 손실 패턴)"

    if not suggestions:
        suggestions["note"] = f"현재 파라미터 적절 (승률 {wr}%, 손익비 {pf})"

    return suggestions


def print_report(strategy: str = "strategy1", days: int = 30, paper_log: list[dict] = None):
    """분석 결과 콘솔 출력."""
    r = generate_report(strategy, days, paper_log)

    if r.get("trades", 0) == 0:
        print(f"\n[분석] 최근 {days}일 거래 내역 없음")
        return

    print(f"\n{'=' * 50}")
    print(f"  전략1 매매 분석 — 최근 {days}일")
    print(f"{'=' * 50}")
    print(f"  총 거래:    {r['trades']}건  (승 {r['wins']} / 패 {r['losses']})")
    print(f"  승률:       {r['win_rate_pct']}%")
    print(f"  누적 손익:  {r['total_pnl']:+,.0f}원")
    print(f"  평균 손익:  {r['avg_pnl']:+,.0f}원  (평균 승 {r['avg_win']:+,.0f} / 평균 패 {r['avg_loss']:+,.0f})")
    print(f"  손익비:     {r['profit_factor']}")
    print(f"  평균 보유:  {_fmt_sec(r['avg_hold_sec'])}")

    if r["rsi_stats"]:
        print(f"\n  [RSI 구간별]")
        for bucket, s in sorted(r["rsi_stats"].items()):
            total = s["win"] + s["loss"]
            wr = round(s["win"] / total * 100) if total else 0
            print(f"    {bucket:15s}  {total}건  승률 {wr}%  손익 {s['pnl']:+,.0f}원")

    print(f"{'=' * 50}\n")
