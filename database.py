"""
database.py — SQLite orqali xarajatlarni saqlash va o'qish uchun modul.
"""
import sqlite3
from datetime import datetime
from contextlib import contextmanager

DB_PATH = "expenses.db"


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                note TEXT,
                source TEXT DEFAULT 'text',
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_date
            ON expenses (user_id, created_at)
        """)


def add_expense(user_id: int, amount: float, category: str, note: str, source: str = "text"):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, note, source, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, amount, category, note, source, datetime.now().isoformat()),
        )


def delete_last_expense(user_id: int) -> bool:
    """Foydalanuvchining oxirgi yozuvini o'chiradi. Muvaffaqiyatli bo'lsa True qaytaradi."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM expenses WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        if not row:
            return False
        conn.execute("DELETE FROM expenses WHERE id = ?", (row["id"],))
        return True


def get_expenses(user_id: int, start: datetime, end: datetime):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? AND created_at >= ? AND created_at < ? "
            "ORDER BY created_at DESC",
            (user_id, start.isoformat(), end.isoformat()),
        ).fetchall()
        return rows


def get_summary_by_category(user_id: int, start: datetime, end: datetime):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT category, SUM(amount) as total, COUNT(*) as cnt "
            "FROM expenses WHERE user_id = ? AND created_at >= ? AND created_at < ? "
            "GROUP BY category ORDER BY total DESC",
            (user_id, start.isoformat(), end.isoformat()),
        ).fetchall()
        return rows
