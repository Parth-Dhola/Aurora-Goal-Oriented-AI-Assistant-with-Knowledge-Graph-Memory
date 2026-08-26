"""
bot.py — Aurora Telegram Bot

Commands:
  /start               — welcome + show status
  /login               — authenticate with your Aurora account (conversation flow)
  /logout              — sign out
  /ask <question>      — send a message through the CRAG agent
  /plan                — "plan my day" shortcut
  /goals               — list your active goals
  /addgoal <name> [priority] — add a goal explicitly
  /stats               — productivity dashboard + KG stats
  /help                — list all commands

Auth flow:
  /login → bot asks username → bot asks password (separate messages, not slash args)
  Token is stored in SQLite (telegram_sessions) — survives bot restarts

Run:
  conda activate aurora
  python bot.py

Requires TELEGRAM_BOT_TOKEN in .env
"""

import os
import sys
import logging
import requests
from dotenv import load_dotenv

# Add backend to path so we can import models
sys.path.insert(0, os.path.dirname(__file__))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
load_dotenv()  # also try local .env

from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("aurora-bot")

BOT_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
API_BASE  = os.getenv("AURORA_API_BASE", "http://localhost:8000/api")

# ConversationHandler states
WAITING_USERNAME, WAITING_PASSWORD = range(2)

# In-memory cache (telegram_user_id → {"username": str, "token": str})
_cache: dict = {}


# ── DB helpers ─────────────────────────────────────────────────────────────────
def _db_get_session(tid: int) -> dict | None:
    try:
        from models.database import get_db
        conn = get_db()
        row = conn.execute(
            "SELECT aurora_username, jwt_token FROM telegram_sessions WHERE telegram_user_id=?",
            (tid,)
        ).fetchone()
        conn.close()
        if row:
            return {"username": row["aurora_username"], "token": row["jwt_token"]}
    except Exception as e:
        logger.warning(f"DB read error: {e}")
    return None


def _db_save_session(tid: int, tg_username: str, aurora_username: str, token: str):
    try:
        from models.database import get_db
        conn = get_db()
        conn.execute(
            """INSERT INTO telegram_sessions
               (telegram_user_id, telegram_username, aurora_username, jwt_token, updated_at)
               VALUES (?,?,?,?,CURRENT_TIMESTAMP)
               ON CONFLICT(telegram_user_id) DO UPDATE SET
                 aurora_username=excluded.aurora_username,
                 jwt_token=excluded.jwt_token,
                 updated_at=CURRENT_TIMESTAMP""",
            (tid, tg_username or "", aurora_username, token)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"DB write error: {e}")


def _db_delete_session(tid: int):
    try:
        from models.database import get_db
        conn = get_db()
        conn.execute("DELETE FROM telegram_sessions WHERE telegram_user_id=?", (tid,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"DB delete error: {e}")


def get_session(tid: int) -> dict | None:
    """Return session from cache, falling back to DB."""
    if tid in _cache:
        return _cache[tid]
    session = _db_get_session(tid)
    if session:
        _cache[tid] = session
    return session


def save_session(update: Update, aurora_username: str, token: str):
    tid = update.effective_user.id
    tg_username = update.effective_user.username or ""
    _cache[tid] = {"username": aurora_username, "token": token}
    _db_save_session(tid, tg_username, aurora_username, token)


def delete_session(tid: int):
    _cache.pop(tid, None)
    _db_delete_session(tid)


# ── API helpers ────────────────────────────────────────────────────────────────
def api(method: str, endpoint: str, token: str = None,
        json_data: dict = None, params: dict = None) -> dict:
    url = f"{API_BASE}{endpoint}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = getattr(requests, method)(
            url, json=json_data, headers=headers, params=params, timeout=90
        )
        return r.json()
    except Exception as e:
        return {"error": str(e)}


# ── Auth guard decorator ───────────────────────────────────────────────────────
def require_auth(func):
    """Decorator: reply with login prompt if user isn't authenticated."""
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not get_session(update.effective_user.id):
            await update.message.reply_text(
                "🔐 You're not logged in.\nUse /login to connect your Aurora account."
            )
            return
        return await func(update, ctx)
    wrapper.__name__ = func.__name__
    return wrapper


# ── /start ─────────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    session = get_session(tid)
    if session:
        await update.message.reply_text(
            f"👋 Welcome back, *{session['username']}*!\n\n"
            "Quick commands:\n"
            "• /ask what should I focus on today?\n"
            "• /goals — view your goals\n"
            "• /plan — plan your day\n"
            "• /stats — dashboard\n"
            "• /help — all commands",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "🌟 *Welcome to Aurora!*\n\n"
            "Your personal AI assistant with Knowledge Graph memory.\n"
            "I remember your goals and progress across every conversation.\n\n"
            "Use /login to connect your Aurora account.",
            parse_mode="Markdown"
        )


# ── /login conversation ────────────────────────────────────────────────────────
async def cmd_login_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    if get_session(tid):
        session = get_session(tid)
        await update.message.reply_text(
            f"✅ You're already logged in as *{session['username']}*.\n"
            "Use /logout to switch accounts.",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    await update.message.reply_text("Enter your Aurora *username*:", parse_mode="Markdown")
    return WAITING_USERNAME


async def login_got_username(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["aurora_username"] = update.message.text.strip()
    await update.message.reply_text("Enter your *password*:", parse_mode="Markdown")
    return WAITING_PASSWORD


async def login_got_password(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    username = ctx.user_data.get("aurora_username", "")
    password = update.message.text.strip()

    await update.message.reply_text("🔐 Authenticating...")

    result = api("post", "/auth/login", json_data={"username": username, "password": password})
    if "access_token" in result:
        save_session(update, username, result["access_token"])
        await update.message.reply_text(
            f"✅ *Logged in as {username}!*\n\n"
            "Your Knowledge Graph is ready. Try:\n"
            "• /ask what should I work on today?\n"
            "• /goals — view your goals",
            parse_mode="Markdown"
        )
    else:
        detail = result.get("detail", result.get("error", "Authentication failed"))
        await update.message.reply_text(
            f"❌ Login failed: {detail}\n"
            "Use /login to try again, or /start to register via the web app."
        )
    return ConversationHandler.END


async def login_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Login cancelled.")
    return ConversationHandler.END


# ── /logout ────────────────────────────────────────────────────────────────────
async def cmd_logout(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    session = get_session(tid)
    if session:
        delete_session(tid)
        await update.message.reply_text(f"👋 Logged out ({session['username']}). Use /login to sign in again.")
    else:
        await update.message.reply_text("You weren't logged in.")


# ── /ask ───────────────────────────────────────────────────────────────────────
@require_auth
async def cmd_ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    session = get_session(tid)
    question = " ".join(ctx.args).strip()
    if not question:
        await update.message.reply_text(
            "Usage: /ask <your question>\nExample: /ask what should I study today?"
        )
        return

    thinking = await update.message.reply_text("🤔 Thinking...")
    result = api("post", "/chat/", token=session["token"],
                 json_data={"message": question, "session_id": f"tg-{tid}"})
    reply = result.get("reply") or result.get("error", "Something went wrong.")
    await thinking.delete()
    # Telegram has 4096 char limit per message
    for i in range(0, len(reply), 4000):
        await update.message.reply_text(reply[i:i+4000])


# ── /plan ──────────────────────────────────────────────────────────────────────
@require_auth
async def cmd_plan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    session = get_session(tid)
    thinking = await update.message.reply_text("📋 Planning your day based on your goals...")
    result = api("post", "/chat/", token=session["token"],
                 json_data={"message": "Plan my day. What should I focus on given my current goals and progress?",
                            "session_id": f"tg-{tid}"})
    reply = result.get("reply") or result.get("error", "Something went wrong.")
    await thinking.delete()
    for i in range(0, len(reply), 4000):
        await update.message.reply_text(reply[i:i+4000])


# ── /goals ─────────────────────────────────────────────────────────────────────
@require_auth
async def cmd_goals(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    session = get_session(update.effective_user.id)
    result = api("get", "/goals/", token=session["token"])
    goal_list = result.get("goals", [])

    if not goal_list:
        await update.message.reply_text(
            "No goals yet!\n\n"
            "• Use /addgoal <name> to add one explicitly\n"
            "• Or just /ask — Aurora extracts goals automatically from your messages"
        )
        return

    icons = {"urgent": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
    active = [g for g in goal_list if g.get("status") == "active"]
    archived = [g for g in goal_list if g.get("status") != "active"]

    lines = [f"🎯 *Your Goals* ({len(active)} active)\n"]
    for g in active:
        icon = icons.get(g["priority"], "•")
        checkmark = " ✓" if g["source"] == "api" else ""
        target = f"\n  └ Target: {g['target']}" if g.get("target") else ""
        deadline = f" by {g['deadline']}" if g.get("deadline") else ""
        lines.append(f"{icon} *{g['label']}*{checkmark}{deadline}{target}")

    if archived:
        lines.append(f"\n_({len(archived)} archived)_")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /addgoal ───────────────────────────────────────────────────────────────────
@require_auth
async def cmd_addgoal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    session = get_session(update.effective_user.id)
    args = ctx.args
    if not args:
        await update.message.reply_text(
            "Usage: /addgoal <goal name> [priority]\n"
            "Priority: urgent | high | medium | low\n\n"
            "Examples:\n"
            "  /addgoal Placement Prep urgent\n"
            "  /addgoal Learn Guitar\n"
            "  /addgoal Lose 10kg high"
        )
        return

    priority = "high"
    label = " ".join(args)
    if args[-1].lower() in ("urgent", "high", "medium", "low"):
        priority = args[-1].lower()
        label = " ".join(args[:-1]).strip()

    if not label:
        await update.message.reply_text("Please provide a goal name.")
        return

    result = api("post", "/goals/", token=session["token"],
                 json_data={"label": label, "priority": priority})
    if "id" in result:
        icons = {"urgent": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
        await update.message.reply_text(
            f"{icons.get(priority,'•')} Goal added: *{label}* [{priority}]\n"
            "Aurora will now reference this goal in every conversation.",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(f"❌ Error: {result.get('detail', str(result))}")


# ── /stats ─────────────────────────────────────────────────────────────────────
@require_auth
async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    session = get_session(update.effective_user.id)
    result = api("get", "/stats/", token=session["token"])
    if "error" in result:
        await update.message.reply_text(f"❌ Error: {result['error']}")
        return

    kg        = result.get("knowledge_graph", {})
    llm       = result.get("llm", {})
    tasks     = result.get("tasks", {})
    chat      = result.get("chat", {})
    placement = result.get("placement", {})
    strategies = llm.get("strategies", [])

    strat_lines = "\n".join(
        f"  • {s['strategy']}: {s['count']} calls (avg {s['avg_latency']}ms)"
        for s in strategies
    ) or "  No calls yet"

    text = (
        f"📊 *Aurora Dashboard*\n\n"
        f"🧠 *Knowledge Graph*\n"
        f"  Goals: {kg.get('active_goals', 0)} active\n"
        f"  Facts: {kg.get('total_facts', 0)} stored\n\n"
        f"💬 *Chat*\n"
        f"  Messages: {chat.get('total_messages', 0)}\n\n"
        f"⚡ *LLM*\n"
        f"  Total calls: {llm.get('total_calls', 0)}\n"
        f"  Avg latency: {llm.get('avg_latency_ms', 0)}ms\n"
        f"  Strategies:\n{strat_lines}\n\n"
        f"✅ *Tasks*\n"
        f"  Done: {tasks.get('done', 0)} / {tasks.get('total', 0)} "
        f"({tasks.get('completion_rate', 0)}%)\n\n"
        f"🎯 *Placement*\n"
        f"  Days remaining: {placement.get('days_remaining', '?')}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ── /help ──────────────────────────────────────────────────────────────────────
async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌟 *Aurora Bot — Commands*\n\n"
        "*Auth*\n"
        "/login — connect your Aurora account\n"
        "/logout — sign out\n\n"
        "*AI Chat (CRAG Agent)*\n"
        "/ask <question> — chat with Aurora\n"
        "/plan — plan your day based on your goals\n\n"
        "*Goals*\n"
        "/goals — list your goals\n"
        "/addgoal <name> [priority] — add a goal\n"
        "_(Aurora also extracts goals from your chat messages automatically)_\n\n"
        "*Stats*\n"
        "/stats — productivity dashboard\n\n"
        "/help — this message",
        parse_mode="Markdown"
    )


# ── Command suggestions (shown when user types /) ──────────────────────────────
_COMMANDS = [
    BotCommand("start",   "👋 Welcome and login status"),
    BotCommand("login",   "🔐 Connect your Aurora account"),
    BotCommand("logout",  "🚪 Sign out"),
    BotCommand("ask",     "💬 Ask Aurora anything"),
    BotCommand("plan",    "📋 Plan your day based on your goals"),
    BotCommand("goals",   "🎯 View your active goals"),
    BotCommand("addgoal", "➕ Add a new goal (e.g. /addgoal Lose weight high)"),
    BotCommand("stats",   "📊 Productivity dashboard and KG stats"),
    BotCommand("help",    "❓ List all commands"),
]


async def _post_init(application: Application) -> None:
    """Register command suggestions with Telegram on bot startup."""
    await application.bot.set_my_commands(_COMMANDS)
    logger.info("Command suggestions registered with Telegram.")


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    if not BOT_TOKEN:
        print("[Bot] ❌  TELEGRAM_TOKEN not set in .env")
        print("[Bot]    Get a token from @BotFather → /newbot")
        return

    print(f"[Bot] Connecting to Aurora API at {API_BASE}")

    # post_init registers command suggestions with Telegram on every startup
    app = Application.builder().token(BOT_TOKEN).post_init(_post_init).build()

    # Login conversation
    login_conv = ConversationHandler(
        entry_points=[CommandHandler("login", cmd_login_start)],
        states={
            WAITING_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_got_username)],
            WAITING_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_got_password)],
        },
        fallbacks=[CommandHandler("cancel", login_cancel)],
    )

    app.add_handler(login_conv)
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("logout",  cmd_logout))
    app.add_handler(CommandHandler("ask",     cmd_ask))
    app.add_handler(CommandHandler("plan",    cmd_plan))
    app.add_handler(CommandHandler("goals",   cmd_goals))
    app.add_handler(CommandHandler("addgoal", cmd_addgoal))
    app.add_handler(CommandHandler("stats",   cmd_stats))
    app.add_handler(CommandHandler("help",    cmd_help))

    print("[Bot] Aurora Telegram Bot is running. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
