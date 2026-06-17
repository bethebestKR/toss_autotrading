import json
import sqlite3
import os
from datetime import date

DB_PATH = os.path.join(os.path.dirname(__file__), "../data/trading.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS orders (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy     TEXT NOT NULL,
                order_id     TEXT UNIQUE,
                symbol       TEXT NOT NULL,
                side         TEXT NOT NULL,
                order_type   TEXT NOT NULL,
                quantity     TEXT,
                price        TEXT,
                status       TEXT,
                created_at   TEXT DEFAULT (datetime('now', 'localtime'))
            );

            CREATE TABLE IF NOT EXISTS holdings (
                id                     INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy               TEXT NOT NULL,
                symbol                 TEXT NOT NULL,
                quantity               TEXT,
                average_purchase_price TEXT,
                recorded_at            TEXT DEFAULT (datetime('now', 'localtime'))
            );

            CREATE TABLE IF NOT EXISTS performance (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy    TEXT NOT NULL,
                date        TEXT NOT NULL,
                return_rate TEXT,
                UNIQUE(strategy, date)
            );

            CREATE TABLE IF NOT EXISTS watchlist (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol    TEXT NOT NULL UNIQUE,
                added_at  TEXT DEFAULT (datetime('now', 'localtime')),
                reason    TEXT,
                score     REAL,
                indicators TEXT
            );

            CREATE TABLE IF NOT EXISTS watchlist_log (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol    TEXT NOT NULL,
                action    TEXT NOT NULL,
                reason    TEXT,
                score     REAL,
                indicators TEXT,
                logged_at TEXT DEFAULT (datetime('now', 'localtime'))
            );
        """)
        # Phase 3 — 트레이드 신호 태깅 컬럼 (없는 경우에만 추가)
        for col in [
            "signal_type TEXT",
            "entry_rsi REAL",
            "entry_ema_gap REAL",
            "volume_ratio REAL",
            "bid_ratio REAL",
        ]:
            try:
                conn.execute(f"ALTER TABLE orders ADD COLUMN {col}")
            except Exception:
                pass


# ── 주문 ──────────────────────────────────────────────────────────────────────

def save_order(strategy: str, order_id: str, symbol: str, side: str, order_type: str, quantity: str = None, price: str = None, status: str = "OPEN"):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO orders (strategy, order_id, symbol, side, order_type, quantity, price, status) VALUES (?,?,?,?,?,?,?,?)",
            (strategy, order_id, symbol, side, order_type, quantity, price, status),
        )


def update_order_status(order_id: str, status: str):
    with get_conn() as conn:
        conn.execute("UPDATE orders SET status=? WHERE order_id=?", (status, order_id))


def save_performance(strategy: str, return_rate: float, day: str = None):
    day = day or date.today().isoformat()
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO performance (strategy, date, return_rate) VALUES (?,?,?)",
            (strategy, day, str(return_rate)),
        )


def update_order_signal(
    order_id: str,
    signal_type: str = None,
    entry_rsi: float = None,
    entry_ema_gap: float = None,
    volume_ratio: float = None,
    bid_ratio: float = None,
):
    """Phase 3 — 매수 주문에 진입 신호 데이터 태깅."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE orders SET signal_type=?, entry_rsi=?, entry_ema_gap=?, volume_ratio=?, bid_ratio=? WHERE order_id=?",
            (signal_type, entry_rsi, entry_ema_gap, volume_ratio, bid_ratio, order_id),
        )


def get_recent_orders(limit: int = 10) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT created_at, symbol, side, price, quantity, status FROM orders ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_orders_for_analysis(strategy: str, days: int = 30) -> list[dict]:
    """Phase 3 — 분석용 전체 주문 내역 반환 (신호 태그 포함)."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT id, order_id, symbol, side, quantity, price, status,
                      created_at, signal_type, entry_rsi, entry_ema_gap,
                      volume_ratio, bid_ratio
               FROM orders
               WHERE strategy=?
                 AND created_at >= datetime('now', 'localtime', ? || ' days')
               ORDER BY created_at ASC""",
            (strategy, f"-{days}"),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Watchlist ──────────────────────────────────────────────────────────────────

def add_to_watchlist(symbol: str, reason: str, score: float, indicators: dict = None):
    ind = json.dumps(indicators, ensure_ascii=False) if indicators else None
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO watchlist (symbol, reason, score, indicators) VALUES (?,?,?,?)",
            (symbol, reason, score, ind),
        )
        conn.execute(
            "INSERT INTO watchlist_log (symbol, action, reason, score, indicators) VALUES (?,?,?,?,?)",
            (symbol, "ADD", reason, score, ind),
        )


def remove_from_watchlist(symbol: str, reason: str = None):
    with get_conn() as conn:
        row = conn.execute("SELECT score, indicators FROM watchlist WHERE symbol=?", (symbol,)).fetchone()
        conn.execute("DELETE FROM watchlist WHERE symbol=?", (symbol,))
        if row:
            conn.execute(
                "INSERT INTO watchlist_log (symbol, action, reason, score, indicators) VALUES (?,?,?,?,?)",
                (symbol, "REMOVE", reason, row["score"], row["indicators"]),
            )


def get_watchlist() -> list[str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT symbol FROM watchlist ORDER BY added_at").fetchall()
    return [r["symbol"] for r in rows]


def get_watchlist_log(limit: int = 20) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT logged_at, symbol, action, reason, score FROM watchlist_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_performance(strategy: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT date, return_rate FROM performance WHERE strategy=? ORDER BY date",
            (strategy,),
        ).fetchall()
    return [dict(r) for r in rows]
