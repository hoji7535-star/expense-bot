"""
reports.py — Oylik va yillik hisobotlarni matn ko'rinishida shakllantirish.
"""
from datetime import datetime
from calendar import monthrange
import database as db

CATEGORY_EMOJI = {
    "oziq-ovqat": "🍎",
    "transport": "🚕",
    "kiyim-kechak": "👕",
    "kommunal": "💡",
    "sog'liq": "💊",
    "ko'ngilochar": "🎬",
    "ta'lim": "📚",
    "boshqa": "📦",
}


def _fmt(amount: float) -> str:
    return f"{amount:,.0f}".replace(",", " ")


def month_range(year: int, month: int):
    start = datetime(year, month, 1)
    last_day = monthrange(year, month)[1]
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)
    return start, end


def year_range(year: int):
    return datetime(year, 1, 1), datetime(year + 1, 1, 1)


def build_report(user_id: int, start: datetime, end: datetime, title: str) -> str:
    rows = db.get_summary_by_category(user_id, start, end)
    if not rows:
        return f"📊 *{title}*\n\nBu davrda xarajatlar qayd etilmagan."

    total = sum(r["total"] for r in rows)
    lines = [f"📊 *{title}*\n"]
    for r in rows:
        emoji = CATEGORY_EMOJI.get(r["category"], "📦")
        pct = (r["total"] / total * 100) if total else 0
        lines.append(
            f"{emoji} {r['category'].capitalize()}: {_fmt(r['total'])} so'm "
            f"({r['cnt']} ta, {pct:.0f}%)"
        )
    lines.append(f"\n💰 *Jami:* {_fmt(total)} so'm")
    return "\n".join(lines)


def monthly_report(user_id: int, year: int, month: int) -> str:
    start, end = month_range(year, month)
    oy_nomlari = [
        "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
        "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr",
    ]
    title = f"{oy_nomlari[month - 1]} {year} oyi bo'yicha hisobot"
    return build_report(user_id, start, end, title)


def yearly_report(user_id: int, year: int) -> str:
    start, end = year_range(year)
    title = f"{year}-yil bo'yicha hisobot"
    return build_report(user_id, start, end, title)
