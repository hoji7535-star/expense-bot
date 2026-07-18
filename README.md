# 💰 Shaxsiy Xarajatlar Hisobi — Telegram Bot

Matn yoki ovozli xabar orqali xarajat kiritish, kategoriya bo'yicha
avtomatik taqsimlash va oylik/yillik hisobotlarni ko'rish imkonini
beruvchi Telegram bot.

## Imkoniyatlar

- 💬 Matn orqali xarajat kiritish: `market 50000`, `taksiga 15 ming`
- 🎙 Ovozli xabar orqali kiritish (gapirib aytish yetarli)
- 🏷 Kategoriyalarga avtomatik ajratish (oziq-ovqat, transport, kiyim,
  kommunal, sog'liq, ko'ngilochar, ta'lim, boshqa)
- 📊 `/oylik` — joriy oy bo'yicha hisobot (kategoriya kesimida)
- 📆 `/yillik` — joriy yil bo'yicha hisobot
- ↩️ `/ochirish` — oxirgi kiritilgan xarajatni bekor qilish
- 🗄 Barcha ma'lumotlar mahalliy SQLite bazasida (`expenses.db`) saqlanadi

## O'rnatish

### 1. Talablar
- Python 3.10+
- ffmpeg (ovozli xabarlarni qayta ishlash uchun)

Ubuntu/Debian'da ffmpeg o'rnatish:
```bash
sudo apt update && sudo apt install -y ffmpeg
```

### 2. Loyihani tayyorlash
```bash
cd expense_bot
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Bot tokenini olish
1. Telegram'da [@BotFather](https://t.me/BotFather) bilan yozishing.
2. `/newbot` buyrug'ini yuboring va ko'rsatmalarga amal qiling.
3. Sizga beriladigan tokenni nusxalab oling.

### 4. Tokenni sozlash
```bash
cp .env.example .env
```
`.env` faylini oching va `TELEGRAM_BOT_TOKEN` qiymatini o'z tokeningizga
almashtiring.

### 5. Botni ishga tushirish
```bash
python bot.py
```
Konsolda `Bot ishga tushdi...` degan yozuv chiqsa — bot ishlayapti.
Endi Telegram'da botingizga o'ting va `/start` bosing.

## Doimiy ishlashi uchun (server/VPS)

Bot uzluksiz ishlashi uchun uni `systemd` xizmati yoki `screen`/`tmux`
sessiyasida, yoxud `pm2`/`supervisor` kabi vosita orqali fon rejimida
ishga tushiring. Masalan, oddiy `systemd` namunasi:

```ini
# /etc/systemd/system/expense-bot.service
[Unit]
Description=Xarajatlar hisobi Telegram bot
After=network.target

[Service]
WorkingDirectory=/uy/yoli/expense_bot
ExecStart=/uy/yoli/expense_bot/venv/bin/python bot.py
Restart=always
User=sizning_user

[Install]
WantedBy=multi-user.target
```
So'ng:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now expense-bot
```

## Fayllar tuzilishi

```
expense_bot/
├── bot.py           # Asosiy bot va handlerlar
├── database.py       # SQLite bilan ishlash
├── parser.py          # Matndan summa/kategoriya ajratish
├── reports.py          # Oylik/yillik hisobot yasash
├── voice.py             # Ovozni matnga o'girish (ffmpeg + SpeechRecognition)
├── requirements.txt
├── .env.example
└── README.md
```

## Eslatma

- Ovozni matnga o'girish uchun `SpeechRecognition` kutubxonasi Google'ning
  bepul Web Speech API'sidan foydalanadi — bu internet ulanishini talab
  qiladi va katta hajmda foydalanish uchun mo'ljallanmagan. Agar
  offline yoki professional darajadagi tanib olish kerak bo'lsa,
  `openai-whisper` yoki `faster-whisper` kutubxonalariga o'tish tavsiya
  etiladi (`voice.py` faylida almashtirish oson).
- Ma'lumotlar bazasi shu papkadagi `expenses.db` faylida saqlanadi;
  uni zaxiralashni unutmang.
