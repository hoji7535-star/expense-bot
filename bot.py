"""
bot.py — Shaxsiy xarajat (chiqim) va daromad (kirim) hisobi Telegram boti.

Ishga tushirish:
    1. .env faylida TELEGRAM_BOT_TOKEN ni kiriting (.env.example ga qarang)
    2. pip install -r requirements.txt
    3. ffmpeg o'rnatilganiga ishonch hosil qiling (apt install ffmpeg)
    4. python bot.py

Asosiy buyruqlar:
    /start, /help          — yo'riqnoma
    /oylik, /yillik        — chiqim + kirim + balans hisoboti (matn + diagramma)
    /ochirish               — oxirgi CHIQIMni o'chirish
    /daromadochirish         — oxirgi KIRIMni o'chirish
    /daromad <matn>          — daromad (kirim) kiritish, masalan: /daromad pensiya 500000

    Kategoriya (CHIQIM):
    /kategoriyalar, /yangikategoriya, /kategoriyayukla,
    /kategoriyanomi, /kategoriyaochir

    Kategoriya (KIRIM):
    /daromadkategoriyalar, /yangidaromadkategoriya, /daromadkategoriyayukla,
    /daromadkategoriyanomi, /daromadkategoriyaochir

    Matn xabar (oddiy)  → CHIQIM sifatida qayd etiladi
    Ovozli xabar        → CHIQIM sifatida qayd etiladi
    Har oyning 1-sanasida, avtomatik ravishda o'tgan oy hisoboti yuboriladi.
"""
import logging
import os
import re
import tempfile
from datetime import datetime, time, timedelta

from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    PicklePersistence,
)

import database as db
from database import CHIQIM, KIRIM
import reports
import voice as voice_module
from parser import parse_expense_text, CATEGORY_TREE, INCOME_CATEGORY_TREE

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["📊 Oylik hisobot", "📆 Yillik hisobot"],
        ["📈 Oylararo solishtirish", "🏷 Kategoriyalar"],
        ["💵 Daromad qo'shish", "↩️ Oxirgisini o'chirish"],
        ["✏️ Kategoriya tahrirlash", "💲 Miqdorni tahrirlash"],
        ["ℹ️ Yordam"],
    ],
    resize_keyboard=True,
)

# Suhbat holatlari
CAT_NAME, SUBCAT_NAME, KEYWORDS = range(3)
BULK_IMPORT = 3
DAROMAD_TEXT = 4
EDIT_INPUT = 5


# ============================================================
#  Yordamchi: kategoriya ro'yxatini matndan bir martada aniqlash
# ============================================================

def _looks_like_bulk_category_list(text: str) -> bool:
    """Matn 'Kategoriya: sub1, sub2, ...' formatidagi qatorlardan
    iboratmi — shunga o'xshasa True. Suhbat holatidan mustaqil ishlaydi,
    shuning uchun bot qayta ishga tushgan taqdirda ham ro'yxatni to'g'ri
    tanib oladi."""
    line_pattern = re.compile(r"^[^:]{2,40}:\s*[^,]+(,\s*[^,]+)+$")
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if not lines:
        return False
    matching = sum(1 for ln in lines if line_pattern.match(ln))
    return matching >= 1 and matching >= len(lines) / 2


async def _do_bulk_import(user_id: int, raw_text: str, kind: str) -> str:
    """Ro'yxatni bazaga yozadi va xabar matnini qaytaradi."""
    lines = raw_text.strip().splitlines()
    added = []
    errors = []

    for line in lines:
        line = line.strip()
        if not line or ":" not in line:
            if line:
                errors.append(line)
            continue
        cat_part, subs_part = line.split(":", 1)
        category = cat_part.strip()
        subcats = [s.strip() for s in subs_part.split(",") if s.strip()]
        if not category or not subcats:
            errors.append(line)
            continue
        for sub in subcats:
            db.add_custom_category(user_id, category, sub, [sub], kind=kind)
            added.append(f"{category} → {sub}")

    if not added:
        return "❌ Hech qanday kategoriya qo'shilmadi. Format: `Kategoriya: sub1, sub2`"

    summary = f"✅ {len(added)} ta subkategoriya qo'shildi."
    if errors:
        summary += f"\n⚠️ {len(errors)} qator formatga mos kelmadi va o'tkazib yuborildi."
    return summary


# ============================================================
#  /start, /help
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    db.register_user(user_id, chat_id)

    text = (
        "👋 Salom! Men shaxsiy xarajat va daromad hisobi botiman.\n\n"
        "💬 *Xarajat (chiqim)* — matn yoki ovoz bilan yozing:\n"
        "   `Muhammad Umar dori 5000`\n"
        "   `Avto benzin 100 ming`\n\n"
        "💵 *Daromad (kirim)* — ikki xil usulda kiritish mumkin:\n"
        "   `/daromad pensiya 500000`\n"
        "   yoki oddiygina: `+500000 pensiya` (boshida \"+\" bilan)\n\n"
        "📊 /oylik — joriy oy hisoboti (chiqim + kirim + balans + diagramma)\n"
        "📆 /yillik — joriy yil hisoboti\n"
        "📈 /solishtir — joriy oyni oldingi oy bilan solishtirish (matn + diagramma)\n"
        "↩️ /ochirish — oxirgi chiqimni o'chirish\n"
        "↩️ /daromadochirish — oxirgi kirimni o'chirish\n\n"
        "🏷 *Chiqim kategoriyalari:*\n"
        "   /kategoriyalar, /yangikategoriya, /kategoriyayukla,\n"
        "   /kategoriyanomi, /kategoriyaochir\n\n"
        "🏷 *Kirim kategoriyalari:*\n"
        "   /daromadkategoriyalar, /yangidaromadkategoriya,\n"
        "   /daromadkategoriyayukla, /daromadkategoriyanomi, /daromadkategoriyaochir\n\n"
        "✏️ /tahrirlash — mavjud kategoriya/subkategoriyani tugmalar orqali "
        "tahrirlash (nomini o'zgartirish, kalit so'zlarini yangilash, o'chirish)\n"
        "💲 /miqdortahrir — kiritilgan yozuvning miqdorini (summasini) o'zgartirish\n\n"
        "🗓 Har oyning 1-sanasida, o'tgan oy hisoboti avtomatik yuboriladi.\n"
        "❓ Kategoriya aniqlanmasa, bot tugmalar orqali tanlashni so'raydi."
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


# ============================================================
#  Hisobotlar
# ============================================================

async def monthly_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    user_id = update.effective_user.id
    text = reports.monthly_full_report(user_id, now.year, now.month)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)

    chart = reports.monthly_chart(user_id, now.year, now.month, kind=CHIQIM)
    if chart:
        await update.message.reply_photo(photo=chart, caption="📊 Chiqimlar taqsimoti")
    income_chart = reports.monthly_chart(user_id, now.year, now.month, kind=KIRIM)
    if income_chart:
        await update.message.reply_photo(photo=income_chart, caption="💵 Kirimlar taqsimoti")


async def yearly_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    user_id = update.effective_user.id
    text = reports.yearly_full_report(user_id, now.year)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)

    chart = reports.yearly_chart(user_id, now.year, kind=CHIQIM)
    if chart:
        await update.message.reply_photo(photo=chart, caption="📊 Chiqimlar taqsimoti")
    income_chart = reports.yearly_chart(user_id, now.year, kind=KIRIM)
    if income_chart:
        await update.message.reply_photo(photo=income_chart, caption="💵 Kirimlar taqsimoti")


async def compare_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    user_id = update.effective_user.id

    text = reports.compare_report(user_id, now.year, now.month, kind=CHIQIM)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)
    chart = reports.compare_chart(user_id, now.year, now.month, kind=CHIQIM)
    if chart:
        await update.message.reply_photo(photo=chart, caption="📊 Chiqim: oylararo solishtiruv")

    income_text = reports.compare_report(user_id, now.year, now.month, kind=KIRIM)
    await update.message.reply_text(income_text, parse_mode="Markdown")
    income_chart = reports.compare_chart(user_id, now.year, now.month, kind=KIRIM)
    if income_chart:
        await update.message.reply_photo(photo=income_chart, caption="💵 Kirim: oylararo solishtiruv")


async def delete_last_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ok = db.delete_last_expense(user_id, kind=CHIQIM)
    if ok:
        await update.message.reply_text("✅ Oxirgi chiqim o'chirildi.", reply_markup=MAIN_KEYBOARD)
    else:
        await update.message.reply_text("Hozircha o'chiriladigan chiqim yo'q.", reply_markup=MAIN_KEYBOARD)


async def delete_last_income_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ok = db.delete_last_expense(user_id, kind=KIRIM)
    if ok:
        await update.message.reply_text("✅ Oxirgi kirim o'chirildi.", reply_markup=MAIN_KEYBOARD)
    else:
        await update.message.reply_text("Hozircha o'chiriladigan kirim yo'q.", reply_markup=MAIN_KEYBOARD)


# ============================================================
#  Kategoriyalarni ko'rish
# ============================================================

async def _list_categories(update: Update, user_id: int, kind: str):
    default_tree = INCOME_CATEGORY_TREE if kind == KIRIM else CATEGORY_TREE
    label = "Kirim" if kind == KIRIM else "Chiqim"

    lines = []
    if default_tree:
        lines.append(f"🏷 *Standart {label.lower()} kategoriyalari:*\n")
        for cat, subs in default_tree.items():
            emoji = reports.CATEGORY_EMOJI.get(cat, "📌")
            lines.append(f"{emoji} *{cat}*: " + ", ".join(subs.keys()))
        lines.append("")

    custom = db.get_custom_categories(user_id, kind=kind)
    if custom:
        lines.append(f"🏷 *Sizning {label.lower()} kategoriyalaringiz:*\n")
        seen = {}
        for cat, sub, _ in custom:
            seen.setdefault(cat, []).append(sub)
        for cat, subs in seen.items():
            lines.append(f"📌 *{cat}*: " + ", ".join(subs))
    elif not default_tree:
        lines.append(f"Hozircha {label.lower()} kategoriyasi yo'q.")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)


async def list_categories_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _list_categories(update, update.effective_user.id, CHIQIM)


async def list_income_categories_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _list_categories(update, update.effective_user.id, KIRIM)


# ============================================================
#  /yangikategoriya va /yangidaromadkategoriya — bitta-bitta qo'shish
# ============================================================

async def new_category_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_cat_kind"] = CHIQIM
    await update.message.reply_text(
        "🆕 Yangi CHIQIM kategoriyasi yaratamiz.\n\n"
        "1-qadam: Kategoriya nomini kiriting (masalan: `Sport`)",
        parse_mode="Markdown",
    )
    return CAT_NAME


async def new_income_category_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_cat_kind"] = KIRIM
    await update.message.reply_text(
        "🆕 Yangi KIRIM (daromad) kategoriyasi yaratamiz.\n\n"
        "1-qadam: Kategoriya nomini kiriting (masalan: `Ijara daromadi`)",
        parse_mode="Markdown",
    )
    return CAT_NAME


async def new_category_get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_cat_name"] = update.message.text.strip()
    await update.message.reply_text(
        "2-qadam: Endi subkategoriya nomini kiriting (masalan: `trenajor zali`)"
    )
    return SUBCAT_NAME


async def new_category_get_subcat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_cat_subcat"] = update.message.text.strip()
    await update.message.reply_text(
        "3-qadam: Bu kategoriyani aniqlash uchun kalit so'zlarni vergul bilan kiriting.\n"
        "Masalan: `sport, trenajor, fitnes, zal`"
    )
    return KEYWORDS


async def new_category_get_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keywords = update.message.text.split(",")
    user_id = update.effective_user.id
    cat = context.user_data.pop("new_cat_name")
    subcat = context.user_data.pop("new_cat_subcat")
    kind = context.user_data.pop("new_cat_kind", CHIQIM)
    db.add_custom_category(user_id, cat, subcat, keywords, kind=kind)
    label = "Kirim" if kind == KIRIM else "Chiqim"
    await update.message.reply_text(
        f"✅ Yangi {label.lower()} kategoriyasi qo'shildi: 📌 *{cat}* → {subcat}",
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD,
    )
    return ConversationHandler.END


async def new_category_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for k in ("new_cat_name", "new_cat_subcat", "new_cat_kind"):
        context.user_data.pop(k, None)
    await update.message.reply_text("❌ Bekor qilindi.", reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# ============================================================
#  O'chirish va nomini o'zgartirish
# ============================================================

async def delete_category_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text(
            "Kategoriya nomini ko'rsating: `/kategoriyaochir Sport`", parse_mode="Markdown"
        )
        return
    cat_name = " ".join(context.args)
    ok = db.delete_custom_category(user_id, cat_name, kind=CHIQIM)
    if ok:
        await update.message.reply_text(f"✅ \"{cat_name}\" o'chirildi.", reply_markup=MAIN_KEYBOARD)
    else:
        await update.message.reply_text(f"\"{cat_name}\" topilmadi.", reply_markup=MAIN_KEYBOARD)


async def delete_income_category_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text(
            "Kategoriya nomini ko'rsating: `/daromadkategoriyaochir Ijara`", parse_mode="Markdown"
        )
        return
    cat_name = " ".join(context.args)
    ok = db.delete_custom_category(user_id, cat_name, kind=KIRIM)
    if ok:
        await update.message.reply_text(f"✅ \"{cat_name}\" o'chirildi.", reply_markup=MAIN_KEYBOARD)
    else:
        await update.message.reply_text(f"\"{cat_name}\" topilmadi.", reply_markup=MAIN_KEYBOARD)


async def _rename_category(update: Update, context: ContextTypes.DEFAULT_TYPE, kind: str):
    user_id = update.effective_user.id
    full_text = " ".join(context.args)
    if "|" not in full_text:
        cmd = "/daromadkategoriyanomi" if kind == KIRIM else "/kategoriyanomi"
        await update.message.reply_text(
            f"Format: `{cmd} Eski nomi | Yangi nomi`", parse_mode="Markdown"
        )
        return
    old_name, new_name = [p.strip() for p in full_text.split("|", 1)]
    ok = db.rename_custom_category(user_id, old_name, new_name, kind=kind)
    if ok:
        await update.message.reply_text(
            f"✅ \"{old_name}\" → \"{new_name}\" deb o'zgartirildi.", reply_markup=MAIN_KEYBOARD
        )
    else:
        await update.message.reply_text(f"\"{old_name}\" topilmadi.", reply_markup=MAIN_KEYBOARD)


async def rename_category_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _rename_category(update, context, CHIQIM)


async def rename_income_category_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _rename_category(update, context, KIRIM)


# ============================================================
#  Bir martada ro'yxat yuklash (/kategoriyayukla, /daromadkategoriyayukla)
# ============================================================

async def bulk_import_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["bulk_kind"] = CHIQIM
    await update.message.reply_text(
        "📋 CHIQIM kategoriyalari ro'yxatini yuboring. Har bir qatorda:\n"
        "`Kategoriya: subkategoriya1, subkategoriya2, ...`\n\n"
        "Bekor qilish uchun /bekor yozing.",
        parse_mode="Markdown",
    )
    return BULK_IMPORT


async def bulk_import_income_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["bulk_kind"] = KIRIM
    await update.message.reply_text(
        "📋 KIRIM kategoriyalari ro'yxatini yuboring. Har bir qatorda:\n"
        "`Kategoriya: subkategoriya1, subkategoriya2, ...`\n\n"
        "Masalan:\n```\nAsosiy ish: oylik, bonus\nQoshimcha: frilanс, ijara\n```\n"
        "Bekor qilish uchun /bekor yozing.",
        parse_mode="Markdown",
    )
    return BULK_IMPORT


async def bulk_import_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    raw_text = update.message.text.strip()
    kind = context.user_data.get("bulk_kind", CHIQIM)

    if ":" not in raw_text:
        await update.message.reply_text(
            "ℹ️ Bu kategoriya ro'yxati formatiga o'xshamadi, shuning uchun "
            "oddiy xarajat sifatida qabul qildim:"
        )
        await _register_transaction(update, context, raw_text, source="text", kind=CHIQIM)
        context.user_data.pop("bulk_kind", None)
        return ConversationHandler.END

    result_text = await _do_bulk_import(user_id, raw_text, kind)
    if result_text.startswith("❌"):
        await update.message.reply_text(
            result_text + "\nQayta urinib ko'ring yoki /bekor deb yozing.", parse_mode="Markdown"
        )
        return BULK_IMPORT

    context.user_data.pop("bulk_kind", None)
    await update.message.reply_text(result_text, reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# ============================================================
#  Mavjud kategoriya/subkategoriyani tahrirlash (/tahrirlash)
#  Oqim: kind tanlash -> kategoriya tanlash -> subkategoriya tanlash
#        -> amal tanlash (nomi/kalit so'z/o'chirish) -> (kerak bo'lsa matn kiritish)
# ============================================================

async def edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton("📊 Chiqim kategoriyasi", callback_data="edk:chiqim")],
        [InlineKeyboardButton("💵 Kirim kategoriyasi", callback_data="edk:kirim")],
    ]
    await update.message.reply_text(
        "✏️ Qaysi turdagi kategoriyani tahrirlaymiz?",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def edit_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    data = query.data

    # 1-qadam: kind tanlandi -> kategoriyalar ro'yxati
    if data.startswith("edk:"):
        kind = data.split(":", 1)[1]
        grouped = db.get_custom_categories_grouped(user_id, kind=kind)
        if not grouped:
            await query.edit_message_text("Hozircha bu turda tahrirlanadigan kategoriya yo'q.")
            return
        context.user_data["edit_kind"] = kind
        context.user_data["edit_cats"] = list(grouped.keys())
        buttons = [
            [InlineKeyboardButton(f"📌 {c}", callback_data=f"edc:{i}")]
            for i, c in enumerate(context.user_data["edit_cats"])
        ]
        await query.edit_message_text("Qaysi kategoriya?", reply_markup=InlineKeyboardMarkup(buttons))
        return

    # 2-qadam: kategoriya tanlandi -> subkategoriyalar ro'yxati
    if data.startswith("edc:"):
        idx = int(data.split(":", 1)[1])
        cats = context.user_data.get("edit_cats", [])
        if idx >= len(cats):
            await query.edit_message_text("❌ Xatolik yuz berdi, qaytadan /tahrirlash bosing.")
            return
        category = cats[idx]
        kind = context.user_data.get("edit_kind", CHIQIM)
        grouped = db.get_custom_categories_grouped(user_id, kind=kind)
        subs = grouped.get(category, [])
        context.user_data["edit_category"] = category
        context.user_data["edit_subs"] = subs
        buttons = [
            [InlineKeyboardButton(s, callback_data=f"eds:{i}")] for i, s in enumerate(subs)
        ]
        await query.edit_message_text(
            f"🏷 *{category}* — qaysi subkategoriyani tahrirlaymiz?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    # 3-qadam: subkategoriya tanlandi -> amal tanlash
    if data.startswith("eds:"):
        idx = int(data.split(":", 1)[1])
        subs = context.user_data.get("edit_subs", [])
        if idx >= len(subs):
            await query.edit_message_text("❌ Xatolik yuz berdi, qaytadan /tahrirlash bosing.")
            return
        subcategory = subs[idx]
        context.user_data["edit_subcategory"] = subcategory
        buttons = [
            [InlineKeyboardButton("✏️ Nomini o'zgartirish", callback_data="eda:rename")],
            [InlineKeyboardButton("🔑 Kalit so'zlarni o'zgartirish", callback_data="eda:keywords")],
            [InlineKeyboardButton("🗑 O'chirish", callback_data="eda:delete")],
        ]
        category = context.user_data.get("edit_category")
        await query.edit_message_text(
            f"🏷 *{category}* → *{subcategory}*\nNima qilamiz?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    # 4-qadam: amal tanlandi
    if data.startswith("eda:"):
        action = data.split(":", 1)[1]
        category = context.user_data.get("edit_category")
        subcategory = context.user_data.get("edit_subcategory")
        kind = context.user_data.get("edit_kind", CHIQIM)

        if action == "delete":
            ok = db.delete_subcategory(user_id, category, subcategory, kind=kind)
            if ok:
                await query.edit_message_text(f"✅ \"{subcategory}\" o'chirildi.")
            else:
                await query.edit_message_text("❌ O'chirishda xatolik.")
            _clear_edit_state(context)
            return

        context.user_data["edit_action"] = action
        if action == "rename":
            await query.edit_message_text(
                f"✏️ \"{subcategory}\" uchun yangi nom yozing:"
            )
        elif action == "keywords":
            current = db.get_subcategory_keywords(user_id, category, subcategory, kind=kind)
            await query.edit_message_text(
                f"🔑 Joriy kalit so'zlar: {', '.join(current)}\n\n"
                "Yangi kalit so'zlarni vergul bilan yozing (eskilarini butunlay almashtiradi):"
            )
        context.user_data["awaiting_edit_input"] = True
        return


def _clear_edit_state(context: ContextTypes.DEFAULT_TYPE):
    for k in ("edit_kind", "edit_cats", "edit_category", "edit_subs", "edit_subcategory",
              "edit_action", "awaiting_edit_input"):
        context.user_data.pop(k, None)


async def edit_text_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Agar foydalanuvchi tahrirlash uchun matn kiritishi kutilayotgan bo'lsa,
    shu yerda qayta ishlanadi. True qaytarsa — xabar band qilingan (boshqa
    handlerlar ishlamasligi kerak)."""
    if not context.user_data.get("awaiting_edit_input"):
        return False

    user_id = update.effective_user.id
    category = context.user_data.get("edit_category")
    subcategory = context.user_data.get("edit_subcategory")
    kind = context.user_data.get("edit_kind", CHIQIM)
    action = context.user_data.get("edit_action")
    text = update.message.text.strip()

    if action == "rename":
        ok = db.rename_subcategory(user_id, category, subcategory, text, kind=kind)
        if ok:
            await update.message.reply_text(
                f"✅ \"{subcategory}\" → \"{text}\" deb o'zgartirildi.", reply_markup=MAIN_KEYBOARD
            )
        else:
            await update.message.reply_text("❌ Xatolik yuz berdi.", reply_markup=MAIN_KEYBOARD)
    elif action == "keywords":
        keywords = text.split(",")
        ok = db.update_subcategory_keywords(user_id, category, subcategory, keywords, kind=kind)
        if ok:
            await update.message.reply_text("✅ Kalit so'zlar yangilandi.", reply_markup=MAIN_KEYBOARD)
        else:
            await update.message.reply_text("❌ Xatolik yuz berdi.", reply_markup=MAIN_KEYBOARD)

    _clear_edit_state(context)
    return True


# ============================================================
#  Kiritilgan yozuvning MIQDORINI tahrirlash (/miqdortahrir)
#  Oqim: kind tanlash -> oxirgi yozuvlar ro'yxati -> yangi summa kiritish
# ============================================================

async def amount_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton("📊 Chiqim", callback_data="amtk:chiqim")],
        [InlineKeyboardButton("💵 Kirim", callback_data="amtk:kirim")],
    ]
    await update.message.reply_text(
        "✏️ Qaysi turdagi yozuvning miqdorini o'zgartiramiz?",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


def _format_expense_button_label(row) -> str:
    date_str = row["created_at"][:10]
    return f"{date_str} | {row['category']}→{row['subcategory']} | {row['amount']:,.0f} so'm".replace(",", " ")


async def amount_edit_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    data = query.data

    if data.startswith("amtk:"):
        kind = data.split(":", 1)[1]
        rows = db.get_recent_expenses(user_id, kind=kind, limit=10)
        if not rows:
            label = "kirim" if kind == KIRIM else "chiqim"
            await query.edit_message_text(f"Hozircha hech qanday {label} yozuvi yo'q.")
            return
        context.user_data["amount_edit_kind"] = kind
        context.user_data["amount_edit_rows"] = {str(r["id"]): dict(r) for r in rows}
        buttons = [
            [InlineKeyboardButton(_format_expense_button_label(r), callback_data=f"amte:{r['id']}")]
            for r in rows
        ]
        await query.edit_message_text(
            "Oxirgi 10 ta yozuv — qaysi birining miqdorini o'zgartiramiz?",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    if data.startswith("amte:"):
        expense_id = data.split(":", 1)[1]
        rows = context.user_data.get("amount_edit_rows", {})
        row = rows.get(expense_id)
        if not row:
            await query.edit_message_text("❌ Yozuv topilmadi, qayta /miqdortahrir bosing.")
            return
        context.user_data["amount_edit_id"] = int(expense_id)
        context.user_data["awaiting_amount_input"] = True
        await query.edit_message_text(
            f"🏷 {row['category']} → {row['subcategory']}\n"
            f"💰 Hozirgi miqdor: {row['amount']:,.0f} so'm\n\n".replace(",", " ") +
            "Yangi miqdorni raqam bilan yozing:"
        )
        return


async def amount_edit_text_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Agar foydalanuvchidan yangi miqdor kutilayotgan bo'lsa, shu yerda
    qayta ishlanadi. True qaytarsa — xabar band qilingan."""
    if not context.user_data.get("awaiting_amount_input"):
        return False

    user_id = update.effective_user.id
    expense_id = context.user_data.get("amount_edit_id")
    text = update.message.text.strip().replace(" ", "").replace(",", "")

    try:
        new_amount = float(text)
        if new_amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "❌ Iltimos, faqat musbat raqam yozing, masalan: `75000`", parse_mode="Markdown"
        )
        return True  # hali ham shu holatda qolamiz, band qilingan

    ok = db.update_expense_amount(user_id, expense_id, new_amount)
    for k in ("amount_edit_kind", "amount_edit_rows", "amount_edit_id", "awaiting_amount_input"):
        context.user_data.pop(k, None)

    if ok:
        await update.message.reply_text(
            f"✅ Miqdor {new_amount:,.0f} so'mga o'zgartirildi.".replace(",", " "),
            reply_markup=MAIN_KEYBOARD,
        )
    else:
        await update.message.reply_text("❌ Xatolik yuz berdi.", reply_markup=MAIN_KEYBOARD)
    return True


# ============================================================
#  Kategoriya/subkategoriya tugmalar orqali tanlash
# ============================================================

def _all_category_names(user_id: int, kind: str):
    default_tree = INCOME_CATEGORY_TREE if kind == KIRIM else CATEGORY_TREE
    custom_grouped = db.get_custom_categories_grouped(user_id, kind=kind)
    names = list(custom_grouped.keys()) + [c for c in default_tree.keys() if c not in custom_grouped]
    return names, custom_grouped


def _subcats_for(category: str, custom_grouped: dict, kind: str):
    default_tree = INCOME_CATEGORY_TREE if kind == KIRIM else CATEGORY_TREE
    if category in custom_grouped:
        return custom_grouped[category]
    if category in default_tree:
        return list(default_tree[category].keys())
    return ["boshqa"]


async def _ask_category(update: Update, context: ContextTypes.DEFAULT_TYPE, amount, note, source, kind):
    user_id = update.effective_user.id
    names, _ = _all_category_names(user_id, kind)
    context.user_data["pending"] = {"amount": amount, "note": note, "source": source, "kind": kind}
    context.user_data["cat_choices"] = names
    context.user_data["cat_kind"] = kind

    buttons = [
        [InlineKeyboardButton(f"{reports.CATEGORY_EMOJI.get(n, '📌')} {n}", callback_data=f"cat:{i}")]
        for i, n in enumerate(names)
    ]
    buttons.append([InlineKeyboardButton("📦 Boshqa", callback_data="cat:boshqa")])

    label = "Kirim" if kind == KIRIM else "Chiqim"
    await update.message.reply_text(
        f"💰 {amount:,.0f} so'm ({label}) — qaysi kategoriyaga tegishli?".replace(",", " "),
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def category_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    data = query.data
    kind = context.user_data.get("cat_kind", CHIQIM)

    if data.startswith("cat:"):
        choice = data.split(":", 1)[1]
        if choice == "boshqa":
            category = "boshqa"
        else:
            names = context.user_data.get("cat_choices", [])
            idx = int(choice)
            category = names[idx] if idx < len(names) else "boshqa"

        _, custom_grouped = _all_category_names(user_id, kind)
        subs = _subcats_for(category, custom_grouped, kind)
        context.user_data["chosen_category"] = category
        context.user_data["sub_choices"] = subs

        buttons = [[InlineKeyboardButton(s, callback_data=f"sub:{i}")] for i, s in enumerate(subs)]
        await query.edit_message_text(
            f"🏷 Kategoriya: *{category}*\nEndi turini tanlang:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    if data.startswith("sub:"):
        idx = int(data.split(":", 1)[1])
        subs = context.user_data.get("sub_choices", ["boshqa"])
        subcategory = subs[idx] if idx < len(subs) else "boshqa"
        category = context.user_data.get("chosen_category", "boshqa")
        pending = context.user_data.pop("pending", None)
        if not pending:
            await query.edit_message_text("❌ Xatolik: yozuv topilmadi, qayta urinib ko'ring.")
            return

        db.add_expense(
            user_id, pending["amount"], category, subcategory, pending["note"],
            source=pending["source"], kind=pending["kind"],
        )
        emoji = reports.CATEGORY_EMOJI.get(category, "📌")
        label = "Kirim" if pending["kind"] == KIRIM else "Chiqim"
        await query.edit_message_text(
            f"✅ Qayd etildi ({label}): {emoji} *{category}* → {subcategory} — "
            f"{pending['amount']:,.0f} so'm".replace(",", " "),
            parse_mode="Markdown",
        )
        for k in ("cat_choices", "sub_choices", "chosen_category", "cat_kind"):
            context.user_data.pop(k, None)


# ============================================================
#  Tranzaksiya (chiqim yoki kirim) yozib olish
# ============================================================

async def _register_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, source: str, kind: str):
    user_id = update.effective_user.id
    custom_categories = db.get_custom_categories(user_id, kind=kind)
    default_tree = INCOME_CATEGORY_TREE if kind == KIRIM else CATEGORY_TREE
    amount, category, subcategory, note = parse_expense_text(text, custom_categories, default_tree)

    if amount is None:
        await update.message.reply_text(
            "❌ Summani aniqlay olmadim. Iltimos, raqam bilan yozing, "
            "masalan: `Muhammad Umar dori 5000` yoki `pensiya 500000`.",
            parse_mode="Markdown",
        )
        return

    if category == "boshqa" and subcategory == "boshqa":
        await _ask_category(update, context, amount=amount, note=note, source=source, kind=kind)
        return

    db.add_expense(user_id, amount, category, subcategory, note, source=source, kind=kind)
    emoji = reports.CATEGORY_EMOJI.get(category, "📌")
    label = "Kirim" if kind == KIRIM else "Chiqim"
    sub_line = f"\n🏷 {subcategory}" if subcategory != "boshqa" else ""
    await update.message.reply_text(
        f"✅ Qayd etildi ({label}): {emoji} *{category}* — {amount:,.0f} so'm".replace(",", " ")
        + sub_line
        + f"\n📝 {note}",
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD,
    )


async def daromad_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Daromad matnini yozing, masalan:\n`/daromad pensiya 500000`\n`/daromad taksi 300 ming`",
            parse_mode="Markdown",
        )
        return
    text = " ".join(context.args)
    await _register_transaction(update, context, text, source="text", kind=KIRIM)


# ============================================================
#  Matn va ovoz handlerlari (standart — CHIQIM)
# ============================================================

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    # Agar foydalanuvchi /tahrirlash oqimida matn kiritishi kutilayotgan bo'lsa
    if await edit_text_input_handler(update, context):
        return
    # Agar foydalanuvchidan yozuv miqdorini yangilash kutilayotgan bo'lsa
    if await amount_edit_text_input_handler(update, context):
        return

    if text == "📊 Oylik hisobot":
        await monthly_cmd(update, context)
        return
    if text == "📆 Yillik hisobot":
        await yearly_cmd(update, context)
        return
    if text == "📈 Oylararo solishtirish":
        await compare_cmd(update, context)
        return
    if text == "✏️ Kategoriya tahrirlash":
        await edit_start(update, context)
        return
    if text == "💲 Miqdorni tahrirlash":
        await amount_edit_start(update, context)
        return
    if text == "↩️ Oxirgisini o'chirish":
        await delete_last_cmd(update, context)
        return
    if text == "🏷 Kategoriyalar":
        await list_categories_cmd(update, context)
        return
    if text == "💵 Daromad qo'shish":
        await update.message.reply_text(
            "Daromadni shunday yozing:\n"
            "`/daromad pensiya 500000`\n"
            "yoki oddiygina: `+500000 pensiya`",
            parse_mode="Markdown",
        )
        return
    if text == "ℹ️ Yordam":
        await help_cmd(update, context)
        return

    if _looks_like_bulk_category_list(text):
        result_text = await _do_bulk_import(update.effective_user.id, text, CHIQIM)
        await update.message.reply_text(result_text, reply_markup=MAIN_KEYBOARD)
        return

    # "+" bilan boshlansa — bu DAROMAD (kirim), masalan "+500000 pensiya"
    if text.startswith("+"):
        income_text = text[1:].strip()
        if not income_text:
            await update.message.reply_text(
                "❌ \"+\" dan keyin summa va izoh yozing, masalan: `+500000 pensiya`",
                parse_mode="Markdown",
            )
            return
        await _register_transaction(update, context, income_text, source="text", kind=KIRIM)
        return

    await _register_transaction(update, context, text, source="text", kind=CHIQIM)


async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    voice_file = update.message.voice or update.message.audio
    if not voice_file:
        return

    status_msg = await update.message.reply_text("🎙 Ovozli xabar tinglanmoqda...")

    tg_file = await context.bot.get_file(voice_file.file_id)
    with tempfile.TemporaryDirectory() as tmp_dir:
        ogg_path = os.path.join(tmp_dir, "voice.ogg")
        await tg_file.download_to_drive(ogg_path)
        try:
            text = voice_module.transcribe(ogg_path)
        except Exception:
            logger.exception("Ovozni matnga o'girishda xato")
            await status_msg.edit_text("❌ Ovozni matnga o'girib bo'lmadi. Matn bilan urinib ko'ring.")
            return

    if not text:
        await status_msg.edit_text("❌ Gapni tushunolmadim. Aniqroq gapiring yoki matn bilan yozing.")
        return

    await status_msg.edit_text(f"🗣 Eshitildi: \"{text}\"")
    await _register_transaction(update, context, text, source="voice", kind=CHIQIM)


# ============================================================
#  Har oyning 1-sanasida avtomatik hisobot
# ============================================================

async def send_monthly_reports_job(context: ContextTypes.DEFAULT_TYPE):
    """Har kuni ishga tushadi, lekin faqat oyning 1-sanasida xabar yuboradi."""
    now = datetime.now()
    if now.day != 1:
        return
    py, pm = reports.prev_month(now.year, now.month)
    await _broadcast_monthly_report(context, py, pm)


async def _broadcast_monthly_report(context: ContextTypes.DEFAULT_TYPE, year: int, month: int):
    users = db.get_all_users()
    for user_id, chat_id in users:
        try:
            text = reports.monthly_full_report(user_id, year, month)
            await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
            chart = reports.monthly_chart(user_id, year, month, kind=CHIQIM)
            if chart:
                await context.bot.send_photo(chat_id=chat_id, photo=chart, caption="📊 Chiqimlar taqsimoti")
            income_chart = reports.monthly_chart(user_id, year, month, kind=KIRIM)
            if income_chart:
                await context.bot.send_photo(chat_id=chat_id, photo=income_chart, caption="💵 Kirimlar taqsimoti")
        except Exception:
            logger.exception(f"Avtomatik hisobot yuborishda xato (user_id={user_id})")


async def diagnostika_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bazaning holatini tekshirish uchun diagnostika."""
    user_id = update.effective_user.id
    db_path_env = os.getenv("DB_PATH", "(o'rnatilmagan, standart 'expenses.db' ishlatiladi)")
    resolved_path = db.DB_PATH
    exists = os.path.exists(resolved_path)
    size = os.path.getsize(resolved_path) if exists else 0

    chiqim_count = len(db.get_recent_expenses(user_id, kind=CHIQIM, limit=10000))
    kirim_count = len(db.get_recent_expenses(user_id, kind=KIRIM, limit=10000))
    custom_chiqim = len(db.get_custom_categories(user_id, kind=CHIQIM))
    custom_kirim = len(db.get_custom_categories(user_id, kind=KIRIM))
    all_users = db.get_all_users()

    exists_label = "✅ Ha" if exists else "❌ Yoq"
    text = (
        f"🔧 *Diagnostika*\n\n"
        f"DB\\_PATH (env): `{db_path_env}`\n"
        f"Haqiqiy fayl yo'li: `{resolved_path}`\n"
        f"Fayl mavjudmi: {exists_label}\n"
        f"Fayl hajmi: {size} bayt\n\n"
        f"Sizning yozuvlaringiz:\n"
        f"  📊 Chiqim: {chiqim_count} ta\n"
        f"  💵 Kirim: {kirim_count} ta\n"
        f"  🏷 Chiqim kategoriya: {custom_chiqim} ta\n"
        f"  🏷 Kirim kategoriya: {custom_kirim} ta\n\n"
        f"Ro'yxatdan o'tgan foydalanuvchilar: {len(all_users)} ta"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def test_monthly_report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Avtomatik hisobotni qo'lda sinash uchun (faqat shu foydalanuvchiga yuboradi)."""
    now = datetime.now()
    py, pm = reports.prev_month(now.year, now.month)
    await update.message.reply_text(
        f"🔧 Sinov: o'tgan oy ({reports.OY_NOMLARI[pm-1]} {py}) hisoboti shu tarzda yuboriladi:"
    )
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    text = reports.monthly_full_report(user_id, py, pm)
    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
    chart = reports.monthly_chart(user_id, py, pm, kind=CHIQIM)
    if chart:
        await context.bot.send_photo(chat_id=chat_id, photo=chart, caption="📊 Chiqimlar taqsimoti")
    income_chart = reports.monthly_chart(user_id, py, pm, kind=KIRIM)
    if income_chart:
        await context.bot.send_photo(chat_id=chat_id, photo=income_chart, caption="💵 Kirimlar taqsimoti")


# ============================================================
#  main()
# ============================================================

def main():
    if not TOKEN:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN topilmadi. .env faylini yarating "
            "(namuna uchun .env.example ga qarang) va tokeningizni kiriting."
        )

    db.init_db()

    # Botning "kutish holatlari" (masalan tugma bosgandan keyin summa
    # kutish) ham bazaviy fayl bilan bir xil doimiy diskda saqlanadi —
    # shunda bot qayta ishga tushsa ham (yangilanish, restart) yarim
    # qolgan amallar yo'qolmaydi.
    persistence_dir = os.path.dirname(db.DB_PATH) or "."
    persistence_path = os.path.join(persistence_dir, "bot_persistence.pickle")
    persistence = PicklePersistence(filepath=persistence_path)

    app = Application.builder().token(TOKEN).persistence(persistence).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("yangikategoriya", new_category_start)],
        states={
            CAT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_category_get_name)],
            SUBCAT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_category_get_subcat)],
            KEYWORDS: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_category_get_keywords)],
        },
        fallbacks=[CommandHandler("bekor", new_category_cancel)],
        conversation_timeout=300,
    )

    income_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("yangidaromadkategoriya", new_income_category_start)],
        states={
            CAT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_category_get_name)],
            SUBCAT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_category_get_subcat)],
            KEYWORDS: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_category_get_keywords)],
        },
        fallbacks=[CommandHandler("bekor", new_category_cancel)],
        conversation_timeout=300,
    )

    bulk_import_handler = ConversationHandler(
        entry_points=[CommandHandler("kategoriyayukla", bulk_import_start)],
        states={BULK_IMPORT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bulk_import_receive)]},
        fallbacks=[CommandHandler("bekor", new_category_cancel)],
        conversation_timeout=300,
    )

    bulk_import_income_handler = ConversationHandler(
        entry_points=[CommandHandler("daromadkategoriyayukla", bulk_import_income_start)],
        states={BULK_IMPORT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bulk_import_receive)]},
        fallbacks=[CommandHandler("bekor", new_category_cancel)],
        conversation_timeout=300,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("oylik", monthly_cmd))
    app.add_handler(CommandHandler("yillik", yearly_cmd))
    app.add_handler(CommandHandler("solishtir", compare_cmd))
    app.add_handler(CommandHandler("ochirish", delete_last_cmd))
    app.add_handler(CommandHandler("daromadochirish", delete_last_income_cmd))
    app.add_handler(CommandHandler("daromad", daromad_cmd))
    app.add_handler(CommandHandler("kategoriyalar", list_categories_cmd))
    app.add_handler(CommandHandler("kategoriyaochir", delete_category_cmd))
    app.add_handler(CommandHandler("kategoriyanomi", rename_category_cmd))
    app.add_handler(CommandHandler("daromadkategoriyalar", list_income_categories_cmd))
    app.add_handler(CommandHandler("daromadkategoriyaochir", delete_income_category_cmd))
    app.add_handler(CommandHandler("daromadkategoriyanomi", rename_income_category_cmd))
    app.add_handler(CommandHandler("avtomatiksinov", test_monthly_report_cmd))
    app.add_handler(CommandHandler("diagnostika", diagnostika_cmd))
    app.add_handler(CommandHandler("tahrirlash", edit_start))
    app.add_handler(CommandHandler("miqdortahrir", amount_edit_start))
    app.add_handler(conv_handler)
    app.add_handler(income_conv_handler)
    app.add_handler(bulk_import_handler)
    app.add_handler(bulk_import_income_handler)
    app.add_handler(CallbackQueryHandler(edit_button_handler, pattern=r"^ed[kcsa]:"))
    app.add_handler(CallbackQueryHandler(amount_edit_button_handler, pattern=r"^amt[ke]:"))
    app.add_handler(CallbackQueryHandler(category_button_handler))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, voice_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    # Har kuni 09:00 da tekshiradi, faqat 1-sanada haqiqiy xabar yuboradi
    app.job_queue.run_daily(send_monthly_reports_job, time=time(hour=9, minute=0), name="monthly_report_job")

    logger.info("Bot ishga tushdi...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
