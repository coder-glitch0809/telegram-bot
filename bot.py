import asyncio
import json
import logging
import os
import smtplib
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from openai import OpenAI
from openpyxl import Workbook
from telegram import Update
from telegram.constants import ChatAction
from telegram import BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters


load_dotenv()

# ============================================================
# API KALITLAR .env FAYLIDA YONMA-YON TURADI:
# TELEGRAM_BOT_TOKEN=...
# OPENAI_API_KEY=...
# Bu yerga kalit yozmang, .env fayliga yozing.
# ============================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
GROK_API_KEY = os.getenv("GROK_API_KEY", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
AI_API_KEY = GROK_API_KEY or GROQ_API_KEY or OPENAI_API_KEY
AI_PROVIDER = os.getenv("AI_PROVIDER", "xai" if GROK_API_KEY else "groq" if GROQ_API_KEY else "openai").strip().lower()
DEFAULT_AI_BASE_URL = {
    "xai": "https://api.x.ai/v1",
    "groq": "https://api.groq.com/openai/v1",
    "openai": "",
}.get(AI_PROVIDER, "")
AI_BASE_URL = os.getenv("AI_BASE_URL", DEFAULT_AI_BASE_URL).strip()

GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "google-service-account.json").strip()
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
GOOGLE_DRIVE_PARENT_FOLDER_ID = os.getenv("GOOGLE_DRIVE_PARENT_FOLDER_ID", "").strip()
SHARE_SPREADSHEET_WITH_EMAIL = os.getenv("SHARE_SPREADSHEET_WITH_EMAIL", "").strip()
DEFAULT_TEXT_MODEL = {
    "xai": "grok-4.20-reasoning",
    "groq": "llama-3.3-70b-versatile",
    "openai": "gpt-4o-mini",
}.get(AI_PROVIDER, "gpt-4o-mini")
OPENAI_TEXT_MODEL = os.getenv("OPENAI_TEXT_MODEL", DEFAULT_TEXT_MODEL).strip()
OPENAI_TRANSCRIBE_MODEL = os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe").strip()
PAYMENT_ENABLED = os.getenv("PAYMENT_ENABLED", "false").strip().lower() in {"1", "true", "yes", "ha"}
PAYMENT_PROVIDER = os.getenv("PAYMENT_PROVIDER", "manual").strip()
PAYMENT_OWNER_CONTACT = os.getenv("PAYMENT_OWNER_CONTACT", "").strip()
PAYMENT_PLANS = os.getenv(
    "PAYMENT_PLANS",
    "free:0:20 ta AI savol;pro:49000:Cheksizga yaqin AI savollar;business:149000:Jamoa uchun",
).strip()
ANALYTICS_DB_FILE = os.getenv(
    "ANALYTICS_DB_FILE",
    "/tmp/bot_analytics.sqlite3" if os.getenv("VERCEL") else "bot_analytics.sqlite3",
).strip()
OWNER_EMAIL = os.getenv("OWNER_EMAIL", "").strip()
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587") or 587)
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", SMTP_USERNAME).strip()
REPORT_WEEKLY_DAY = int(os.getenv("REPORT_WEEKLY_DAY", "0") or 0)

EXPENSE_ALLOWED_USER_IDS = {
    int(user_id)
    for user_id in os.getenv("EXPENSE_ALLOWED_USER_IDS", "").replace(" ", "").split(",")
    if user_id
}

EXPENSE_HEADERS = [
    "date",
    "time",
    "telegram_user_id",
    "telegram_username",
    "amount",
    "currency",
    "category",
    "description",
    "raw_text",
]

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

openai_client_kwargs = {"api_key": AI_API_KEY or "missing"}
if AI_BASE_URL:
    openai_client_kwargs["base_url"] = AI_BASE_URL
openai_client = OpenAI(**openai_client_kwargs)
analytics: "AnalyticsStore | None" = None
sheets: "ExpenseSheets | None" = None


@dataclass
class Expense:
    amount: float
    currency: str
    category: str
    description: str
    raw_text: str


class AnalyticsStore:
    def __init__(self, db_file: str) -> None:
        self.db_file = db_file
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_file)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    message_count INTEGER NOT NULL DEFAULT 0,
                    ai_count INTEGER NOT NULL DEFAULT 0,
                    voice_count INTEGER NOT NULL DEFAULT 0,
                    expense_count INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS interactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    username TEXT,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    text_preview TEXT,
                    response_chars INTEGER NOT NULL DEFAULT 0,
                    error TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sent_reports (
                    report_key TEXT PRIMARY KEY,
                    sent_at TEXT NOT NULL
                )
                """
            )

    def record_interaction(
        self,
        user_id: int,
        username: str,
        full_name: str,
        action: str,
        status: str = "ok",
        text_preview: str = "",
        response_chars: int = 0,
        error: str = "",
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        preview = text_preview.replace("\n", " ")[:300]
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO users (user_id, username, full_name, first_seen, last_seen, message_count, ai_count, voice_count, expense_count)
                VALUES (?, ?, ?, ?, ?, 0, 0, 0, 0)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = excluded.username,
                    full_name = excluded.full_name,
                    last_seen = excluded.last_seen
                """,
                (user_id, username, full_name, now, now),
            )
            connection.execute(
                """
                UPDATE users
                SET
                    message_count = message_count + 1,
                    ai_count = ai_count + ?,
                    voice_count = voice_count + ?,
                    expense_count = expense_count + ?
                WHERE user_id = ?
                """,
                (
                    1 if action in {"ai", "text"} else 0,
                    1 if action == "voice" else 0,
                    1 if action == "expense" and status == "ok" else 0,
                    user_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO interactions (created_at, user_id, username, action, status, text_preview, response_chars, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now, user_id, username, action, status, preview, response_chars, error[:300]),
            )

    def has_sent_report(self, report_key: str) -> bool:
        with self._connect() as connection:
            row = connection.execute("SELECT 1 FROM sent_reports WHERE report_key = ?", (report_key,)).fetchone()
        return row is not None

    def mark_report_sent(self, report_key: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO sent_reports (report_key, sent_at) VALUES (?, ?)",
                (report_key, datetime.now().isoformat(timespec="seconds")),
            )

    def build_report(
        self,
        title: str,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> str:
        conditions = []
        params_list: list[Any] = []
        if start_at:
            conditions.append("created_at >= ?")
            params_list.append(start_at.isoformat(timespec="seconds"))
        if end_at:
            conditions.append("created_at < ?")
            params_list.append(end_at.isoformat(timespec="seconds"))
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params = tuple(params_list)

        with self._connect() as connection:
            total_users = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            active_users = connection.execute(
                f"SELECT COUNT(DISTINCT user_id) FROM interactions {where}", params
            ).fetchone()[0]
            action_rows = connection.execute(
                f"""
                SELECT action, COUNT(*) AS count
                FROM interactions
                {where}
                GROUP BY action
                ORDER BY count DESC
                """,
                params,
            ).fetchall()
            user_rows = connection.execute(
                f"""
                SELECT
                    user_id,
                    COALESCE(username, '') AS username,
                    COUNT(*) AS count,
                    SUM(response_chars) AS response_chars,
                    MAX(created_at) AS last_seen
                FROM interactions
                {where}
                GROUP BY user_id, username
                ORDER BY count DESC
                LIMIT 15
                """,
                params,
            ).fetchall()
            recent_rows = connection.execute(
                f"""
                SELECT created_at, user_id, COALESCE(username, '') AS username, action, status, text_preview
                FROM interactions
                {where}
                ORDER BY created_at DESC
                LIMIT 20
                """,
                params,
            ).fetchall()

        lines = [
            title,
            "",
            f"Jami obunachi/foydalanuvchi: {total_users}",
            f"Shu davrda faol foydalanuvchi: {active_users}",
            "",
            "Ishlatish turi:",
        ]
        if action_rows:
            lines.extend(f"- {row['action']}: {row['count']}" for row in action_rows)
        else:
            lines.append("- Hali faollik yo'q")

        lines.extend(["", "Eng faol foydalanuvchilar:"])
        if user_rows:
            for row in user_rows:
                username = f"@{row['username']}" if row["username"] else "username yo'q"
                lines.append(
                    f"- {row['user_id']} ({username}): {row['count']} marta, "
                    f"AI javob belgisi: {row['response_chars'] or 0}, oxirgi: {row['last_seen']}"
                )
        else:
            lines.append("- Hali foydalanuvchi yo'q")

        lines.extend(["", "Oxirgi so'rovlar:"])
        if recent_rows:
            for row in recent_rows:
                username = f"@{row['username']}" if row["username"] else str(row["user_id"])
                lines.append(
                    f"- {row['created_at']} | {username} | {row['action']} | {row['status']} | {row['text_preview']}"
                )
        else:
            lines.append("- Hali so'rov yo'q")

        return "\n".join(lines)


class ExpenseSheets:
    def __init__(self) -> None:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        if GOOGLE_SERVICE_ACCOUNT_JSON:
            credentials = Credentials.from_service_account_info(
                json.loads(GOOGLE_SERVICE_ACCOUNT_JSON),
                scopes=scopes,
            )
        else:
            credentials = Credentials.from_service_account_file(
                GOOGLE_SERVICE_ACCOUNT_FILE,
                scopes=scopes,
            )
        self.client = gspread.authorize(credentials)

    def _spreadsheet_title(self, user_id: int, username: str) -> str:
        return f"Telegram Expenses - {user_id}"

    def _open_or_create_spreadsheet(self, user_id: int, username: str):
        title = self._spreadsheet_title(user_id, username)
        try:
            spreadsheet = self.client.open(title)
        except gspread.SpreadsheetNotFound:
            spreadsheet = self.client.create(title, folder_id=GOOGLE_DRIVE_PARENT_FOLDER_ID or None)
            if SHARE_SPREADSHEET_WITH_EMAIL:
                spreadsheet.share(SHARE_SPREADSHEET_WITH_EMAIL, perm_type="user", role="writer")
        return spreadsheet

    def _month_sheet(self, spreadsheet, month_key: str):
        try:
            worksheet = spreadsheet.worksheet(month_key)
        except gspread.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title=month_key, rows=1000, cols=len(EXPENSE_HEADERS))
            worksheet.append_row(EXPENSE_HEADERS)
        return worksheet

    def append_expense(self, user_id: int, username: str, expense: Expense) -> str:
        now = datetime.now()
        month_key = now.strftime("%Y-%m")
        spreadsheet = self._open_or_create_spreadsheet(user_id, username)
        worksheet = self._month_sheet(spreadsheet, month_key)
        worksheet.append_row(
            [
                now.strftime("%Y-%m-%d"),
                now.strftime("%H:%M:%S"),
                user_id,
                username,
                expense.amount,
                expense.currency,
                expense.category,
                expense.description,
                expense.raw_text,
            ],
            value_input_option="USER_ENTERED",
        )
        return spreadsheet.url

    def rows_for_month(self, user_id: int, username: str, month_key: str) -> list[dict[str, Any]]:
        spreadsheet = self._open_or_create_spreadsheet(user_id, username)
        worksheet = self._month_sheet(spreadsheet, month_key)
        return worksheet.get_all_records()


def require_config() -> None:
    missing = []
    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not AI_API_KEY:
        missing.append("GROK_API_KEY yoki GROQ_API_KEY yoki OPENAI_API_KEY")
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(f"Sozlanmagan yoki topilmadi: {joined}. .env.example faylini ko'ring.")


def require_google_config() -> None:
    if not GOOGLE_SERVICE_ACCOUNT_JSON and not Path(GOOGLE_SERVICE_ACCOUNT_FILE).exists():
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON yoki GOOGLE_SERVICE_ACCOUNT_FILE sozlanmagan.")


def get_analytics() -> AnalyticsStore:
    global analytics

    if analytics is None:
        analytics = AnalyticsStore(ANALYTICS_DB_FILE)
    return analytics


def get_sheets() -> ExpenseSheets:
    global sheets

    require_google_config()
    if sheets is None:
        sheets = ExpenseSheets()
    return sheets


def email_reports_enabled() -> bool:
    return all([OWNER_EMAIL, SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM_EMAIL])


def send_email(subject: str, body: str) -> None:
    if not email_reports_enabled():
        logger.info("Email hisobot o'chirilgan: SMTP yoki OWNER_EMAIL sozlanmagan.")
        return

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = SMTP_FROM_EMAIL
    message["To"] = OWNER_EMAIL
    message.set_content(body)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
        smtp.send_message(message)


async def maybe_send_reports() -> None:
    now = datetime.now()
    if now.weekday() == REPORT_WEEKLY_DAY:
        report_key = f"weekly-{now.strftime('%Y-%W')}"
        store = get_analytics()
        if not store.has_sent_report(report_key):
            start_at = now - timedelta(days=7)
            body = store.build_report("Haftalik Telegram bot hisoboti", start_at=start_at)
            await asyncio.to_thread(send_email, "Haftalik Telegram bot hisoboti", body)
            store.mark_report_sent(report_key)

    if now.day == 1:
        this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        previous_month_start = (this_month_start - timedelta(days=1)).replace(day=1)
        previous_month = previous_month_start.strftime("%Y-%m")
        report_key = f"monthly-{previous_month}"
        store = get_analytics()
        if not store.has_sent_report(report_key):
            body = store.build_report(
                f"Oylik Telegram bot hisoboti: {previous_month}",
                start_at=previous_month_start,
                end_at=this_month_start,
            )
            await asyncio.to_thread(send_email, f"Oylik Telegram bot hisoboti: {previous_month}", body)
            store.mark_report_sent(report_key)


async def report_scheduler() -> None:
    while True:
        try:
            await maybe_send_reports()
        except Exception:
            logger.exception("Email hisobot yuborishda xato")
        await asyncio.sleep(60 * 60)


async def start_background_tasks(application: Application) -> None:
    await setup_bot_commands(application)
    application.bot_data["report_scheduler_task"] = asyncio.create_task(report_scheduler())


async def stop_background_tasks(application: Application) -> None:
    task = application.bot_data.get("report_scheduler_task")
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def setup_bot_commands(application: Application) -> None:
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Botni boshlash"),
            BotCommand("setting", "Profil va bot sozlamalari"),
            BotCommand("payment", "Obuna va to'lov holati"),
            BotCommand("ai", "AI ga savol berish"),
            BotCommand("help", "Komandalar ro'yxati"),
            BotCommand("report", "Admin statistikasi"),
        ]
    )


def can_write_expenses(user_id: int) -> bool:
    return user_id in EXPENSE_ALLOWED_USER_IDS


def is_owner(user_id: int) -> bool:
    return can_write_expenses(user_id)


def parse_payment_plans() -> list[tuple[str, str, str]]:
    plans = []
    for raw_plan in PAYMENT_PLANS.split(";"):
        parts = [part.strip() for part in raw_plan.split(":", 2)]
        if len(parts) == 3 and parts[0]:
            plans.append((parts[0], parts[1], parts[2]))
    return plans


def payment_status_text() -> str:
    plans = parse_payment_plans()
    lines = [
        "To'lov tizimi holati:",
        "Yoqilgan" if PAYMENT_ENABLED else "Hozircha to'lovsiz rejim yoqilgan.",
        "",
        "Rejalar:",
    ]
    if plans:
        for name, price, description in plans:
            price_text = "bepul" if price == "0" else f"{price} UZS"
            lines.append(f"- {name}: {price_text} - {description}")
    else:
        lines.append("- Hali reja kiritilmagan.")

    lines.extend(["", f"Provider: {PAYMENT_PROVIDER}"])
    if PAYMENT_OWNER_CONTACT:
        lines.append(f"Aloqa: {PAYMENT_OWNER_CONTACT}")
    if not PAYMENT_ENABLED:
        lines.append("")
        lines.append("Obunachilar ko'payganda admin to'lovni yoqadi.")
    return "\n".join(lines)


def clean_json_response(content: str) -> str:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```").strip()
        cleaned = cleaned.removesuffix("```").strip()
    return cleaned


def parse_expense(text: str) -> Expense:
    prompt = f"""
Matndan xarajat ma'lumotini ajrat.
Faqat JSON qaytar:
{{
  "amount": number,
  "currency": "UZS yoki USD yoki boshqa",
  "category": "ovqat|transport|uy|internet|kiyim|sog'liq|ta'lim|boshqa",
  "description": "qisqa izoh"
}}

Agar valyuta aytilmagan bo'lsa UZS deb ol.
Matn: {text}
""".strip()

    response = openai_client.chat.completions.create(
        model=OPENAI_TEXT_MODEL,
        messages=[
            {"role": "system", "content": "Faqat valid JSON qaytaring. Markdown ishlatmang."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
    )
    content = clean_json_response(response.choices[0].message.content or "")
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"AI xarajatni JSON formatida qaytarmadi: {content}") from exc

    amount = float(data["amount"])
    if amount <= 0:
        raise ValueError("Xarajat summasi 0 dan katta bo'lishi kerak.")

    return Expense(
        amount=amount,
        currency=str(data.get("currency") or "UZS").upper(),
        category=str(data.get("category") or "boshqa"),
        description=str(data.get("description") or text),
        raw_text=text,
    )


def telegram_user_details(update: Update) -> tuple[int, str, str]:
    user = update.effective_user
    username = user.username or ""
    full_name = user.full_name or username or "user"
    return user.id, username, full_name


def record_usage(
    update: Update,
    action: str,
    status: str = "ok",
    text_preview: str = "",
    response_chars: int = 0,
    error: str = "",
) -> None:
    user_id, username, full_name = telegram_user_details(update)
    try:
        get_analytics().record_interaction(
            user_id=user_id,
            username=username,
            full_name=full_name,
            action=action,
            status=status,
            text_preview=text_preview,
            response_chars=response_chars,
            error=error,
        )
    except Exception:
        logger.exception("Analytics yozishda xato")


async def ask_ai(text: str) -> str:
    response = await asyncio.to_thread(
        openai_client.chat.completions.create,
        model=OPENAI_TEXT_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Siz Telegram bot ichidagi foydali AI yordamchisiz. "
                    "Javoblarni foydalanuvchi yozgan tilda, aniq, foydali va qisqa bering. "
                    "Savolga bevosita javob bering, keraksiz kirish gaplarni yozmang."
                ),
            },
            {"role": "user", "content": text},
        ],
        temperature=0.4,
    )
    return (response.choices[0].message.content or "").strip()


async def transcribe_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    voice = update.message.voice
    telegram_file = await context.bot.get_file(voice.file_id)

    with tempfile.TemporaryDirectory() as tmp_dir:
        audio_path = Path(tmp_dir) / "voice.ogg"
        await telegram_file.download_to_drive(custom_path=str(audio_path))
        with audio_path.open("rb") as audio_file:
            transcription = await asyncio.to_thread(
                openai_client.audio.transcriptions.create,
                model=OPENAI_TRANSCRIBE_MODEL,
                file=audio_file,
            )
    return transcription.text.strip()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    record_usage(update, "start")
    expense_status = (
        "Sizda xarajat yozish ruxsati bor."
        if can_write_expenses(user.id)
        else "Siz AI yordamchidan foydalanishingiz mumkin."
    )
    await update.message.reply_text(
        "Salom! Men AI yordamchi botman.\n\n"
        f"Sizning Telegram user ID: {user.id}\n\n"
        f"{expense_status}\n\n"
        "Savolingizni oddiy matn qilib yuboring, men aniq javob beraman.\n\n"
        "/setting - bot sozlamalari\n"
        "/payment - obuna va to'lov holati\n"
        "/help - komandalar"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_usage(update, "help")
    await update.message.reply_text(
        "Komandalar:\n"
        "/start - botni boshlash\n"
        "/setting - sozlamalar va profilingiz\n"
        "/payment - obuna/to'lov holati\n"
        "/ai savol - AI ga aniq savol berish\n"
        "/help - komandalar ro'yxati\n\n"
        "Admin komandalar:\n"
        "/report - 7 kunlik statistika\n"
        "/report month - 31 kunlik statistika\n"
        "/expense 25000 ovqat - xarajat qo'shish\n"
        "/month - oylik Excel"
    )


async def setting_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    record_usage(update, "setting")
    role = "admin" if is_owner(user.id) else "foydalanuvchi"
    username = f"@{user.username}" if user.username else "yo'q"
    await update.message.reply_text(
        "Sozlamalar:\n"
        f"User ID: {user.id}\n"
        f"Username: {username}\n"
        f"Rol: {role}\n"
        f"AI provider: {AI_PROVIDER}\n"
        f"AI model: {OPENAI_TEXT_MODEL}\n"
        f"To'lov: {'yoqilgan' if PAYMENT_ENABLED else 'hozircha ochirilgan'}\n"
        f"Xarajat yozish: {'ruxsat bor' if can_write_expenses(user.id) else 'ruxsat yoq'}"
    )


async def payment_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record_usage(update, "payment")
    await update.message.reply_text(payment_status_text())


async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text("Savolni ham yozing: /ai biznes reja tuzib ber")
        record_usage(update, "ai", status="empty")
        return
    await update.message.chat.send_action(ChatAction.TYPING)
    try:
        answer = await ask_ai(text)
    except Exception as exc:
        logger.exception("AI request failed")
        record_usage(update, "ai", status="error", text_preview=text, error=str(exc))
        await update.message.reply_text(f"AI javob bera olmadi: {exc}")
        return
    record_usage(update, "ai", text_preview=text, response_chars=len(answer))
    await update.message.reply_text(answer[:4096])


async def expense_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not can_write_expenses(user.id):
        await update.message.reply_text("Bu botda xarajat yozish faqat egasi uchun yoqilgan. Siz AI bilan ishlashingiz mumkin.")
        record_usage(update, "expense", status="denied")
        return
    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text("Masalan: /expense 45000 ovqat yoki /expense taksi 25000")
        record_usage(update, "expense", status="empty")
        return
    await save_expense_from_text(update, text)


async def save_expense_from_text(update: Update, text: str) -> None:
    user = update.effective_user
    username = user.username or user.full_name or "user"
    await update.message.chat.send_action(ChatAction.TYPING)
    try:
        expense = await asyncio.to_thread(parse_expense, text)
        sheet_url = await asyncio.to_thread(lambda: get_sheets().append_expense(user.id, username, expense))
    except Exception as exc:
        logger.exception("Expense save failed")
        record_usage(update, "expense", status="error", text_preview=text, error=str(exc))
        await update.message.reply_text(f"Xarajatni yozib bo'lmadi: {exc}")
        return

    record_usage(update, "expense", text_preview=text)
    await update.message.reply_text(
        "Xarajat yozildi:\n"
        f"Summa: {expense.amount:g} {expense.currency}\n"
        f"Kategoriya: {expense.category}\n"
        f"Izoh: {expense.description}\n"
        f"Google Sheets: {sheet_url}"
    )


async def month_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not can_write_expenses(user.id):
        await update.message.reply_text("Oylik xarajat fayli faqat xarajat yozish ruxsati bor foydalanuvchilar uchun.")
        record_usage(update, "month", status="denied")
        return

    month_key = context.args[0].strip() if context.args else datetime.now().strftime("%Y-%m")
    try:
        datetime.strptime(month_key, "%Y-%m")
    except ValueError:
        await update.message.reply_text("Oy formati noto'g'ri. Masalan: /month 2026-05")
        record_usage(update, "month", status="bad_month")
        return

    username = user.username or user.full_name or "user"
    rows = await asyncio.to_thread(lambda: get_sheets().rows_for_month(user.id, username, month_key))
    if not rows:
        await update.message.reply_text(f"{month_key} oyida xarajat topilmadi.")
        record_usage(update, "month", status="empty", text_preview=month_key)
        return

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = month_key
    worksheet.append(EXPENSE_HEADERS)
    total_by_currency: dict[str, float] = {}

    for row in rows:
        values = [row.get(header, "") for header in EXPENSE_HEADERS]
        worksheet.append(values)
        currency = str(row.get("currency", "UZS") or "UZS")
        amount = float(row.get("amount", 0) or 0)
        total_by_currency[currency] = total_by_currency.get(currency, 0) + amount

    worksheet.append([])
    worksheet.append(["TOTAL"])
    for currency, total in sorted(total_by_currency.items()):
        worksheet.append([currency, total])

    with tempfile.TemporaryDirectory() as tmp_dir:
        report_path = Path(tmp_dir) / f"expenses-{user.id}-{month_key}.xlsx"
        workbook.save(report_path)
        with report_path.open("rb") as report_file:
            await update.message.reply_document(
                document=report_file,
                filename=report_path.name,
                caption=f"{month_key} xarajatlar hisoboti",
            )
    record_usage(update, "month", text_preview=month_key)


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not can_write_expenses(user.id):
        await update.message.reply_text("Bu hisobot faqat bot egasi uchun.")
        record_usage(update, "report", status="denied")
        return

    period = context.args[0].strip().lower() if context.args else "week"
    if period in {"month", "oy"}:
        start_at = datetime.now() - timedelta(days=31)
        title = "Oxirgi 31 kunlik Telegram bot hisoboti"
    else:
        start_at = datetime.now() - timedelta(days=7)
        title = "Oxirgi 7 kunlik Telegram bot hisoboti"

    report = get_analytics().build_report(title, start_at=start_at)
    record_usage(update, "report", text_preview=period)
    await update.message.reply_text(report[:4096])


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.chat.send_action(ChatAction.TYPING)
    try:
        text = await transcribe_voice(update, context)
    except Exception as exc:
        logger.exception("Voice transcription failed")
        record_usage(update, "voice", status="error", error=str(exc))
        await update.message.reply_text(f"Ovozni matnga aylantirib bo'lmadi: {exc}")
        return

    record_usage(update, "voice", text_preview=text)
    if can_write_expenses(user.id):
        await update.message.reply_text(f"Ovozdan o'qilgan matn: {text}")
        await save_expense_from_text(update, text)
        return

    try:
        answer = await ask_ai(text)
    except Exception as exc:
        logger.exception("AI voice answer failed")
        record_usage(update, "ai", status="error", text_preview=text, error=str(exc))
        await update.message.reply_text(f"AI javob bera olmadi: {exc}")
        return
    record_usage(update, "ai", text_preview=text, response_chars=len(answer))
    await update.message.reply_text(answer[:4096])


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()
    await update.message.chat.send_action(ChatAction.TYPING)
    try:
        answer = await ask_ai(text)
    except Exception as exc:
        logger.exception("AI text answer failed")
        record_usage(update, "text", status="error", text_preview=text, error=str(exc))
        await update.message.reply_text(f"AI javob bera olmadi: {exc}")
        return
    record_usage(update, "text", text_preview=text, response_chars=len(answer))
    await update.message.reply_text(answer[:4096])


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Telegram update failed", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "Kechirasiz, bot ichida xatolik chiqdi. Iltimos, birozdan keyin yana urinib ko'ring."
            )
        except Exception:
            logger.exception("Error xabarini yuborib bo'lmadi")


def build_application() -> Application:
    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(start_background_tasks)
        .post_shutdown(stop_background_tasks)
        .build()
    )
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("setting", setting_command))
    application.add_handler(CommandHandler("payment", payment_command))
    application.add_handler(CommandHandler("ai", ai_command))
    application.add_handler(CommandHandler("expense", expense_command))
    application.add_handler(CommandHandler("month", month_command))
    application.add_handler(CommandHandler("report", report_command))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_error_handler(error_handler)
    return application


if __name__ == "__main__":
    require_config()
    analytics = AnalyticsStore(ANALYTICS_DB_FILE)
    sheets = ExpenseSheets()
    app = build_application()
    logger.info("Bot ishga tushdi.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
