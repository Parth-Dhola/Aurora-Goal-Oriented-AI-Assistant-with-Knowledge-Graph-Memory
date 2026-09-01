"""
bot.py — Aurora Telegram Bot

Commands:
  /start               — welcome + show status
  /login               — authenticate with your Aurora account (conversation flow)
  /logout              — sign out
  /ask <question>      — send a message through the CRAG agent
  /plan                — "plan my day" shortcut
  /model               — switch AI model (Local, Gemini, OpenAI, Groq, Claude)
  /docs                — list uploaded study documents
  /goals               — list your active goals
  /addgoal <name> [priority] — add a goal explicitly
  /stats               — productivity dashboard + KG stats
  /help                — list all commands

Direct Chat:
  You can also type any message directly to Aurora without typing /ask!

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

from telegram import Update, BotCommand, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
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


def _get_token(tid: int) -> str | None:
    """Extract JWT token for a given telegram user ID."""
    session = get_session(tid)
    return session["token"] if session else None


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


async def _safe_send_reply(update: Update, text: str):
    """Safely send message chunks to Telegram with markdown fallback."""
    for i in range(0, len(text), 4000):
        chunk = text[i:i+4000]
        try:
            await update.message.reply_text(chunk, parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(chunk)


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
            "• Just type any message to chat directly!\n"
            "• /model — switch AI models\n"
            "• /goals — view your goals\n"
            "• /plan — plan your day\n"
            "• /docs — view study materials\n"
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
            "• Type any question directly into chat!\n"
            "• /model — switch AI models\n"
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


# ── /ask & Direct Message Handler ──────────────────────────────────────────────
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
    await _safe_send_reply(update, reply)


@require_auth
async def handle_direct_chat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Allow user to type natural messages directly without needing /ask."""
    user_msg = update.message.text.strip() if update.message and update.message.text else ""
    if not user_msg:
        return

    tid = update.effective_user.id
    session = get_session(tid)
    thinking = await update.message.reply_text("🤔 Thinking...")
    result = api("post", "/chat/", token=session["token"],
                 json_data={"message": user_msg, "session_id": f"tg-{tid}"})
    reply = result.get("reply") or result.get("error", "Something went wrong.")
    await thinking.delete()
    await _safe_send_reply(update, reply)


# ── /paper & /research ────────────────────────────────────────────────────────
@require_auth
async def cmd_paper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Directly query Apollo for academic research papers, citations, and repositories."""
    query = " ".join(ctx.args).strip()
    if not query:
        await update.message.reply_text(
            "Usage: /paper <topic or question>\nExample: /paper FlashAttention-2 memory optimization"
        )
        return

    thinking = await update.message.reply_text("🔬 Searching arXiv, Semantic Scholar, and GitHub via Apollo...")
    try:
        from services.apollo_service import fetch_unified_research_context
        results = fetch_unified_research_context(query, top_k=3)
        await thinking.delete()
        await _safe_send_reply(update, results)
    except Exception as e:
        await thinking.delete()
        await update.message.reply_text(f"❌ Research error: {e}")


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
    await _safe_send_reply(update, reply)


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
            "• Or just chat — Aurora extracts goals automatically from your messages"
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

    await _safe_send_reply(update, "\n".join(lines))


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
    await _safe_send_reply(update, text)


# ── Documents (Hybrid GraphRAG) ────────────────────────────────────────────────
async def handle_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle incoming PDF/TXT files sent directly to the Telegram bot."""
    tid = update.effective_user.id
    token = _get_token(tid)
    if not token:
        await update.message.reply_text(
            "🔒 Please log in first with /login to upload study documents.",
            parse_mode="Markdown"
        )
        return

    doc = update.message.document
    filename = doc.file_name or "document.pdf"
    if not filename.lower().endswith((".pdf", ".txt")):
        await update.message.reply_text("⚠️ Please send a `.pdf` or `.txt` document.")
        return

    status_msg = await update.message.reply_text(
        f"⏳ Processing *{filename}*...\nDecomposing topics into Knowledge Graph & Obsidian notes...",
        parse_mode="Markdown"
    )

    try:
        tg_file = await doc.get_file()
        file_bytes = await tg_file.download_as_bytearray()

        files = {"file": (filename, bytes(file_bytes), "application/pdf" if filename.endswith(".pdf") else "text/plain")}
        r = requests.post(
            f"{API_BASE}/documents/upload",
            files=files,
            headers={"Authorization": f"Bearer {token}"},
            timeout=180
        )

        if r.status_code == 200:
            data = r.json().get("document", {})
            title = data.get("title", filename)
            summary = data.get("summary", "")
            topics_count = data.get("topics_created", 0)

            reply = (
                f"✅ *Document Processed & Graph Linked!*\n\n"
                f"📄 *Title:* {title}\n"
                f"📝 *Summary:* {summary}\n"
                f"📚 *Topic Notes Created:* {topics_count} notes with `[[wikilinks]]`\n"
                f"🔗 *Knowledge Graph:* Connected to your topics and goals!\n\n"
                f"💡 _You can now ask questions about this document with /ask or in chat!_"
            )
            await status_msg.edit_text(reply, parse_mode="Markdown")
        else:
            err = r.json().get("detail", r.text[:200])
            await status_msg.edit_text(f"❌ Upload failed: {err}")
    except Exception as e:
        logger.error(f"Document upload error: {e}")
        await status_msg.edit_text(f"❌ Error processing document: {str(e)}")


async def cmd_docs(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """List uploaded study documents."""
    tid = update.effective_user.id
    token = _get_token(tid)
    if not token:
        await update.message.reply_text("🔒 Please log in first with /login")
        return

    try:
        r = requests.get(f"{API_BASE}/documents/", headers={"Authorization": f"Bearer {token}"}, timeout=10)
        docs = r.json().get("documents", [])
        if not docs:
            await update.message.reply_text(
                "📄 *No documents uploaded yet.*\n\n"
                "Send any `.pdf` or `.txt` study material to this chat, and I'll automatically break it down into Knowledge Graph notes!",
                parse_mode="Markdown"
            )
            return

        lines = ["📚 *Your Uploaded Documents:*\n"]
        for d in docs:
            lines.append(f"• 📄 *{d['title']}* ({d['filename']})")
            if d.get("summary"):
                lines.append(f"  _{d['summary'][:120]}..._")
            lines.append("")

        lines.append("💡 _Ask anything about these documents using /ask_")
        await _safe_send_reply(update, "\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"❌ Could not fetch documents: {e}")


# ── /model (Switch AI Provider & Model) ────────────────────────────────────────
async def cmd_model(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Display active AI model and inline buttons to switch providers."""
    tid = update.effective_user.id
    token = _get_token(tid)
    if not token:
        await update.message.reply_text("🔒 Please log in first with /login")
        return

    try:
        r = requests.get(f"{API_BASE}/llm/", headers={"Authorization": f"Bearer {token}"}, timeout=10)
        data = r.json()
        curr = data.get("current", {})
        active_desc = f"*{curr.get('provider', 'unknown').upper()}* (`{curr.get('model', 'default')}`)"
        if curr.get("is_local"):
            active_desc += " [⚡ Offline Local]"

        options = data.get("options", [])
        configured_opts = [opt for opt in options if opt.get("configured")]
        if not configured_opts:
            configured_opts = [{"id": "gemini", "name": "Google Gemini", "default_model": "gemini-3.1-flash-lite"}]

        buttons = []
        row = []
        for opt in configured_opts:
            prov = opt.get("id")
            pname = opt.get("name", prov.capitalize())
            mname = opt.get("default_model")
            btn = InlineKeyboardButton(f"{pname} ({mname})", callback_data=f"llm:{prov}:{mname}")
            row.append(btn)
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

        keyboard = InlineKeyboardMarkup(buttons)

        await update.message.reply_text(
            f"🧠 *AI Model Settings*\n\n"
            f"Currently Active: {active_desc}\n\n"
            f"Tap an option below to switch Aurora's brain dynamically:",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Fetch LLM status error: {e}")
        await update.message.reply_text(f"❌ Could not retrieve model status: {e}")


async def handle_model_switch(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle inline button click for switching LLM."""
    query = update.callback_query
    await query.answer()

    tid = update.effective_user.id
    token = _get_token(tid)
    if not token:
        await query.edit_message_text("🔒 Session expired. Please log in with /login")
        return

    # callback format: "llm:<provider>:<model>"
    parts = query.data.split(":")
    if len(parts) >= 3:
        provider = parts[1]
        model = parts[2]
        try:
            r = requests.post(
                f"{API_BASE}/llm/switch",
                json={"provider": provider, "model": model},
                headers={"Authorization": f"Bearer {token}"},
                timeout=10
            )
            res = r.json()
            if res.get("status") == "success":
                await query.edit_message_text(
                    f"✅ *AI Provider Switched Successfully!*\n\n"
                    f"• Provider: `{provider}`\n"
                    f"• Model: `{model}`\n\n"
                    f"All new queries and document notes will now use this model!",
                    parse_mode="Markdown"
                )
            else:
                err = res.get("detail", "Switch failed")
                await query.edit_message_text(f"❌ Switch failed: {err}")
        except Exception as e:
            logger.error(f"Switch LLM error: {e}")
            await query.edit_message_text(f"❌ Connection error: {e}")


# ── /help ──────────────────────────────────────────────────────────────────────
async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌟 *Aurora Bot — Commands*\n\n"
        "*Auth*\n"
        "/login — connect your Aurora account\n"
        "/logout — sign out\n\n"
        "*AI Chat & Models*\n"
        "💬 _Just type any question directly to chat!_\n"
        "/ask <question> — chat via slash command\n"
        "/plan — plan your day based on your goals\n"
        "/model — switch AI model (Local, Gemini, OpenAI, Groq, Claude)\n\n"
        "*Study Documents (Hybrid RAG)*\n"
        "/docs — list your uploaded documents\n"
        "📎 _(Send any .pdf or .txt file directly to upload & structure into KG)_\n\n"
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
    BotCommand("start",    "👋 Welcome and login status"),
    BotCommand("login",    "🔐 Connect your Aurora account"),
    BotCommand("logout",   "🚪 Sign out"),
    BotCommand("ask",      "💬 Ask Aurora anything"),
    BotCommand("paper",    "🔬 Search arXiv papers & GitHub repos (Apollo)"),
    BotCommand("plan",     "📋 Plan your day based on your goals"),
    BotCommand("model",    "⚙️ Switch AI model (Local, Gemini, OpenAI, Groq)"),
    BotCommand("docs",     "📄 View uploaded study documents"),
    BotCommand("goals",    "🎯 View your active goals"),
    BotCommand("addgoal",  "➕ Add a new goal (e.g. /addgoal Lose weight high)"),
    BotCommand("stats",    "📊 Productivity dashboard and KG stats"),
    BotCommand("help",     "❓ List all commands"),
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
    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("logout",   cmd_logout))
    app.add_handler(CommandHandler("ask",      cmd_ask))
    app.add_handler(CommandHandler("paper",    cmd_paper))
    app.add_handler(CommandHandler("research", cmd_paper))
    app.add_handler(CommandHandler("plan",     cmd_plan))
    app.add_handler(CommandHandler("model",    cmd_model))
    app.add_handler(CommandHandler("llm",      cmd_model))
    app.add_handler(CommandHandler("docs",     cmd_docs))
    app.add_handler(CommandHandler("goals",    cmd_goals))
    app.add_handler(CommandHandler("addgoal",  cmd_addgoal))
    app.add_handler(CommandHandler("stats",    cmd_stats))
    app.add_handler(CommandHandler("help",     cmd_help))
    app.add_handler(CallbackQueryHandler(handle_model_switch, pattern="^llm:"))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    # Direct chat handler for normal text messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_direct_chat))

    print("[Bot] Aurora Telegram Bot is running. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
