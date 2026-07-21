"""
database.py — SQLite orqali xarajat (chiqim) va daromad (kirim)
ma'lumotlarini saqlash va o'qish uchun modul.
"""
import sqlite3
import os
from datetime import datetime
from contextlib import contextmanager

# DB_PATH atrof-muhit o'zgaruvchisi orqali beriladi — Railway'da doimiy
# "Volume" ulanganda shu yerga ko'rsatiladi (masalan /data/expenses.db),
# aks holda joriy papkada saqlanadi (lokal ishga tushirish uchun).
DB_PATH = os.getenv("DB_PATH", "expenses.db")

_db_dir = os.path.dirname(DB_PATH)
if _db_dir:
    os.makedirs(_db_dir, exist_ok=True)

CHIQIM = "chiqim"
KIRIM = "kirim"


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
                kind TEXT DEFAULT 'chiqim',
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_date ON expenses (user_id, created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_kind ON expenses (user_id, kind)")

        # Migratsiyalar — eski bazalarda ustunlar bo'lmasligi mumkin
        cols = [row["name"] for row in conn.execute("PRAGMA table_info(expenses)")]
        if "subcategory" not in cols:
            conn.execute("ALTER TABLE expenses ADD COLUMN subcategory TEXT DEFAULT 'boshqa'")
        if "kind" not in cols:
            conn.execute("ALTER TABLE expenses ADD COLUMN kind TEXT DEFAULT 'chiqim'")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS custom_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                subcategory TEXT NOT NULL,
                keywords TEXT NOT NULL,
                kind TEXT DEFAULT 'chiqim',
                UNIQUE(user_id, category, subcategory, kind)
            )
        """)
        cc_cols = [row["name"] for row in conn.execute("PRAGMA table_info(custom_categories)")]
        if "kind" not in cc_cols:
            conn.execute("ALTER TABLE custom_categories ADD COLUMN kind TEXT DEFAULT 'chiqim'")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                first_seen TEXT NOT NULL
            )
        """)


def register_user(user_id: int, chat_id: int):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users (user_id, chat_id, first_seen) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET chat_id = excluded.chat_id",
            (user_id, chat_id, datetime.now().isoformat()),
        )


def get_all_users():
    """[(user_id, chat_id), ...] — barcha ro'yxatdan o'tgan foydalanuvchilar."""
    with get_conn() as conn:
        rows = conn.execute("SELECT user_id, chat_id FROM users").fetchall()
        return [(r["user_id"], r["chat_id"]) for r in rows]


# ---- Kategoriya boshqaruvi (chiqim va kirim uchun umumiy, kind bilan ajratiladi) ----

def add_custom_category(user_id: int, category: str, subcategory: str, keywords: list, kind: str = CHIQIM):
    kw_str = ",".join(k.strip().lower() for k in keywords if k.strip())
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO custom_categories (user_id, category, subcategory, keywords, kind) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id, category, subcategory, kind) DO UPDATE SET keywords = excluded.keywords",
            (user_id, category.strip(), subcategory.strip(), kw_str, kind),
        )


def get_custom_categories(user_id: int, kind: str = CHIQIM):
    """[(category, subcategory, [keywords...]), ...] qaytaradi."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT category, subcategory, keywords FROM custom_categories WHERE user_id = ? AND kind = ?",
            (user_id, kind),
        ).fetchall()
        return [(r["category"], r["subcategory"], r["keywords"].split(",")) for r in rows]


def delete_custom_category(user_id: int, category: str, kind: str = CHIQIM) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM custom_categories WHERE user_id = ? AND category = ? AND kind = ?",
            (user_id, category.strip(), kind),
        )
        return cur.rowcount > 0


def rename_custom_category(user_id: int, old_name: str, new_name: str, kind: str = CHIQIM) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE custom_categories SET category = ? WHERE user_id = ? AND category = ? AND kind = ?",
            (new_name.strip(), user_id, old_name.strip(), kind),
        )
        if cur.rowcount > 0:
            conn.execute(
                "UPDATE expenses SET category = ? WHERE user_id = ? AND category = ? AND kind = ?",
                (new_name.strip(), user_id, old_name.strip(), kind),
            )
            return True
        return False


def get_custom_categories_grouped(user_id: int, kind: str = CHIQIM):
    """{category: [subcategory, ...]} ko'rinishida qaytaradi (tugmalar uchun)."""
    rows = get_custom_categories(user_id, kind)
    grouped = {}
    for cat, sub, _ in rows:
        grouped.setdefault(cat, [])
        if sub not in grouped[cat]:
            grouped[cat].append(sub)
    return grouped


def get_subcategory_keywords(user_id: int, category: str, subcategory: str, kind: str = CHIQIM):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT keywords FROM custom_categories WHERE user_id = ? AND category = ? "
            "AND subcategory = ? AND kind = ?",
            (user_id, category.strip(), subcategory.strip(), kind),
        ).fetchone()
        return row["keywords"].split(",") if row else []


def rename_subcategory(user_id: int, category: str, old_sub: str, new_sub: str, kind: str = CHIQIM) -> bool:
    """Faqat bitta subkategoriya nomini o'zgartiradi (kategoriya o'zgarmaydi)."""
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE custom_categories SET subcategory = ? "
            "WHERE user_id = ? AND category = ? AND subcategory = ? AND kind = ?",
            (new_sub.strip(), user_id, category.strip(), old_sub.strip(), kind),
        )
        if cur.rowcount > 0:
            conn.execute(
                "UPDATE expenses SET subcategory = ? "
                "WHERE user_id = ? AND category = ? AND subcategory = ? AND kind = ?",
                (new_sub.strip(), user_id, category.strip(), old_sub.strip(), kind),
            )
            return True
        return False


def update_subcategory_keywords(user_id: int, category: str, subcategory: str, keywords: list, kind: str = CHIQIM) -> bool:
    kw_str = ",".join(k.strip().lower() for k in keywords if k.strip())
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE custom_categories SET keywords = ? "
            "WHERE user_id = ? AND category = ? AND subcategory = ? AND kind = ?",
            (kw_str, user_id, category.strip(), subcategory.strip(), kind),
        )
        return cur.rowcount > 0


def delete_subcategory(user_id: int, category: str, subcategory: str, kind: str = CHIQIM) -> bool:
    """Faqat bitta subkategoriyani o'chiradi (butun kategoriyani emas)."""
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM custom_categories WHERE user_id = ? AND category = ? "
            "AND subcategory = ? AND kind = ?",
            (user_id, category.strip(), subcategory.strip(), kind),
        )
        return cur.rowcount > 0


# ---- Tranzaksiyalar (chiqim va kirim uchun umumiy) ----

def add_expense(user_id: int, amount: float, category: str, subcategory: str, note: str,
                 source: str = "text", kind: str = CHIQIM):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, subcategory, note, source, kind, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, amount, category, subcategory, note, source, kind, datetime.now().isoformat()),
        )


def delete_last_expense(user_id: int, kind: str = CHIQIM) -> bool:
    """Foydalanuvchining shu turdagi oxirgi yozuvini o'chiradi."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM expenses WHERE user_id = ? AND kind = ? ORDER BY id DESC LIMIT 1",
            (user_id, kind),
        ).fetchone()
        if not row:
            return False
        conn.execute("DELETE FROM expenses WHERE id = ?", (row["id"],))
        return True


def get_expenses(user_id: int, start: datetime, end: datetime, kind: str = CHIQIM):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? AND kind = ? AND created_at >= ? AND created_at < ? "
            "ORDER BY created_at DESC",
            (user_id, kind, start.isoformat(), end.isoformat()),
        ).fetchall()
        return rows


def get_summary_by_category(user_id: int, start: datetime, end: datetime, kind: str = CHIQIM):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT category, SUM(amount) as total, COUNT(*) as cnt "
            "FROM expenses WHERE user_id = ? AND kind = ? AND created_at >= ? AND created_at < ? "
            "GROUP BY category ORDER BY total DESC",
            (user_id, kind, start.isoformat(), end.isoformat()),
        ).fetchall()
        return rows


def get_summary_by_subcategory(user_id: int, start: datetime, end: datetime, kind: str = CHIQIM):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT category, subcategory, SUM(amount) as total, COUNT(*) as cnt "
            "FROM expenses WHERE user_id = ? AND kind = ? AND created_at >= ? AND created_at < ? "
            "GROUP BY category, subcategory ORDER BY category, total DESC",
            (user_id, kind, start.isoformat(), end.isoformat()),
        ).fetchall()
        return rows


def get_total(user_id: int, start: datetime, end: datetime, kind: str = CHIQIM) -> float:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) as total FROM expenses "
            "WHERE user_id = ? AND kind = ? AND created_at >= ? AND created_at < ?",
            (user_id, kind, start.isoformat(), end.isoformat()),
        ).fetchone()
        return row["total"]


def get_recent_expenses(user_id: int, kind: str = CHIQIM, limit: int = 10):
    """Oxirgi N ta yozuvni qaytaradi (eng yangisi birinchi)."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, amount, category, subcategory, note, created_at FROM expenses "
            "WHERE user_id = ? AND kind = ? ORDER BY id DESC LIMIT ?",
            (user_id, kind, limit),
        ).fetchall()
        return rows


def update_expense_amount(user_id: int, expense_id: int, new_amount: float) -> bool:
    """Faqat shu foydalanuvchiga tegishli yozuvning miqdorini yangilaydi."""
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE expenses SET amount = ? WHERE id = ? AND user_id = ?",
            (new_amount, expense_id, user_id),
        )
        return cur.rowcount > 0


def get_expense_by_id(user_id: int, expense_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM expenses WHERE id = ? AND user_id = ?",
            (expense_id, user_id),
        ).fetchone()
        return row
