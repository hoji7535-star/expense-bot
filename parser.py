"""
parser.py — Foydalanuvchi matnidan (yoki ovozdan matnga aylantirilgandan keyin)
summa va kategoriyani ajratib olish.

Misollar:
  "market 50000"            -> 50000, oziq-ovqat
  "taxi 15 ming"             -> 15000, transport
  "kino uchun 30000 so'm"    -> 30000, ko'ngilochar
  "150 ming kiyim oldim"     -> 150000, kiyim-kechak
"""
import re

# Kategoriya kalit so'zlari (kichik harflarda)
CATEGORY_KEYWORDS = {
    "oziq-ovqat": [
        "market", "oziq", "ovqat", "non", "go'sht", "sabzavot", "meva",
        "supermarket", "bozor", "produkt", "restoran", "kafe", "osh",
        "fastfood", "fast food", "choy", "kofe",
    ],
    "transport": [
        "taxi", "taksi", "avtobus", "metro", "yonilg'i", "benzin",
        "moshina", "mashina", "transport", "yandex", "bolt", "poyezd",
    ],
    "kiyim-kechak": [
        "kiyim", "poyabzal", "krossovka", "futbolka", "shim", "ko'ylak",
        "kurtka", "sumka",
    ],
    "kommunal": [
        "kommunal", "svet", "elektr", "gaz", "suv", "internet", "wifi",
        "telefon", "aloqa", "ijara", "kvartira",
    ],
    "sog'liq": [
        "dori", "dorixona", "shifokor", "vrach", "klinika", "kasalxona",
        "sog'liq", "tibbiyot", "stomatolog",
    ],
    "ko'ngilochar": [
        "kino", "konsert", "o'yin", "oyin", "teatr", "sayohat", "dam olish",
        "klub", "bar", "sovg'a",
    ],
    "ta'lim": [
        "kitob", "kurs", "ta'lim", "maktab", "universitet", "repetitor",
    ],
}

MULTIPLIERS = {
    "ming": 1_000,
    "mln": 1_000_000,
    "million": 1_000_000,
}

NUMBER_RE = re.compile(
    r"(\d[\d\s.,]*)\s*(ming|mln|million)?", re.IGNORECASE
)


def extract_amount(text: str):
    """Matndan eng katta ehtimoldagi summani topadi (so'mda)."""
    best_value = None
    best_span = None
    for m in NUMBER_RE.finditer(text):
        raw_num = m.group(1)
        mult_word = (m.group(2) or "").lower()
        cleaned = raw_num.replace(" ", "").replace(",", "").rstrip(".")
        cleaned = cleaned.rstrip(".")
        if not cleaned or not any(ch.isdigit() for ch in cleaned):
            continue
        try:
            value = float(cleaned)
        except ValueError:
            continue
        if mult_word in MULTIPLIERS:
            value *= MULTIPLIERS[mult_word]
        # Eng katta summani tanlaymiz (odatda bu narx bo'ladi)
        if best_value is None or value > best_value:
            best_value = value
            best_span = m.span()
    return best_value, best_span


def extract_category(text: str) -> str:
    lowered = text.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in lowered:
                return category
    return "boshqa"


def parse_expense_text(text: str):
    """
    Matndan (amount, category, note) qaytaradi.
    Agar summa topilmasa, amount = None bo'ladi.
    """
    amount, span = extract_amount(text)
    category = extract_category(text)

    # Note sifatida summa raqamidan tashqari qolgan matnni olamiz
    if span:
        note = (text[:span[0]] + " " + text[span[1]:]).strip()
    else:
        note = text.strip()
    note = re.sub(r"\s+", " ", note).strip(" -,.")
    if not note:
        note = category

    return amount, category, note
