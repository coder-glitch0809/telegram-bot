import asyncio

from fastapi import FastAPI, HTTPException, Request
from telegram import Update

import bot as telegram_bot


app = FastAPI()
bot_app = None
bot_lock = asyncio.Lock()


@app.get("/")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "telegram-ai-bot"}


@app.get("/status")
async def status() -> dict[str, object]:
    return {
        "status": "ok",
        "telegram_token": bool(telegram_bot.TELEGRAM_BOT_TOKEN),
        "ai_provider": telegram_bot.AI_PROVIDER,
        "ai_model": telegram_bot.OPENAI_TEXT_MODEL,
        "ai_key": bool(telegram_bot.AI_API_KEY),
        "google_sheets": bool(
            telegram_bot.GOOGLE_SERVICE_ACCOUNT_JSON
            or telegram_bot.Path(telegram_bot.GOOGLE_SERVICE_ACCOUNT_FILE).exists()
        ),
        "payment_enabled": telegram_bot.PAYMENT_ENABLED,
    }


async def get_bot_application():
    global bot_app

    if bot_app:
        return bot_app

    async with bot_lock:
        if bot_app:
            return bot_app

        telegram_bot.require_config()
        telegram_bot.analytics = telegram_bot.AnalyticsStore(telegram_bot.ANALYTICS_DB_FILE)
        bot_app = telegram_bot.build_application()
        await bot_app.initialize()
        await telegram_bot.setup_bot_commands(bot_app)
        await bot_app.start()
        return bot_app


@app.get("/setup-webhook")
async def setup_webhook(url: str) -> dict[str, object]:
    application = await get_bot_application()
    ok = await application.bot.set_webhook(url=url, allowed_updates=Update.ALL_TYPES)
    return {"ok": ok, "webhook_url": url}


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
