"""
services/session_service.py — Multi-Session Chat & Thread Management
"""
import uuid
import datetime
from models.database import get_db


def list_user_sessions(user_id: int) -> list:
    """Return all chat sessions for the user with message counts."""
    conn = get_db()
    # Ensure default session exists
    row = conn.execute(
        "SELECT id FROM chat_sessions WHERE user_id = ? AND session_id = ?",
        (user_id, "default")
    ).fetchone()
    if not row:
        conn.execute(
            "INSERT INTO chat_sessions (user_id, session_id, title) VALUES (?, ?, ?)",
            (user_id, "default", "Main Chat")
        )
        conn.commit()

    rows = conn.execute("""
        SELECT s.id, s.session_id, s.title, s.created_at, s.updated_at,
               COUNT(h.id) as message_count
        FROM chat_sessions s
        LEFT JOIN chat_history h ON (h.session_id = s.session_id OR h.session_id = s.session_id || '-' || s.user_id)
        WHERE s.user_id = ?
        GROUP BY s.id
        ORDER BY s.updated_at DESC
    """, (user_id,)).fetchall()
    return [dict(r) for r in rows]


def create_user_session(user_id: int, title: str = None, session_id: str = None) -> dict:
    """Create a new chat session for user."""
    conn = get_db()
    if not session_id:
        session_id = f"sess_{uuid.uuid4().hex[:10]}"
    if not title or not title.strip():
        title = f"Chat {datetime.datetime.now().strftime('%b %d, %H:%M')}"

    conn.execute(
        "INSERT INTO chat_sessions (user_id, session_id, title) VALUES (?, ?, ?)",
        (user_id, session_id, title.strip())
    )
    conn.commit()
    return {"user_id": user_id, "session_id": session_id, "title": title.strip()}


def get_session_messages(user_id: int, session_id: str, limit: int = 100) -> list:
    """Retrieve ordered message history for a specific session."""
    conn = get_db()
    rows = conn.execute("""
        SELECT id, role, content, session_id, created_at
        FROM chat_history
        WHERE session_id = ? OR session_id = ?
        ORDER BY id ASC
        LIMIT ?
    """, (session_id, f"{session_id}-{user_id}", limit)).fetchall()
    return [dict(r) for r in rows]


def delete_user_session(user_id: int, session_id: str) -> bool:
    """Delete a session and clear its history."""
    conn = get_db()
    conn.execute("DELETE FROM chat_sessions WHERE user_id = ? AND session_id = ?", (user_id, session_id))
    conn.execute("DELETE FROM chat_history WHERE session_id = ? OR session_id = ?", (session_id, f"{session_id}-{user_id}"))
    conn.commit()
    return True


def touch_session(user_id: int, session_id: str, auto_title_from_msg: str = None):
    """Update session updated_at timestamp or create session if missing."""
    conn = get_db()
    clean_id = session_id.split("-")[0] if "-" in session_id else session_id
    row = conn.execute(
        "SELECT id, title FROM chat_sessions WHERE user_id = ? AND session_id = ?",
        (user_id, clean_id)
    ).fetchone()
    if not row:
        title = auto_title_from_msg[:30] if auto_title_from_msg else f"Chat {datetime.datetime.now().strftime('%b %d')}"
        conn.execute(
            "INSERT INTO chat_sessions (user_id, session_id, title) VALUES (?, ?, ?)",
            (user_id, clean_id, title)
        )
    else:
        conn.execute(
            "UPDATE chat_sessions SET updated_at = CURRENT_TIMESTAMP WHERE user_id = ? AND session_id = ?",
            (user_id, clean_id)
        )
    conn.commit()
