"""
reports.py — Oylik va yillik hisobotlarni matn va diagramma ko'rinishida
shakllantirish. Chiqim (xarajat) va kirim (daromad) uchun umumiy.
"""
import io
from datetime import datetime
from calendar import monthrange

import matplotlib
matplotlib.use("Agg")  # server muhitida ekran kerak emas
import matplotlib.pyplot as plt

import database as db
from database import CHIQIM, KIRIM

CATEGORY_EMOJI = {
    "oziq-ovqat": "🍎",
    "transport": "🚕",
    "kiyim-kechak": "👕",
    "kommunal": "💡",
    "sog'liq": "💊",
    "ko'ngilochar": "🎬",
    "ta'lim": "📚",
    "boshqa": "📦",
    "pensiya": "👵",
    "taksi": "🚕",
    "asaxiy": "💹",
    "iman": "💰",
}

CATEGORY_COLORS = [
    "#FF6B6B", "#4ECDC4", "#45B7D1", "#FFA94D",
    "#A78BFA", "#F783AC", "#63E6BE", "#FFD43B",
    "#748FFC", "#FF922B",
]

OY_NOMLARI = [
    "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
    "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr",
]


def _fmt(amount: float) -> str:
    return f"{amount:,.0f}".replace(",", " ")


def month_range(year: int, month: int):
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)
    return start, end


def year_range(year: int):
    return datetime(year, 1, 1), datetime(year + 1, 1, 1)


def prev_month(year: int, month: int):
    """Oldingi oyni qaytaradi (year, month)."""
    if month == 1:
        return year - 1, 12
    return year, month - 1


# ---- Diagramma ----

def generate_pie_chart(user_id: int, start: datetime, end: datetime, title: str, kind: str = CHIQIM):
    """
    Kategoriyalar bo'yicha doira diagramma yasaydi.
    Ma'lumot bo'lmasa None qaytaradi, aks holda PNG rasm baytlari (BytesIO).
    """
    rows = db.get_summary_by_category(user_id, start, end, kind=kind)
    if not rows:
        return None

    labels = [r["category"] for r in rows]
    values = [r["total"] for r in rows]
    colors = [CATEGORY_COLORS[i % len(CATEGORY_COLORS)] for i in range(len(labels))]

    fig, ax = plt.subplots(figsize=(6, 6), facecolor="#1e1e2e")
    ax.set_facecolor("#1e1e2e")
    wedges, texts, autotexts = ax.pie(
        values,
        labels=labels,
        colors=colors,
        autopct="%1.0f%%",
        startangle=90,
        textprops={"color": "white", "fontsize": 11},
        wedgeprops={"edgecolor": "#1e1e2e", "linewidth": 2},
    )
    for at in autotexts:
        at.set_color("#1e1e2e")
        at.set_fontweight("bold")
    ax.set_title(title, color="white", fontsize=14, fontweight="bold", pad=20)
    ax.axis("equal")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor(), bbox_inches="tight", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf


# ---- Matnli hisobot (bitta tur uchun: kirim YOKI chiqim) ----

def build_report(user_id: int, start: datetime, end: datetime, title: str, kind: str = CHIQIM) -> str:
    label = "Kirim" if kind == KIRIM else "Chiqim"
    icon = "💵" if kind == KIRIM else "📊"

    cat_rows = db.get_summary_by_category(user_id, start, end, kind=kind)
    if not cat_rows:
        return f"{icon} *{title}*\n\nBu davrda {label.lower()} qayd etilmagan."

    subcat_rows = db.get_summary_by_subcategory(user_id, start, end, kind=kind)
    subcats_by_category = {}
    for r in subcat_rows:
        subcats_by_category.setdefault(r["category"], []).append(r)

    total = sum(r["total"] for r in cat_rows)
    lines = [f"{icon} *{title}*\n"]
    for r in cat_rows:
        emoji = CATEGORY_EMOJI.get(r["category"], "📌")
        pct = (r["total"] / total * 100) if total else 0
        lines.append(
            f"{emoji} *{r['category']}*: {_fmt(r['total'])} so'm "
            f"({r['cnt']} ta, {pct:.0f}%)"
        )
        subs = subcats_by_category.get(r["category"], [])
        if len(subs) > 1 or (len(subs) == 1 and subs[0]["subcategory"] != "boshqa"):
            for s in subs:
                lines.append(f"    • {s['subcategory']}: {_fmt(s['total'])} so'm ({s['cnt']} ta)")
    lines.append(f"\n💰 *Jami {label.lower()}:* {_fmt(total)} so'm")
    return "\n".join(lines)


# ---- Birlashtirilgan hisobot: chiqim + kirim + balans ----

def build_full_report(user_id: int, start: datetime, end: datetime, title: str) -> str:
    expense_total = db.get_total(user_id, start, end, kind=CHIQIM)
    income_total = db.get_total(user_id, start, end, kind=KIRIM)
    balance = income_total - expense_total
    balance_emoji = "✅" if balance >= 0 else "⚠️"
    balance_sign = "+" if balance >= 0 else ""

    parts = [f"📅 *{title}*\n"]
    parts.append(build_report(user_id, start, end, "Chiqimlar", kind=CHIQIM))
    parts.append("")
    parts.append(build_report(user_id, start, end, "Kirimlar", kind=KIRIM))
    parts.append("")
    parts.append(
        f"{balance_emoji} *Balans (kirim - chiqim):* {balance_sign}{_fmt(balance)} so'm"
    )
    return "\n".join(parts)


def monthly_report(user_id: int, year: int, month: int, kind: str = CHIQIM) -> str:
    start, end = month_range(year, month)
    title = f"{OY_NOMLARI[month - 1]} {year} oyi bo'yicha hisobot"
    return build_report(user_id, start, end, title, kind=kind)


def monthly_full_report(user_id: int, year: int, month: int) -> str:
    start, end = month_range(year, month)
    title = f"{OY_NOMLARI[month - 1]} {year} oyi bo'yicha hisobot"
    return build_full_report(user_id, start, end, title)


def monthly_chart(user_id: int, year: int, month: int, kind: str = CHIQIM):
    start, end = month_range(year, month)
    suffix = " (kirim)" if kind == KIRIM else " (chiqim)"
    title = f"{OY_NOMLARI[month - 1]} {year}{suffix}"
    return generate_pie_chart(user_id, start, end, title, kind=kind)


def yearly_report(user_id: int, year: int, kind: str = CHIQIM) -> str:
    start, end = year_range(year)
    title = f"{year}-yil bo'yicha hisobot"
    return build_report(user_id, start, end, title, kind=kind)


def yearly_full_report(user_id: int, year: int) -> str:
    start, end = year_range(year)
    title = f"{year}-yil bo'yicha hisobot"
    return build_full_report(user_id, start, end, title)


def yearly_chart(user_id: int, year: int, kind: str = CHIQIM):
    start, end = year_range(year)
    suffix = " (kirim)" if kind == KIRIM else " (chiqim)"
    return generate_pie_chart(user_id, start, end, f"{year}-yil{suffix}", kind=kind)
