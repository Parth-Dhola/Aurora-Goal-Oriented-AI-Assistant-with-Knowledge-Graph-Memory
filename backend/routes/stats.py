from fastapi import APIRouter, Depends
from models.database import get_db
from services.auth_service import get_current_user
from services.llm_provider import get_current_llm_info
from datetime import datetime, timedelta

router = APIRouter()
PLACEMENT_DATE = "2025-12-01"


@router.get("/")
async def get_stats(user: dict = Depends(get_current_user)):
    conn = get_db()

    # Tasks
    total    = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    done     = conn.execute("SELECT COUNT(*) FROM tasks WHERE status='done'").fetchone()[0]
    pending  = conn.execute("SELECT COUNT(*) FROM tasks WHERE status='pending'").fetchone()[0]
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    this_week = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE completed_at>=?", (week_ago,)
    ).fetchone()[0]
    cats = conn.execute(
        "SELECT category, COUNT(*) as count FROM tasks WHERE status='done' GROUP BY category"
    ).fetchall()

    # Chat
    total_msg = conn.execute(
        "SELECT COUNT(*) FROM chat_history WHERE role='user'"
    ).fetchone()[0]

    # LLM logs
    total_llm  = conn.execute("SELECT COUNT(*) FROM llm_logs").fetchone()[0]
    raw_lat    = conn.execute("SELECT AVG(latency_ms) FROM llm_logs").fetchone()[0]

    # Strategy breakdown (CRAG)
    strategies = conn.execute("""
        SELECT strategy, COUNT(*) as count, AVG(latency_ms) as avg_latency
        FROM   llm_logs
        WHERE  strategy IS NOT NULL
        GROUP BY strategy
    """).fetchall()

    # Knowledge graph stats (scoped to this user)
    kg_goals = conn.execute(
        "SELECT COUNT(*) FROM kg_nodes WHERE user_id=? AND type='goal' AND status='active'",
        (user["id"],)
    ).fetchone()[0]
    kg_facts = conn.execute(
        "SELECT COUNT(*) FROM kg_edges WHERE user_id=?",
        (user["id"],)
    ).fetchone()[0]

    conn.close()

    days = (datetime.strptime(PLACEMENT_DATE, "%Y-%m-%d") - datetime.now()).days

    return {
        "tasks": {
            "total":           total,
            "done":            done,
            "pending":         pending,
            "this_week":       this_week,
            "completion_rate": round(done / total * 100, 1) if total > 0 else 0,
        },
        "chat": {"total_messages": total_msg},
        "llm": {
            "active_provider": get_current_llm_info(),
            "total_calls":    total_llm,
            "avg_latency_ms": round(raw_lat, 1) if raw_lat else 0,
            "strategies": [
                {
                    "strategy":    s["strategy"],
                    "count":       s["count"],
                    "avg_latency": round(s["avg_latency"], 1) if s["avg_latency"] else 0,
                }
                for s in strategies
            ],
        },
        "knowledge_graph": {
            "active_goals": kg_goals,
            "total_facts":  kg_facts,
        },
        "placement": {"days_remaining": days, "target_date": PLACEMENT_DATE},
        "categories": [
            {"category": r["category"], "count": r["count"]} for r in cats
        ],
    }
