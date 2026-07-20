"""
bot.py — Shaxsiy xarajatlar hisobi Telegram boti.

Ishga tushirish:
    1. .env faylida TELEGRAM_BOT_TOKEN ni kiriting (.env.example ga qarang)
    2. pip install -r requirements.txt
    3. ffmpeg o'rnatilganiga ishonch hosil qiling (apt install ffmpeg)
    4. python bot.py

Buyruqlar:
    /start          - botni ishga tushirish, yo'riqnoma
    /help           - yordam
    /oylik          - joriy oy hisobot
    /yillik         - joriy yil hisobot
    /ochirish       - oxirgi kiritilgan xarajatni o'chirish
    Matn xabar      - "market 50000" kabi yozib xarajat kiritish
    Ovozli xabar    - gapirib xarajat kiritish ("taksiga o'n besh ming so'm")
"""
import logging
import os
import tempfile
from datetime import datetime

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
)

import database as db
import reports
import voice as voice_module
from parser import parse_expense_text

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
        ["🏷 Kategoriyalar", "↩️ Oxirgisini o'chirish"],
        ["ℹ️ Yordam"],
    ],
    resize_keyboard=True,
)

# /yangikategoriya suhbat holatlari
CAT_NAME, SUBCAT_NAME, KEYWORDS = range(3)
# /kategoriyayukla suhbat holati
BULK_IMPORT = 3


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 Salom! Men shaxsiy xarajatlar hisobi botiman.\n\n"
        "💬 *Matn bilan* xarajat kiriting, masalan:\n"
        "   `market 50000`\n"
        "   `taksiga 15 ming`\n"
        "   `kino uchun 30000 so'm`\n\n"
        "🎙 *Ovozli xabar* yuborib ham xarajat kirita olasiz — shunchaki gapiring.\n\n"
        "📊 /oylik — joriy oy hisoboti (matn + diagramma)\n"
        "📆 /yillik — joriy yil hisoboti (matn + diagramma)\n"
        "↩️ /ochirish — oxirgi yozuvni o'chirish\n\n"
        "🏷 *Kategoriyalar:*\n"
        "   /kategoriyalar — ro'yxatni ko'rish\n"
        "   /yangikategoriya — bitta-bitta kategoriya qo'shish\n"
        "   /kategoriyayukla — ro'yxatni bir martada yuklash\n"
        "   /kategoriyanomi — nomini o'zgartirish\n"
        "   /kategoriyaochir — o'chirish\n\n"
        "❓ Kategoriya aniqlanmasa, bot tugmalar orqali tanlashni so'raydi."
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def monthly_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    user_id = update.effective_user.id
    text = reports.monthly_report(user_id, now.year, now.month)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)
    chart = reports.monthly_chart(user_id, now.year, now.month)
    if chart:
        await update.message.reply_photo(photo=chart)


async def yearly_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    user_id = update.effective_user.id
    text = reports.yearly_report(user_id, now.year)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)
    chart = reports.yearly_chart(user_id, now.year)
    if chart:
        await update.message.reply_photo(photo=chart)


async def delete_last_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ok = db.delete_last_expense(user_id)
    if ok:
        await update.message.reply_text("✅ Oxirgi xarajat o'chirildi.", reply_markup=MAIN_KEYBOARD)
    else:
        await update.message.reply_text("Hozircha o'chiriladigan xarajat yo'q.", reply_markup=MAIN_KEYBOARD)


async def list_categories_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from parser import CATEGORY_TREE

    lines = ["🏷 *Standart kategoriyalar:*\n"]
    for cat, subs in CATEGORY_TREE.items():
        emoji = reports.CATEGORY_EMOJI.get(cat, "📦")
        lines.append(f"{emoji} *{cat}*: " + ", ".join(subs.keys()))

    user_id = update.effective_user.id
    custom = db.get_custom_categories(user_id)
    if custom:
        lines.append("\n✨ *Siz qo'shgan kategoriyalar:*\n")
        seen = {}
        for cat, sub, _ in custom:
            seen.setdefault(cat, []).append(sub)
        for cat, subs in seen.items():
            lines.append(f"📌 *{cat}*: " + ", ".join(subs))
    else:
        lines.append(
            "\nO'zingizga xos kategoriya qo'shish uchun /yangikategoriya buyrug'ini ishlating."
        )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)


# ---- /yangikategoriya suhbat oqimi ----

async def new_category_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🆕 Yangi kategoriya yaratamiz.\n\n"
        "1-qadam: Kategoriya nomini kiriting (masalan: `Sport`, `Uy hayvonlari`)",
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
    db.add_custom_category(user_id, cat, subcat, keywords)
    await update.message.reply_text(
        f"✅ Yangi kategoriya qo'shildi: 📌 *{cat}* → {subcat}\n\n"
        f"Endi matnda shu kalit so'zlardan biri ishlatilsa, xarajat shu kategoriyaga tushadi.",
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD,
    )
    return ConversationHandler.END


async def new_category_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("new_cat_name", None)
    context.user_data.pop("new_cat_subcat", None)
    await update.message.reply_text("❌ Bekor qilindi.", reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


async def delete_category_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text(
            "Kategoriya nomini ko'rsating, masalan:\n`/kategoriyaochir Sport`",
            parse_mode="Markdown",
        )
        return
    cat_name = " ".join(context.args)
    ok = db.delete_custom_category(user_id, cat_name)
    if ok:
        await update.message.reply_text(f"✅ \"{cat_name}\" kategoriyasi o'chirildi.", reply_markup=MAIN_KEYBOARD)
    else:
        await update.message.reply_text(
            f"\"{cat_name}\" nomli o'zingiz qo'shgan kategoriya topilmadi.\n"
            "Eslatma: standart kategoriyalarni o'chirib bo'lmaydi.",
            reply_markup=MAIN_KEYBOARD,
        )


async def rename_category_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    full_text = " ".join(context.args)
    if "|" not in full_text:
        await update.message.reply_text(
            "Format: `/kategoriyanomi Eski nomi | Yangi nomi`\n"
            "Masalan: `/kategoriyanomi Wife | Xotinim`",
            parse_mode="Markdown",
        )
        return
    old_name, new_name = [p.strip() for p in full_text.split("|", 1)]
    ok = db.rename_custom_category(user_id, old_name, new_name)
    if ok:
        await update.message.reply_text(
            f"✅ \"{old_name}\" → \"{new_name}\" deb o'zgartirildi (avvalgi xarajatlar ham yangilandi).",
            reply_markup=MAIN_KEYBOARD,
        )
    else:
        await update.message.reply_text(
            f"\"{old_name}\" nomli o'zingiz qo'shgan kategoriya topilmadi.",
            reply_markup=MAIN_KEYBOARD,
        )


# ---- /kategoriyayukla — bir martada ko'p kategoriya import qilish ----

async def bulk_import_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Kategoriyalar ro'yxatini yuboring. Har bir qatorda:\n"
        "`Kategoriya: subkategoriya1, subkategoriya2, ...`\n\n"
        "Masalan:\n"
        "```\n"
        "Muhammad Umar: bogcha, dori, kiyim, oyinchoq, ovqat, boshqa\n"
        "Hadicha: bogcha, dori, kiyim, oyinchoq, ovqat, PAMPERS, boshqa\n"
        "Avto: gaz, benzin, moyka, boshqa\n"
        "```\n"
        "Bekor qilish uchun /bekor yozing.",
        parse_mode="Markdown",
    )
    return BULK_IMPORT


async def bulk_import_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lines = update.message.text.strip().splitlines()
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
            db.add_custom_category(user_id, category, sub, [sub])
            added.append(f"{category} → {sub}")

    if not added:
        await update.message.reply_text(
            "❌ Hech qanday kategoriya qo'shilmadi. Format: `Kategoriya: sub1, sub2`",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    summary = f"✅ {len(added)} ta subkategoriya qo'shildi.\n"
    if errors:
        summary += f"\n⚠️ {len(errors)} qator formatga mos kelmadi va o'tkazib yuborildi."
    await update.message.reply_text(summary, reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


def _all_category_names(user_id: int):
    """Foydalanuvchining custom + standart kategoriya nomlari ro'yxati."""
    from parser import CATEGORY_TREE
    custom_grouped = db.get_custom_categories_grouped(user_id)
    names = list(custom_grouped.keys()) + [c for c in CATEGORY_TREE.keys() if c not in custom_grouped]
    return names, custom_grouped


def _subcats_for(category: str, custom_grouped: dict):
    from parser import CATEGORY_TREE
    if category in custom_grouped:
        return custom_grouped[category]
    if category in CATEGORY_TREE:
        return list(CATEGORY_TREE[category].keys())
    return ["boshqa"]


async def _ask_category(update: Update, context: ContextTypes.DEFAULT_TYPE, amount, note, source):
    user_id = update.effective_user.id
    names, _ = _all_category_names(user_id)
    context.user_data["pending"] = {"amount": amount, "note": note, "source": source}
    context.user_data["cat_choices"] = names

    buttons = [
        [InlineKeyboardButton(f"{reports.CATEGORY_EMOJI.get(n, '📌')} {n}", callback_data=f"cat:{i}")]
        for i, n in enumerate(names)
    ]
    buttons.append([InlineKeyboardButton("📦 Boshqa", callback_data="cat:boshqa")])

    await update.message.reply_text(
        f"💰 {amount:,.0f} so'm — qaysi kategoriyaga tegishli?".replace(",", " "),
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def category_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    data = query.data

    if data.startswith("cat:"):
        choice = data.split(":", 1)[1]
        if choice == "boshqa":
            category = "boshqa"
        else:
            names = context.user_data.get("cat_choices", [])
            idx = int(choice)
            category = names[idx] if idx < len(names) else "boshqa"

        _, custom_grouped = _all_category_names(user_id)
        subs = _subcats_for(category, custom_grouped)
        context.user_data["chosen_category"] = category
        context.user_data["sub_choices"] = subs

        buttons = [
            [InlineKeyboardButton(s, callback_data=f"sub:{i}")]
            for i, s in enumerate(subs)
        ]
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
            await query.edit_message_text("❌ Xatolik: xarajat topilmadi, qayta urinib ko'ring.")
            return

        db.add_expense(
            user_id, pending["amount"], category, subcategory, pending["note"], source=pending["source"]
        )
        emoji = reports.CATEGORY_EMOJI.get(category, "📌")
        await query.edit_message_text(
            f"✅ Qayd etildi: {emoji} *{category}* → {subcategory} — "
            f"{pending['amount']:,.0f} so'm".replace(",", " "),
            parse_mode="Markdown",
        )
        context.user_data.pop("cat_choices", None)
        context.user_data.pop("sub_choices", None)
        context.user_data.pop("chosen_category", None)


async def _register_expense(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, source: str):
    user_id = update.effective_user.id
    custom_categories = db.get_custom_categories(user_id)
    amount, category, subcategory, note = parse_expense_text(text, custom_categories)

    if amount is None:
        await update.message.reply_text(
            "❌ Summani aniqlay olmadim. Iltimos, raqam bilan yozing, "
            "masalan: `market 50000` yoki `taksiga 15 ming`.",
            parse_mode="Markdown",
        )
        return

    # Kategoriya avtomatik aniqlanmadi — tugmalar orqali so'raymiz
    if category == "boshqa" and subcategory == "boshqa":
        await _ask_category(update, context, amount=amount, note=note, source=source)
        return

    db.add_expense(user_id, amount, category, subcategory, note, source=source)
    emoji = reports.CATEGORY_EMOJI.get(category, "📦")
    sub_line = f"\n🏷 {subcategory}" if subcategory != "boshqa" else ""
    await update.message.reply_text(
        f"✅ Qayd etildi: {emoji} *{category}* — {amount:,.0f} so'm".replace(",", " ")
        + sub_line
        + f"\n📝 {note}",
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD,
    )


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    # Klaviatura tugmalari
    if text == "📊 Oylik hisobot":
        await monthly_cmd(update, context)
        return
    if text == "📆 Yillik hisobot":
        await yearly_cmd(update, context)
        return
    if text == "↩️ Oxirgisini o'chirish":
        await delete_last_cmd(update, context)
        return
    if text == "🏷 Kategoriyalar":
        await list_categories_cmd(update, context)
        return
    if text == "ℹ️ Yordam":
        await help_cmd(update, context)
        return

    await _register_expense(update, context, text, source="text")


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
        except Exception as e:
            logger.exception("Ovozni matnga o'girishda xato")
            await status_msg.edit_text(
                "❌ Ovozni matnga o'girib bo'lmadi. Iltimos, matn bilan urinib ko'ring."
            )
            return

    if not text:
        await status_msg.edit_text(
            "❌ Gapni tushunolmadim. Iltimos, aniqroq gapiring yoki matn bilan yozing."
        )
        return

    await status_msg.edit_text(f"🗣 Eshitildi: \"{text}\"")
    await _register_expense(update, context, text, source="voice")


def main():
    if not TOKEN:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN topilmadi. .env faylini yarating "
            "(namuna uchun .env.example ga qarang) va tokeningizni kiriting."
        )

    db.init_db()

    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("yangikategoriya", new_category_start)],
        states={
            CAT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_category_get_name)],
            SUBCAT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_category_get_subcat)],
            KEYWORDS: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_category_get_keywords)],
        },
        fallbacks=[CommandHandler("bekor", new_category_cancel)],
    )

    bulk_import_handler = ConversationHandler(
        entry_points=[CommandHandler("kategoriyayukla", bulk_import_start)],
        states={
            BULK_IMPORT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bulk_import_receive)],
        },
        fallbacks=[CommandHandler("bekor", new_category_cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("oylik", monthly_cmd))
    app.add_handler(CommandHandler("yillik", yearly_cmd))
    app.add_handler(CommandHandler("ochirish", delete_last_cmd))
    app.add_handler(CommandHandler("kategoriyalar", list_categories_cmd))
    app.add_handler(CommandHandler("kategoriyaochir", delete_category_cmd))
    app.add_handler(CommandHandler("kategoriyanomi", rename_category_cmd))
    app.add_handler(conv_handler)
    app.add_handler(bulk_import_handler)
    app.add_handler(CallbackQueryHandler(category_button_handler))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, voice_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    logger.info("Bot ishga tushdi...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
