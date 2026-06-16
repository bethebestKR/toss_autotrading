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
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy    TEXT NOT NULL,
                order_id    TEXT UNIQUE,
                symbol      TEXT NOT NULL,
                side        TEXT NOT NULL,
                order_type  TEXT NOT NULL,
                quantity    TEXT,
                price       TEXT,
                status      TEXT,
                created_at  TEXT DEFAULT (datetime('now', 'localtime'))
            );

            CREATE TABLE IF NOT EXISTS holdings (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy              TEXT NOT NULL,
                symbol                TEXT NOT NULL,
                quantity              TEXT,
                average_purchase_price TEXT,
                recorded_at           TEXT DEFAULT (datetime('now', 'localtime'))
            );

            CREATE TABLE IF NOT EXISTS performance (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy    TEXT NOT NULL,
                date        TEXT NOT NULL,
                return_rate TEXT,
                UNIQUE(strategy, date)
            );
        """)


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


def get_performance(strategy: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT date, return_rate FROM performance WHERE strategy=? ORDER BY date",
            (strategy,),
        ).fetchall()
    return [dict(r) for r in rows]
