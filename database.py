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
                subcategory TEXT DEFAULT 'boshqa',
                note TEXT,
                source TEXT DEFAULT 'text',
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_date
            ON expenses (user_id, created_at)
        """)
        # Eski bazalarda subcategory ustuni bo'lmasligi mumkin — mavjud
        # bo'lmasa qo'shib qo'yamiz (migratsiya).
        cols = [row["name"] for row in conn.execute("PRAGMA table_info(expenses)")]
        if "subcategory" not in cols:
            conn.execute(
                "ALTER TABLE expenses ADD COLUMN subcategory TEXT DEFAULT 'boshqa'"
            )

        conn.execute("""
            CREATE TABLE IF NOT EXISTS custom_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                subcategory TEXT NOT NULL,
                keywords TEXT NOT NULL,
                UNIQUE(user_id, category, subcategory)
            )
        """)


def add_custom_category(user_id: int, category: str, subcategory: str, keywords: list):
    kw_str = ",".join(k.strip().lower() for k in keywords if k.strip())
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO custom_categories (user_id, category, subcategory, keywords) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id, category, subcategory) DO UPDATE SET keywords = excluded.keywords",
            (user_id, category.strip(), subcategory.strip(), kw_str),
        )


def get_custom_categories(user_id: int):
    """[(category, subcategory, [keywords...]), ...] qaytaradi."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT category, subcategory, keywords FROM custom_categories WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        return [
            (r["category"], r["subcategory"], r["keywords"].split(","))
            for r in rows
        ]


def delete_custom_category(user_id: int, category: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM custom_categories WHERE user_id = ? AND category = ?",
            (user_id, category.strip()),
        )
        return cur.rowcount > 0


def rename_custom_category(user_id: int, old_name: str, new_name: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE custom_categories SET category = ? WHERE user_id = ? AND category = ?",
            (new_name.strip(), user_id, old_name.strip()),
        )
        if cur.rowcount > 0:
            # Avval shu nom bilan kiritilgan xarajatlarni ham yangilaymiz
            conn.execute(
                "UPDATE expenses SET category = ? WHERE user_id = ? AND category = ?",
                (new_name.strip(), user_id, old_name.strip()),
            )
            return True
        return False


def get_custom_categories_grouped(user_id: int):
    """{category: [subcategory, ...]} ko'rinishida qaytaradi (tugmalar uchun)."""
    rows = get_custom_categories(user_id)
    grouped = {}
    for cat, sub, _ in rows:
        grouped.setdefault(cat, [])
        if sub not in grouped[cat]:
            grouped[cat].append(sub)
    return grouped


def add_expense(user_id: int, amount: float, category: str, subcategory: str, note: str, source: str = "text"):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, subcategory, note, source, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, amount, category, subcategory, note, source, datetime.now().isoformat()),
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


def get_summary_by_subcategory(user_id: int, start: datetime, end: datetime):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT category, subcategory, SUM(amount) as total, COUNT(*) as cnt "
            "FROM expenses WHERE user_id = ? AND created_at >= ? AND created_at < ? "
            "GROUP BY category, subcategory ORDER BY category, total DESC",
            (user_id, start.isoformat(), end.isoformat()),
        ).fetchall()
        return rows
