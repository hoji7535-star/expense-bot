"""
parser.py — Foydalanuvchi matnidan (yoki ovozdan matnga aylantirilgandan keyin)
summa, kategoriya va subkategoriyani ajratib olish.

Misollar:
  "market 50000"            -> 50000, oziq-ovqat, market/supermarket
  "taxi 15 ming"             -> 15000, transport, taksi
  "kino uchun 30000 so'm"    -> 30000, ko'ngilochar, kino/teatr
  "150 ming kiyim oldim"     -> 150000, kiyim-kechak, kiyim
"""
import re

# Kategoriya -> subkategoriya -> kalit so'zlar (kichik harflarda)
CATEGORY_TREE = {
    "oziq-ovqat": {
        "market/supermarket": ["market", "supermarket", "bozor", "produkt", "do'kon"],
        "restoran/kafe": ["restoran", "kafe", "osh", "oshxona"],
        "fastfood": ["fastfood", "fast food", "burger", "pitsa", "shashlik"],
        "ichimlik": ["choy", "kofe", "coffee", "sув", "sharbat"],
        "oziq-ovqat (umumiy)": ["oziq", "ovqat", "non", "go'sht", "sabzavot", "meva"],
    },
    "transport": {
        "taksi": ["taxi", "taksi", "yandex", "bolt", "mytaxi"],
        "jamoat transporti": ["avtobus", "metro", "poyezd", "marshrutka"],
        "yonilg'i": ["benzin", "yonilg'i", "gaz kolonka", "zapravka"],
        "transport (umumiy)": ["transport", "moshina", "mashina", "yo'l haqi"],
    },
    "kiyim-kechak": {
        "kiyim": ["kiyim", "futbolka", "shim", "ko'ylak", "kurtka"],
        "poyabzal": ["poyabzal", "krossovka", "botinka", "tufli"],
        "aksessuar": ["sumka", "soat", "ko'zoynak", "aksessuar"],
    },
    "kommunal": {
        "svet/elektr": ["svet", "elektr"],
        "gaz": ["gaz"],
        "suv": ["suv ta'minoti", "suv haqi"],
        "internet/aloqa": ["internet", "wifi", "telefon", "aloqa"],
        "ijara": ["ijara", "kvartira haqi"],
        "kommunal (umumiy)": ["kommunal"],
    },
    "sog'liq": {
        "dorixona": ["dori", "dorixona"],
        "shifokor": ["shifokor", "vrach", "klinika", "kasalxona", "stomatolog"],
        "sog'liq (umumiy)": ["sog'liq", "tibbiyot"],
    },
    "ko'ngilochar": {
        "kino/teatr": ["kino", "teatr", "konsert"],
        "sayohat": ["sayohat", "dam olish", "safar"],
        "o'yin-kulgi": ["o'yin", "oyin", "klub", "bar"],
        "sovg'a": ["sovg'a", "gift"],
    },
    "ta'lim": {
        "kitob": ["kitob"],
        "kurs/repetitor": ["kurs", "repetitor"],
        "ta'lim (umumiy)": ["ta'lim", "maktab", "universitet"],
    },
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


def extract_category(text: str, custom_categories=None):
    """(category, subcategory) qaytaradi. Topilmasa ('boshqa', 'boshqa').
    custom_categories: [(category, subcategory, [keywords...]), ...] —
    foydalanuvchi qo'shgan kategoriyalar birinchi navbatda tekshiriladi,
    chunki ular standart ro'yxatdan ustunroq bo'lishi kerak.
    """
    lowered = text.lower()

    if custom_categories:
        for category, subcat, keywords in custom_categories:
            for kw in keywords:
                kw = kw.strip()
                if kw and kw in lowered:
                    return category, subcat

    for category, subcats in CATEGORY_TREE.items():
        for subcat, keywords in subcats.items():
            for kw in keywords:
                if kw in lowered:
                    return category, subcat
    return "boshqa", "boshqa"


def parse_expense_text(text: str, custom_categories=None):
    """
    Matndan (amount, category, subcategory, note) qaytaradi.
    Agar summa topilmasa, amount = None bo'ladi.
    """
    amount, span = extract_amount(text)
    category, subcategory = extract_category(text, custom_categories)

    # Note sifatida summa raqamidan tashqari qolgan matnni olamiz
    if span:
        note = (text[:span[0]] + " " + text[span[1]:]).strip()
    else:
        note = text.strip()
    note = re.sub(r"\s+", " ", note).strip(" -,.")
    if not note:
        note = subcategory

    return amount, category, subcategory, note

