import asyncio
import os

from fastapi import FastAPI, HTTPException, Request
from telegram import Update

import bot as telegram_bot


app = FastAPI()
bot_app = None
bot_lock = asyncio.Lock()
webhook_lock = asyncio.Lock()
webhook_ready = False


def clean_base_url(value: str) -> str:
    value = value.strip().rstrip("/")
    if not value:
        return ""
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    return value


def configured_base_url(request: Request | None = None) -> str:
    for key in ("PUBLIC_BASE_URL", "VERCEL_PROJECT_PRODUCTION_URL", "VERCEL_URL"):
        base_url = clean_base_url(os.getenv(key, ""))
        if base_url:
            return base_url
    if request:
        return clean_base_url(str(request.base_url))
    return ""


def webhook_url_for(request: Request | None = None, explicit_url: str | None = None) -> str:
    if explicit_url:
        return clean_base_url(explicit_url)
    base_url = configured_base_url(request)
    if not base_url:
        raise RuntimeError("PUBLIC_BASE_URL yoki VERCEL_URL topilmadi.")
    return f"{base_url}/telegram-webhook"


@app.get("/")
async def health_check(request: Request) -> dict[str, object]:
    return {
        "status": "ok",
        "service": "telegram-ai-bot",
        "base_url": configured_base_url(request),
        "webhook_url": webhook_url_for(request),
        "next": ["/status", "/ai-health", "/setup-webhook", "/webhook-info"],
    }


@app.get("/status")
async def status() -> dict[str, object]:
    return {
        "status": "ok",
        "telegram_token": bool(telegram_bot.TELEGRAM_BOT_TOKEN),
        "ai_provider": telegram_bot.AI_PROVIDER,
        "ai_model": telegram_bot.OPENAI_TEXT_MODEL,
        "transcribe_model": telegram_bot.OPENAI_TRANSCRIBE_MODEL,
        "ai_key": bool(telegram_bot.AI_API_KEY),
        "image_generation": telegram_bot.IMAGE_GENERATION_ENABLED,
        "image_free_limit": telegram_bot.IMAGE_FREE_LIMIT,
        "media_download": telegram_bot.MEDIA_DOWNLOAD_ENABLED,
        "payment_enabled": telegram_bot.PAYMENT_ENABLED,
        "analytics_db": telegram_bot.ANALYTICS_DB_FILE,
    }


@app.get("/ai-health")
async def ai_health() -> dict[str, object]:
    try:
        answer = await telegram_bot.ask_ai("Faqat bitta so'z bilan javob ber: OK")
        return {
            "ok": True,
            "provider": telegram_bot.AI_PROVIDER,
            "model": telegram_bot.OPENAI_TEXT_MODEL,
            "answer": answer[:100],
        }
    except Exception as exc:
        telegram_bot.logger.exception("AI health check failed")
        return {
            "ok": False,
            "provider": telegram_bot.AI_PROVIDER,
            "model": telegram_bot.OPENAI_TEXT_MODEL,
            "error": str(exc),
        }


async def get_bot_application():
    global bot_app

    if bot_app:
        return bot_app


async def ensure_webhook(request: Request | None = None, explicit_url: str | None = None) -> dict[str, object]:
    global webhook_ready

    async with webhook_lock:
        application = await get_bot_application()
        url = webhook_url_for(request, explicit_url)
        info = await application.bot.get_webhook_info()
        if info.url == url:
            webhook_ready = True
            return {"ok": True, "webhook_url": url, "already_set": True}
        ok = await application.bot.set_webhook(url=url, allowed_updates=Update.ALL_TYPES, drop_pending_updates=False)
        webhook_ready = bool(ok)
        return {"ok": ok, "webhook_url": url, "already_set": False}


@app.on_event("startup")
async def auto_setup_webhook_on_startup() -> None:
    if os.getenv("AUTO_SETUP_WEBHOOK", "true").strip().lower() not in {"1", "true", "yes", "ha"}:
        return
    if not telegram_bot.TELEGRAM_BOT_TOKEN:
        return
    try:
        await ensure_webhook()
    except Exception:
        telegram_bot.logger.exception("Automatic webhook setup skipped")

    async with bot_lock:
        if bot_app:
            return bot_app

        telegram_bot.require_config()
        telegram_bot.analytics = telegram_bot.AnalyticsStore(telegram_bot.ANALYTICS_DB_FILE)
        bot_app = telegram_bot.build_application()
        await bot_app.initialize()
        await telegram_bot.setup_bot_commands(bot_app)
        if not bot_app.running:
            await bot_app.start()
        return bot_app


@app.get("/setup-webhook")
async def setup_webhook(request: Request, url: str | None = None) -> dict[str, object]:
    return await ensure_webhook(request, url)


@app.get("/auto-webhook")
async def auto_webhook(request: Request) -> dict[str, object]:
    return await ensure_webhook(request)


@app.get("/webhook-info")
async def webhook_info() -> dict[str, object]:
    application = await get_bot_application()
    info = await application.bot.get_webhook_info()
    return {
        "url": info.url,
        "pending_update_count": info.pending_update_count,
        "last_error_date": info.last_error_date.isoformat() if info.last_error_date else None,
        "last_error_message": info.last_error_message,
    }


@app.get("/cron/weekly")
async def weekly_cron() -> dict[str, object]:
    telegram_bot.get_analytics()
    application = await get_bot_application()
    await telegram_bot.maybe_send_reports(application)
    return {"ok": True, "message": "weekly reports checked"}


@app.post("/telegram-webhook")
async def telegram_webhook(request: Request) -> dict[str, bool]:
    try:
        application = await get_bot_application()
        payload = await request.json()
        update = Update.de_json(payload, application.bot)
        if update is None:
            raise HTTPException(status_code=400, detail="Invalid Telegram update")

        await application.process_update(update)
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as exc:
        telegram_bot.logger.exception("Webhook update failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
