from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from types import ModuleType

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
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
        "next": ["/dashboard", "/status", "/ai-health", "/webhook-check", "/setup-webhook", "/force-webhook", "/webhook-info"],
    }


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request) -> str:
    """Interactive dashboard with Vercel Web Analytics."""
    try:
        bot = load_bot()
        bot_imported = True
        telegram_token = bool(bot.TELEGRAM_BOT_TOKEN)
        ai_provider = bot.AI_PROVIDER
        ai_model = bot.OPENAI_TEXT_MODEL
        bot_initialized = bot.bot_app is not None
        bot_init_error = bot.bot_init_error
        
        # Get webhook info
        try:
            application = await bot.get_bot_application()
            info = await application.bot.get_webhook_info()
            webhook_url = info.url
            webhook_pending = info.pending_update_count
            webhook_error = info.last_error_message or "None"
        except Exception:
            webhook_url = "Not set"
            webhook_pending = 0
            webhook_error = "Failed to fetch"
    except Exception as exc:
        bot_imported = False
        telegram_token = False
        ai_provider = "unknown"
        ai_model = "unknown"
        bot_initialized = False
        bot_init_error = str(exc)[:200]
        webhook_url = "N/A"
        webhook_pending = 0
        webhook_error = "N/A"
    
    base_url = configured_base_url(request)
    
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Telegram AI Bot Dashboard</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
            color: #333;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        header {{
            text-align: center;
            color: white;
            margin-bottom: 40px;
        }}
        h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
        }}
        .subtitle {{
            font-size: 1.2em;
            opacity: 0.9;
        }}
        .cards {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .card {{
            background: white;
            border-radius: 12px;
            padding: 25px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 8px 12px rgba(0,0,0,0.15);
        }}
        .card-header {{
            display: flex;
            align-items: center;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #f0f0f0;
        }}
        .card-icon {{
            font-size: 2em;
            margin-right: 10px;
        }}
        .card-title {{
            font-size: 1.3em;
            font-weight: 600;
            color: #667eea;
        }}
        .status-badge {{
            display: inline-block;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 0.9em;
            font-weight: 600;
            margin: 5px 0;
        }}
        .status-ok {{
            background: #d4edda;
            color: #155724;
        }}
        .status-error {{
            background: #f8d7da;
            color: #721c24;
        }}
        .info-row {{
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #f5f5f5;
        }}
        .info-row:last-child {{
            border-bottom: none;
        }}
        .info-label {{
            font-weight: 600;
            color: #666;
        }}
        .info-value {{
            color: #333;
            text-align: right;
            max-width: 60%;
            word-break: break-word;
        }}
        .links {{
            background: white;
            border-radius: 12px;
            padding: 25px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .links h2 {{
            color: #667eea;
            margin-bottom: 15px;
            font-size: 1.5em;
        }}
        .link-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 10px;
        }}
        .link-button {{
            display: block;
            padding: 12px 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            text-decoration: none;
            border-radius: 8px;
            text-align: center;
            font-weight: 600;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .link-button:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.2);
        }}
        footer {{
            text-align: center;
            color: white;
            margin-top: 40px;
            opacity: 0.8;
        }}
        .error-message {{
            background: #f8d7da;
            color: #721c24;
            padding: 10px;
            border-radius: 6px;
            margin-top: 10px;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🤖 Telegram AI Bot</h1>
            <p class="subtitle">Real-time Status Dashboard</p>
        </header>

        <div class="cards">
            <div class="card">
                <div class="card-header">
                    <span class="card-icon">🔧</span>
                    <h2 class="card-title">System Status</h2>
                </div>
                <div class="info-row">
                    <span class="info-label">Bot Imported:</span>
                    <span class="info-value">
                        <span class="status-badge {'status-ok' if bot_imported else 'status-error'}">
                            {'✓ OK' if bot_imported else '✗ Error'}
                        </span>
                    </span>
                </div>
                <div class="info-row">
                    <span class="info-label">Bot Initialized:</span>
                    <span class="info-value">
                        <span class="status-badge {'status-ok' if bot_initialized else 'status-error'}">
                            {'✓ Yes' if bot_initialized else '✗ No'}
                        </span>
                    </span>
                </div>
                <div class="info-row">
                    <span class="info-label">Telegram Token:</span>
                    <span class="info-value">
                        <span class="status-badge {'status-ok' if telegram_token else 'status-error'}">
                            {'✓ Set' if telegram_token else '✗ Missing'}
                        </span>
                    </span>
                </div>
                {f'<div class="error-message">Error: {bot_init_error}</div>' if bot_init_error else ''}
            </div>

            <div class="card">
                <div class="card-header">
                    <span class="card-icon">🤖</span>
                    <h2 class="card-title">AI Configuration</h2>
                </div>
                <div class="info-row">
                    <span class="info-label">Provider:</span>
                    <span class="info-value">{ai_provider}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Model:</span>
                    <span class="info-value">{ai_model}</span>
                </div>
            </div>

            <div class="card">
                <div class="card-header">
                    <span class="card-icon">🔗</span>
                    <h2 class="card-title">Webhook Status</h2>
                </div>
                <div class="info-row">
                    <span class="info-label">URL:</span>
                    <span class="info-value">{webhook_url if webhook_url else 'Not configured'}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Pending Updates:</span>
                    <span class="info-value">{webhook_pending}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Last Error:</span>
                    <span class="info-value">{webhook_error}</span>
                </div>
            </div>
        </div>

        <div class="links">
            <h2>🔗 Quick Links</h2>
            <div class="link-grid">
                <a href="{base_url}/status" class="link-button">📊 Status JSON</a>
                <a href="{base_url}/ai-health" class="link-button">🧠 AI Health</a>
                <a href="{base_url}/webhook-info" class="link-button">🔗 Webhook Info</a>
                <a href="{base_url}/webhook-check" class="link-button">✅ Check Webhook</a>
                <a href="{base_url}/setup-webhook" class="link-button">⚙️ Setup Webhook</a>
                <a href="{base_url}/cron/weekly" class="link-button">📈 Weekly Report</a>
            </div>
        </div>

        <footer>
            <p>Telegram AI Bot Dashboard • Powered by FastAPI & Vercel</p>
        </footer>
    </div>

    <!-- Vercel Web Analytics -->
    <script>
        window.va = window.va || function () {{ (window.vaq = window.vaq || []).push(arguments); }};
    </script>
    <script defer src="/_vercel/insights/script.js"></script>
</body>
</html>
"""


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
