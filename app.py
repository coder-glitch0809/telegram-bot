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


async def get_bot_application():
    global bot_app

    if bot_app:
        return bot_app

    async with bot_lock:
        if bot_app:
            return bot_app

        telegram_bot.require_config()
        telegram_bot.analytics = telegram_bot.AnalyticsStore(telegram_bot.ANALYTICS_DB_FILE)
        telegram_bot.sheets = telegram_bot.ExpenseSheets()
        bot_app = telegram_bot.build_application()
        await bot_app.initialize()
        await bot_app.start()
        return bot_app


@app.post("/telegram-webhook")
async def telegram_webhook(request: Request) -> dict[str, bool]:
    application = await get_bot_application()
    payload = await request.json()
    update = Update.de_json(payload, application.bot)
    if update is None:
        raise HTTPException(status_code=400, detail="Invalid Telegram update")

    await application.process_update(update)
    return {"ok": True}
