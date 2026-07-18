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
    cat_rows = db.get_summary_by_category(user_id, start, end)
    if not cat_rows:
        return f"📊 *{title}*\n\nBu davrda xarajatlar qayd etilmagan."

    subcat_rows = db.get_summary_by_subcategory(user_id, start, end)
    subcats_by_category = {}
    for r in subcat_rows:
        subcats_by_category.setdefault(r["category"], []).append(r)

    total = sum(r["total"] for r in cat_rows)
    lines = [f"📊 *{title}*\n"]
    for r in cat_rows:
        emoji = CATEGORY_EMOJI.get(r["category"], "📦")
        pct = (r["total"] / total * 100) if total else 0
        lines.append(
            f"{emoji} *{r['category'].capitalize()}*: {_fmt(r['total'])} so'm "
            f"({r['cnt']} ta, {pct:.0f}%)"
        )
        # Subkategoriyalar (agar bittadan ko'p bo'lsa, batafsilroq ko'rsatamiz)
        subs = subcats_by_category.get(r["category"], [])
        if len(subs) > 1 or (len(subs) == 1 and subs[0]["subcategory"] != "boshqa"):
            for s in subs:
                lines.append(
                    f"    • {s['subcategory']}: {_fmt(s['total'])} so'm ({s['cnt']} ta)"
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
