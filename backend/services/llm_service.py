"""
llm_service.py — Public chat interface

Wires the CRAG agent, SQLite chat history, and MLflow logging.
All route handlers call chat() — nothing else needs to change.
"""

import os
import hashlib
from dotenv import load_dotenv
import google.generativeai as genai
from models.database import get_db
from services.crag_agent import run_agent
from services.mlflow_service import log_agent_run

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


# ── Chat history (for display / Android app) ───────────────────────────────────
def get_chat_history(session_id: str = "default", limit: int = 50) -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT role, content FROM chat_history WHERE session_id=? ORDER BY created_at DESC LIMIT ?",
        (session_id, limit),
    ).fetchall()
    conn.close()
    rows.reverse()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


def save_message(role: str, content: str, session_id: str = "default") -> None:
    conn = get_db()
    conn.execute(
        "INSERT INTO chat_history (role, content, session_id) VALUES (?,?,?)",
        (role, content, session_id),
    )
    conn.commit()
    conn.close()


def clear_history(session_id: str = "default") -> None:
    conn = get_db()
    conn.execute("DELETE FROM chat_history WHERE session_id=?", (session_id,))
    conn.commit()
    conn.close()


# ── SQLite logging ─────────────────────────────────────────────────────────────
def _log_to_db(query: str, answer: str, latency_ms: float, strategy: str,
               kg_nodes_used: int, context_relevant: bool,
               model: str = "gemini-3.1-flash-lite") -> None:
    prompt_hash   = hashlib.md5(query.encode()).hexdigest()[:8]
    input_tokens  = len(query.split())
    output_tokens = len(answer.split())
    conn = get_db()
    conn.execute(
        """INSERT INTO llm_logs
           (model, prompt_version, prompt_hash, latency_ms,
            input_tokens, output_tokens, response_length,
            strategy, kg_nodes_used, context_relevant)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (model, "crag-kg-v1", prompt_hash, latency_ms,
         input_tokens, output_tokens, len(answer),
         strategy, kg_nodes_used, 1 if context_relevant else 0),
    )
    conn.commit()
    conn.close()


# ── Main chat function ─────────────────────────────────────────────────────────
def chat(user_message: str, session_id: str = "default", user_id: int = 1, return_details: bool = False):
    """
    Process a user message through the CRAG agent and return Aurora's reply.

    session_id     : used for LangGraph checkpointing + chat_history display
    user_id        : scopes the knowledge graph to this user
    return_details : if True, returns dict with reply + full context_md and CRAG metadata
    """
    save_message("user", user_message, session_id)

    result = run_agent(user_message, user_id=user_id, session_id=session_id)

    reply            = result.get("answer") or "I couldn't generate a response. Please try again."
    latency_ms       = result.get("latency_ms", 0.0)
    strategy         = result.get("strategy", "direct")
    kg_nodes_used    = result.get("kg_nodes_used", 0)
    context_relevant = result.get("context_relevant", False)
    context_md       = result.get("context_md", "")

    save_message("model", reply, session_id)
    _log_to_db(user_message, reply, latency_ms, strategy, kg_nodes_used, context_relevant)
    log_agent_run(
        query=user_message, answer=reply, strategy=strategy,
        latency_ms=latency_ms, kg_nodes_used=kg_nodes_used,
        context_relevant=context_relevant,
    )

    if return_details:
        return {
            "reply": reply,
            "strategy": strategy,
            "kg_nodes_used": kg_nodes_used,
            "context_relevant": context_relevant,
            "context_md": context_md,
            "latency_ms": latency_ms
        }

    return reply
