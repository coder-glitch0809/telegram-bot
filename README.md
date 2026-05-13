# AI Telegram Bot

Bu loyiha Telegram ichida to'liq AI yordamchi bot sifatida ishlaydi:

- uzbekcha, ruscha va inglizcha savol-javob;
- privat chatda matn va voice orqali AI javob;
- guruhlarda faqat `/ai` komandasi orqali AI javob;
- AI rasm generatsiyasi, har foydalanuvchiga 10 ta bepul;
- Instagram va YouTube linklaridan audio yoki video tanlash;
- 18+ materiallarni rad etish;
- bot egasiga haftalik foydalanuvchi va top so'rovlar hisoboti.

## Kalitlar

Hech qachon API token yoki Google/Telegram kalitlarini kodga yozmang. Hammasi `.env` yoki hosting Environment Variables ichida turadi.

Minimal sozlama:

```env
TELEGRAM_BOT_TOKEN=PASTE_TELEGRAM_TOKEN_HERE
OWNER_TELEGRAM_ID=123456789

AI_PROVIDER=groq
GROQ_API_KEY=PASTE_GROQ_KEY_HERE
AI_BASE_URL=https://api.groq.com/openai/v1
OPENAI_TEXT_MODEL=llama-3.3-70b-versatile
OPENAI_TRANSCRIBE_MODEL=whisper-large-v3

OPENAI_API_KEY=PASTE_OPENAI_KEY_HERE
IMAGE_GENERATION_ENABLED=true
IMAGE_MODEL=gpt-image-1
IMAGE_SIZE=1024x1024
IMAGE_FREE_LIMIT=10

MEDIA_DOWNLOAD_ENABLED=true
MEDIA_MAX_MB=45

PAYMENT_ENABLED=true
PAYMENT_PROVIDER=manual
PAYMENT_OWNER_CONTACT=@username_yoki_telefon
PAYMENT_PLANS=pro:49000:10 tadan keyingi rasm generatsiyasi;business:149000:Jamoa va kanal uchun
PREMIUM_USER_IDS=

OWNER_EMAIL=your_gmail@gmail.com
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_gmail@gmail.com
SMTP_PASSWORD=PASTE_GMAIL_APP_PASSWORD_HERE
SMTP_FROM_EMAIL=your_gmail@gmail.com
REPORT_WEEKLY_DAY=0
```

`OWNER_EMAIL` va `SMTP_USERNAME` joyiga Gmail manzilingiz yoziladi. Gmail uchun oddiy parol emas, Google App Password ishlating.

Rasm generatsiyasi OpenAI Images API orqali ishlaydi, shuning uchun `OPENAI_API_KEY` alohida kerak. Matn AI uchun Groq/Gemini/xAI/OpenAI ishlatishingiz mumkin.

## Ishga Tushirish

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python bot.py
```

## Vercel Webhook

Vercel Environment Variables ichiga `.env`dagi qiymatlarni kiriting. Deploydan keyin webhook:

```text
https://YOUR-VERCEL-DOMAIN.vercel.app/setup-webhook?url=https://YOUR-VERCEL-DOMAIN.vercel.app/telegram-webhook
```

Tekshirish endpointlari:

```text
/status
/ai-health
/webhook-info
/cron/weekly
```

## Komandalar

```text
/start
/help
/ai savol
/image rasm prompti
/rasm rasm prompti
/media audio LINK
/media video LINK
/yt_ol audio LINK
/yt_ol video LINK
/payment
/radar
/report
```

`/radar` va `/report` faqat `OWNER_TELEGRAM_ID` uchun ishlaydi.

## Muhim

Media yuklash funksiyasi faqat o'zingizga tegishli, ruxsat berilgan yoki qonunan yuklab olish mumkin bo'lgan kontent uchun ishlatilishi kerak. Bot 18+ va pornografik kontentni tarqatmaydi.
