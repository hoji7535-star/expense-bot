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

    custom_categories: [(category, subcategory, [keywords...]), ...]

    Ikki bosqichli aniqlash:
    1) Avval matnda kategoriya NOMINING o'zi bor-yo'qligini tekshiramiz
       (masalan "Muhammad Umar"). Topilsa, faqat SHU kategoriya ichidagi
       subkategoriyalarni qidiramiz — bu bir xil so'z (masalan "dori")
       turli odamlarga tegishli bo'lganda chalkashmaslik uchun kerak.
    2) Agar kategoriya nomi topilmasa, barcha kalit so'zlar bo'yicha
       to'g'ridan-to'g'ri qidiramiz (avvalgidek).
    """
    lowered = text.lower()

    # Foydalanuvchi kategoriyalarini category -> {subcat: [keywords]} ga yig'amiz
    custom_tree = {}
    if custom_categories:
        for category, subcat, keywords in custom_categories:
            custom_tree.setdefault(category, {})[subcat] = keywords

    # 1-bosqich: kategoriya nomi matnda bormi?
    all_trees = [(cat, subs) for cat, subs in custom_tree.items()] + \
                [(cat, subs) for cat, subs in CATEGORY_TREE.items()]
    for category, subs in all_trees:
        if category.lower() in lowered:
            # Shu kategoriya ichida subkategoriya qidiramiz
            for subcat, keywords in subs.items():
                for kw in keywords:
                    kw = kw.strip().lower()
                    if kw and kw in lowered:
                        return category, subcat
            # Kategoriya topildi, lekin subkategoriya aniqlanmadi
            first_sub = next(iter(subs), "boshqa")
            return category, first_sub

    # 2-bosqich: to'g'ridan-to'g'ri kalit so'z qidiruvi (custom birinchi)
    if custom_categories:
        matches = []
        for category, subcat, keywords in custom_categories:
            for kw in keywords:
                kw = kw.strip().lower()
                if kw and kw in lowered:
                    matches.append((category, subcat))
                    break
        if matches:
            distinct_categories = {m[0] for m in matches}
            if len(distinct_categories) == 1:
                # Faqat bitta kategoriyaga tegishli — ishonchli
                return matches[0]
            # Bir nechta turli kategoriyaga mos keldi (masalan bir nechta
            # odamda "dori" bor) — noto'g'ri taxmin qilmaslik uchun
            # aniqlanmagan deb hisoblaymiz, bot foydalanuvchidan tugma
            # orqali so'raydi.
            return "boshqa", "boshqa"

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

