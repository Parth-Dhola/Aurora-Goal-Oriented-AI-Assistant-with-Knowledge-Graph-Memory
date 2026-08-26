import sqlite3
import os
from dotenv import load_dotenv

load_dotenv()
DB_PATH = os.getenv("DB_PATH", "aurora.db")


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")   # safe for multi-thread SQLite
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # ── Original tables ────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            title        TEXT NOT NULL,
            description  TEXT,
            priority     TEXT DEFAULT 'medium',
            status       TEXT DEFAULT 'pending',
            category     TEXT DEFAULT 'general',
            due_date     TEXT,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            role       TEXT NOT NULL,
            content    TEXT NOT NULL,
            session_id TEXT DEFAULT 'default',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS llm_logs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt_hash     TEXT,
            prompt_version  TEXT DEFAULT 'crag-kg-v1',
            input_tokens    INTEGER,
            output_tokens   INTEGER,
            latency_ms      REAL,
            model           TEXT,
            response_length INTEGER,
            strategy        TEXT DEFAULT 'direct',
            kg_nodes_used   INTEGER DEFAULT 0,
            context_relevant INTEGER DEFAULT 0,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            title      TEXT NOT NULL,
            remind_at  TEXT NOT NULL,
            repeat     TEXT DEFAULT 'none',
            sent       INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Knowledge Graph tables ─────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kg_nodes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER,
            type       TEXT NOT NULL,
            label      TEXT NOT NULL,
            priority   TEXT DEFAULT 'medium',
            source     TEXT DEFAULT 'chat',
            status     TEXT DEFAULT 'active',
            properties TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kg_edges (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER,
            source_id  INTEGER,
            target_id  INTEGER,
            relation   TEXT NOT NULL,
            weight     REAL DEFAULT 1.0,
            context    TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Telegram bot sessions ──────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS telegram_sessions (
            telegram_user_id INTEGER PRIMARY KEY,
            telegram_username TEXT,
            aurora_username   TEXT NOT NULL,
            jwt_token         TEXT NOT NULL,
            created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Migrate existing llm_logs if columns missing ───────────────────────────
    existing_cols = [
        row[1] for row in cursor.execute("PRAGMA table_info(llm_logs)").fetchall()
    ]
    for col, definition in [
        ("strategy",         "TEXT DEFAULT 'direct'"),
        ("kg_nodes_used",    "INTEGER DEFAULT 0"),
        ("context_relevant", "INTEGER DEFAULT 0"),
    ]:
        if col not in existing_cols:
            cursor.execute(f"ALTER TABLE llm_logs ADD COLUMN {col} {definition}")

    try:
        conn.commit()
        print("[Aurora DB] All tables ready.")
    except Exception as e:
        print(f"[Aurora DB] Error: {e}")
    finally:
        conn.close()
