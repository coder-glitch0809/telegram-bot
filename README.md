# AI Telegram Bot

Bu loyiha Telegram ichida to'liq AI yordamchi bot sifatida ishlaydi:

- uzbekcha, ruscha va inglizcha savol-javob;
- privat chatda matn va voice orqali AI javob;
- guruhlarda faqat `/ai` komandasi orqali AI javob;
- AI rasm generatsiyasi ochiq rejimda;
- o'qituvchi, o'quvchi va studentlar uchun konspekt, test, dars reja va prezentatsiya fayllari;
- Instagram va YouTube linklaridan audio yoki video tanlash;
- 18+ materiallarni rad etish;
- bot egasiga yangi foydalanuvchi xabari va haftalik foydalanuvchi/top so'rovlar hisoboti.

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
OPENAI_IMAGE_API_KEY=PASTE_OPENAI_IMAGE_KEY_HERE
IMAGE_GENERATION_ENABLED=true
IMAGE_MODEL=gpt-image-1
IMAGE_SIZE=1024x1024

MEDIA_DOWNLOAD_ENABLED=true
MEDIA_MAX_MB=45

OWNER_EMAIL=your_gmail@gmail.com
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_gmail@gmail.com
SMTP_PASSWORD=PASTE_GMAIL_APP_PASSWORD_HERE
SMTP_FROM_EMAIL=your_gmail@gmail.com
REPORT_WEEKLY_DAY=0
```

`OWNER_EMAIL` va `SMTP_USERNAME` joyiga Gmail manzilingiz yoziladi. Gmail uchun oddiy parol emas, Google App Password ishlating.

Rasm generatsiyasi OpenAI Images API orqali ishlaydi. Rasm uchun `OPENAI_IMAGE_API_KEY` ishlatiladi; bo'sh bo'lsa `OPENAI_API_KEY` fallback bo'ladi. Matn va voice AI uchun Groq yoki OpenAI ishlatishingiz mumkin.

Provider tanlashda key nomi mos bo'lishi kerak:

```env
AI_PROVIDER=groq
GROQ_API_KEY=gsk_...

AI_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

Excel uchun ro'yxat kerak bo'lsa, botga shunday yozing:

```text
Telefonlar ro'yxatini Excel uchun jadval qilib ber: nomi, narxi, izoh
```

Bot bunday so'rovda Excelga ko'chirish qulay bo'lgan tab bilan ajratilgan jadval qaytaradi.

## Ishga Tushirish

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python bot.py
```

## Vercel Webhook

Vercel Environment Variables ichiga `.env.example`dagi nomlarni kiriting. Custom domeningiz bo'lsa:

```env
PUBLIC_BASE_URL=https://sizning-domeningiz.uz
AUTO_SETUP_WEBHOOK=false
```

Custom domen bo'lmasa `PUBLIC_BASE_URL` bo'sh qolishi mumkin, Vercel `VERCEL_URL` orqali webhookni avtomatik yasaydi.

Deploydan keyin webhookni bir marta qo'lda ulang:

```text
https://YOUR-VERCEL-DOMAIN.vercel.app/setup-webhook?url=https://YOUR-VERCEL-DOMAIN.vercel.app/telegram-webhook
```

Yoki domenni envdan o'zi olishi uchun:

```text
https://YOUR-VERCEL-DOMAIN.vercel.app/setup-webhook
```

Tekshirish endpointlari:

```text
/dashboard        # Interactive HTML dashboard with Vercel Analytics
/status
/ai-health
/webhook-info
/cron/weekly
```

## Dashboard

Proyekt `/dashboard` endpointida interaktiv HTML dashboardga ega. Dashboard quyidagilarni ko'rsatadi:

- Bot holati va konfiguratsiya
- AI provider va model ma'lumotlari
- Webhook holati
- Tezkor havola tugmalari barcha API endpointlariga

Dashboard Vercel Web Analytics bilan integratsiya qilingan, shuning uchun Vercel Analytics dashboard orqali ziyorat statistikasini ko'rishingiz mumkin.

## Komandalar

```text
/start
/help
/ai savol
/image rasm prompti
/rasm rasm prompti
/present mavzu pptx
/prezentatsiya mavzu docx
/media audio LINK
/media video LINK
/yt_ol audio LINK
/yt_ol video LINK
/radar
/report
```

`/radar` va `/report` faqat `OWNER_TELEGRAM_ID` uchun ishlaydi.

## Muhim

Media yuklash funksiyasi faqat o'zingizga tegishli, ruxsat berilgan yoki qonunan yuklab olish mumkin bo'lgan kontent uchun ishlatilishi kerak. Bot 18+ va pornografik kontentni tarqatmaydi.
