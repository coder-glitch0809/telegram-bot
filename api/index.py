from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from types import ModuleType

from fastapi import FastAPI, HTTPException, Request
from telegram import Update


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

app = FastAPI()
bot_module: ModuleType | None = None
bot_import_error = ""


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


def load_bot() -> ModuleType:
    global bot_module, bot_import_error

    if bot_module:
        return bot_module
    try:
        bot_module = importlib.import_module("bot")
        bot_import_error = ""
        return bot_module
    except Exception as exc:
        bot_import_error = str(exc)[:700]
        raise


@app.get("/")
async def health_check(request: Request) -> dict[str, object]:
    return {
        "status": "ok",
        "service": "telegram-ai-bot",
        "entrypoint": "api/index.py",
        "bot_runtime": "bot.py",
        "base_url": configured_base_url(request),
        "webhook_url": webhook_url_for(request),
        "next": ["/status", "/ai-health", "/webhook-check", "/setup-webhook", "/force-webhook", "/webhook-info"],
    }


@app.get("/favicon.ico")
@app.get("/favicon.png")
async def favicon() -> dict[str, bool]:
    return {"ok": True}


@app.get("/status")
async def status() -> dict[str, object]:
    try:
        bot = load_bot()
    except Exception as exc:
        return {
            "status": "error",
            "entrypoint": "api/index.py",
            "bot_runtime": "bot.py",
            "bot_imported": False,
            "bot_import_error": str(exc)[:700],
        }

    missing_config = []
    if not bot.TELEGRAM_BOT_TOKEN:
        missing_config.append("TELEGRAM_BOT_TOKEN")
    if not bot.AI_API_KEY:
        missing_config.append("GROQ_API_KEY yoki GEMINI_API_KEY yoki OPENAI_API_KEY")
    return {
        "status": "ok",
        "entrypoint": "api/index.py",
        "bot_runtime": "bot.py",
        "bot_imported": True,
        "telegram_token": bool(bot.TELEGRAM_BOT_TOKEN),
        "ai_provider": bot.AI_PROVIDER,
        "ai_model": bot.OPENAI_TEXT_MODEL,
        "transcribe_model": bot.OPENAI_TRANSCRIBE_MODEL,
        "ai_key": bool(bot.AI_API_KEY),
        "image_generation": bot.IMAGE_GENERATION_ENABLED,
        "image_free_limit": bot.IMAGE_FREE_LIMIT,
        "media_download": bot.MEDIA_DOWNLOAD_ENABLED,
        "payment_enabled": bot.PAYMENT_ENABLED,
        "analytics_db": bot.ANALYTICS_DB_FILE,
        "missing_config": missing_config,
        "bot_initialized": bot.bot_app is not None,
        "bot_init_error": bot.bot_init_error,
    }


@app.get("/ai-health")
async def ai_health() -> dict[str, object]:
    try:
        bot = load_bot()
        answer = await bot.ask_ai("Faqat bitta so'z bilan javob ber: OK")
        return {"ok": True, "provider": bot.AI_PROVIDER, "model": bot.OPENAI_TEXT_MODEL, "answer": answer[:100]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:700]}


@app.get("/setup-webhook")
async def setup_webhook(request: Request, url: str | None = None) -> dict[str, object]:
    try:
        bot = load_bot()
        return await bot.ensure_webhook(request, url)
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc)[:700],
            "hint": "Vercel Environment Variables ichida TELEGRAM_BOT_TOKEN va AI key nomlarini tekshiring.",
        }


@app.get("/force-webhook")
async def force_webhook(request: Request, url: str | None = None) -> dict[str, object]:
    try:
        bot = load_bot()
        return await bot.force_webhook(request, url)
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:700]}


@app.get("/webhook-info")
async def webhook_info() -> dict[str, object]:
    try:
        bot = load_bot()
        application = await bot.get_bot_application()
        info = await application.bot.get_webhook_info()
        return {
            "ok": True,
            "url": info.url,
            "pending_update_count": info.pending_update_count,
            "last_error_date": info.last_error_date.isoformat() if info.last_error_date else None,
            "last_error_message": info.last_error_message,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:700]}


@app.get("/webhook-check")
async def webhook_check(request: Request) -> dict[str, object]:
    expected_url = webhook_url_for(request)
    try:
        bot = load_bot()
        application = await bot.get_bot_application()
        info = await application.bot.get_webhook_info()
        current_url = info.url
        return {
            "ok": current_url == expected_url,
            "expected_url": expected_url,
            "current_url": current_url,
            "needs_setup": current_url != expected_url,
            "fix_url": f"{configured_base_url(request)}/setup-webhook",
            "pending_update_count": info.pending_update_count,
            "last_error_date": info.last_error_date.isoformat() if info.last_error_date else None,
            "last_error_message": info.last_error_message,
        }
    except Exception as exc:
        return {"ok": False, "expected_url": expected_url, "error": str(exc)[:700]}


@app.get("/cron/weekly")
async def weekly_cron() -> dict[str, object]:
    bot = load_bot()
    bot.get_analytics()
    application = await bot.get_bot_application()
    await bot.maybe_send_reports(application)
    return {"ok": True, "message": "weekly reports checked"}


@app.post("/telegram-webhook")
async def telegram_webhook(request: Request) -> dict[str, bool]:
    try:
        print("telegram_webhook: POST received", flush=True)
        bot = load_bot()
        application = await bot.get_bot_application()
        payload = await request.json()
        update = Update.de_json(payload, application.bot)
        if update is None:
            raise HTTPException(status_code=400, detail="Invalid Telegram update")
        await application.process_update(update)
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)[:700]) from exc
