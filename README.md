# AI Telegram Bot + Google Sheets Xarajatlar

Bu loyiha Telegram bot orqali AI bilan ishlash, ovozli yoki matnli xarajatlarni Google Sheets ga yozish va oy oxirida Excel hisobot olish uchun tayyorlangan.

## 1. Kalitlarni joylash

`.env.example` faylidan nusxa oling va nomini `.env` qiling.

Eng muhim joy shu:

```env
TELEGRAM_BOT_TOKEN=PASTE_TELEGRAM_BOT_TOKEN_HERE
GROK_API_KEY=PASTE_GROK_API_KEY_HERE
AI_BASE_URL=https://api.x.ai/v1
```

Telegram bot tokenini `@BotFather` beradi. Grok API key esa xAI console ichidan olinadi.

## 2. Google Sheets ulash

Google Cloud da Service Account yarating va JSON credential faylini shu papkaga `google-service-account.json` nomi bilan qo'ying.

`.env` ichida:

```env
GOOGLE_SERVICE_ACCOUNT_FILE=google-service-account.json
SHARE_SPREADSHEET_WITH_EMAIL=sizning_gmailingiz@gmail.com
```

Bot har bir foydalanuvchi uchun alohida spreadsheet ochadi:

```text
Telegram Expenses - USER_ID
```

Har oy alohida worksheet bo'ladi, masalan `2026-05`.

## 3. O'zingizni xarajat yozuvchi qilish

Botni ishga tushirgandan keyin Telegramda `/start` yozing. Bot sizga user ID chiqaradi. Shu ID ni `.env` ga yozing:

```env
EXPENSE_ALLOWED_USER_IDS=123456789
```

Bu qiymat bo'sh qolsa, hech kim xarajat yoza olmaydi. Xavfsiz variant: o'zingizning ID ingizni yozib qo'yish.

## 4. Ishga tushirish

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python bot.py
```

## 5. Vercelga deploy qilish

Vercel Python entrypoint qidiradi, shuning uchun loyiha ichida `app.py` bor. Vercelda Environment Variables qilib quyidagilarni qo'shing:

```env
TELEGRAM_BOT_TOKEN=...
GROK_API_KEY=...
AI_BASE_URL=https://api.x.ai/v1
GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account",...}
GOOGLE_DRIVE_PARENT_FOLDER_ID=...
SHARE_SPREADSHEET_WITH_EMAIL=...
EXPENSE_ALLOWED_USER_IDS=...
OWNER_EMAIL=...
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=...
SMTP_PASSWORD=...
SMTP_FROM_EMAIL=...
```

Deploydan keyin Telegram webhookni Vercel domeningizga ulang:

```text
https://api.telegram.org/botBOT_TOKEN/setWebhook?url=https://YOUR-VERCEL-DOMAIN.vercel.app/telegram-webhook
```

Vercelda polling (`python bot.py`) ishlatilmaydi; u faqat lokal yoki doimiy server uchun.

## 6. Bot buyruqlari

```text
/start
/help
/ai savolingiz
/expense 25000 taksi
/month
/month 2026-05
/report
/report month
```

Ovozli xarajat yuborsangiz, bot avval ovozni matnga aylantiradi, keyin xarajatni Google Sheets ga yozadi.

## 7. Foydalanuvchi statistikasi va email hisobot

Bot hammaga ochiq: kim `/start` bossa yoki oddiy savol yozsa AI bilan ishlata oladi. Har bir foydalanuvchi va so'rov qisqacha `bot_analytics.sqlite3` bazaga yoziladi:

- Telegram user ID, username, birinchi va oxirgi faollik;
- AI so'rovlari, voice, xarajat va report buyruqlari soni;
- oxirgi so'rovlarning qisqa matn preview qismi.

Email hisobot uchun `.env` ichida SMTP sozlamalarini to'ldiring:

```env
OWNER_EMAIL=sizning_emailingiz@gmail.com
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=sizning_emailingiz@gmail.com
SMTP_PASSWORD=PASTE_EMAIL_APP_PASSWORD_HERE
SMTP_FROM_EMAIL=sizning_emailingiz@gmail.com
REPORT_WEEKLY_DAY=0
```

Bot haftada bir marta qisqa faollik hisobotini, har oyning 1-kuni esa oldingi oy bo'yicha umumiy hisobotni emailga yuboradi. Gmail uchun `SMTP_PASSWORD` sifatida Google App Password ishlating.

## 8. Keyinchalik payment ulash

Obunachilar ko'payganda to'lov tizimi uchun quyidagi joy kengaytiriladi:

- foydalanuvchi bazasi;
- subscription status;
- payment provider webhook;
- AI so'rovlar limitlari;
- faqat to'laganlarga AI ishlatish.

Hozirgi kodda oddiy foydalanuvchilar AI bilan ishlay oladi, xarajat yozish esa `EXPENSE_ALLOWED_USER_IDS` orqali cheklanadi.
# telegram-bot
