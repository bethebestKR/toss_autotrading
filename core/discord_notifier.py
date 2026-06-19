"""
Discord Webhook 알림 모듈.

DISCORD_WEBHOOK_URL 환경변수가 없으면 모든 함수가 무음으로 통과한다.
"""
import os
import time
import threading
import requests

_WEBHOOK_URL: str | None = None
_lock = threading.Lock()
_last_call: float = 0.0
_RATE_LIMIT = 1.0  # Discord: 초당 1건 이상 보내면 429 — 최소 간격(초)


def _get_url() -> str | None:
    global _WEBHOOK_URL
    if _WEBHOOK_URL is None:
        _WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL") or None
    return _WEBHOOK_URL


def _send(embed: dict) -> None:
    url = _get_url()
    if not url:
        return
    with _lock:
        global _last_call
        elapsed = time.time() - _last_call
        if elapsed < _RATE_LIMIT:
            time.sleep(_RATE_LIMIT - elapsed)
        try:
            requests.post(url, json={"embeds": [embed]}, timeout=5)
        except Exception:
            pass
        _last_call = time.time()


def _pnl_color(pnl_pct: float) -> int:
    if pnl_pct >= 0:
        return 0x2ECC71  # green
    return 0xE74C3C      # red


# ── 공개 API ──────────────────────────────────────────────────────────────────

def notify_buy(symbol: str, price: float, qty: int,
               stop_loss_pct: float, take_profit_pct: float) -> None:
    sl_price = round(price * (1 - stop_loss_pct / 100), 2)
    tp_price = round(price * (1 + take_profit_pct / 100), 2)
    _send({
        "title": f"📈 매수 — {symbol}",
        "color": 0x3498DB,
        "fields": [
            {"name": "체결가",  "value": f"{price:,.2f}", "inline": True},
            {"name": "수량",    "value": str(qty),         "inline": True},
            {"name": "손절가",  "value": f"{sl_price:,.2f} (-{stop_loss_pct:.1f}%)",  "inline": True},
            {"name": "익절가",  "value": f"{tp_price:,.2f} (+{take_profit_pct:.1f}%)", "inline": True},
        ],
    })


def notify_sell(symbol: str, price: float, pnl_pct: float, reason: str) -> None:
    sign = "+" if pnl_pct >= 0 else ""
    _send({
        "title": f"{'📉' if pnl_pct < 0 else '💰'} 매도 — {symbol}",
        "color": _pnl_color(pnl_pct),
        "fields": [
            {"name": "체결가",  "value": f"{price:,.2f}",            "inline": True},
            {"name": "손익",    "value": f"{sign}{pnl_pct:.2f}%",    "inline": True},
            {"name": "사유",    "value": reason,                      "inline": False},
        ],
    })


def notify_emergency(reason: str) -> None:
    _send({
        "title": "🚨 비상 정지 — 전 포지션 청산",
        "color": 0xFF0000,
        "fields": [
            {"name": "사유", "value": reason, "inline": False},
        ],
    })


def notify_status(positions: dict, pnl_summary: dict) -> None:
    """5분마다 현황 요약. positions = {symbol: {buy_price, current_price, change_pct}}"""
    realized   = pnl_summary.get("realized",   0)
    unrealized = pnl_summary.get("unrealized", 0)
    total      = pnl_summary.get("total",      0)
    balance    = pnl_summary.get("balance")

    pos_lines = []
    for sym, p in positions.items():
        chg = p.get("change_pct", 0.0)
        sign = "+" if chg >= 0 else ""
        pos_lines.append(f"**{sym}** {sign}{chg:.2f}%")

    fields = []
    if pos_lines:
        fields.append({"name": "보유 포지션", "value": "\n".join(pos_lines), "inline": False})
    fields += [
        {"name": "실현 손익",   "value": f"{realized:+,.0f}",   "inline": True},
        {"name": "미실현 손익", "value": f"{unrealized:+,.0f}", "inline": True},
        {"name": "합계",        "value": f"{total:+,.0f}",      "inline": True},
    ]
    if balance is not None:
        fields.append({"name": "잔고 (페이퍼)", "value": f"{balance:,.0f}", "inline": True})

    _send({
        "title": "📊 현황 요약",
        "color": _pnl_color(total),
        "fields": fields,
    })
