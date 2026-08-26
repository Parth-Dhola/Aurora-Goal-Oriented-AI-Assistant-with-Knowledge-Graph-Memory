"""
goals.py — Goals CRUD API

Two creation paths feed the same kg_nodes table:
  POST /api/goals  → explicit, structured, source='api'   (urgent/high priority)
  chat messages    → extracted by kg_service, source='chat' (any priority)

Both show up in GET /api/goals and in the KG context brief.
"""

import json
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from models.database import get_db
from services.auth_service import get_current_user
from services.kg_service import create_goal_node

router = APIRouter()


class GoalCreate(BaseModel):
    label:    str
    priority: str          = "high"   # urgent | high | medium | low
    target:   Optional[str] = None
    deadline: Optional[str] = None


class GoalUpdate(BaseModel):
    priority: Optional[str] = None
    status:   Optional[str] = None    # active | completed | archived
    target:   Optional[str] = None
    deadline: Optional[str] = None


@router.post("/", status_code=201)
async def create_goal(body: GoalCreate, user: dict = Depends(get_current_user)):
    """
    Explicitly register a goal (source='api').
    Use this for important / urgent goals where you want full structure:
    label, priority, measurable target, and deadline.
    """
    if body.priority not in ("urgent", "high", "medium", "low"):
        raise HTTPException(400, "priority must be one of: urgent, high, medium, low")

    node_id = create_goal_node(
        user_id=user["id"],
        label=body.label,
        priority=body.priority,
        source="api",
        target=body.target,
        deadline=body.deadline,
    )
    return {
        "id":       node_id,
        "label":    body.label,
        "priority": body.priority,
        "source":   "api",
    }


@router.get("/")
async def list_goals(user: dict = Depends(get_current_user)):
    """
    List all goals for the current user (active + archived).
    Goals from both API creation and chat extraction are included.
    """
    conn = get_db()
    rows = conn.execute(
        """
        SELECT id, label, priority, status, source, properties, created_at, updated_at
        FROM   kg_nodes
        WHERE  user_id=? AND type='goal'
        ORDER BY
            CASE priority
                WHEN 'urgent' THEN 1 WHEN 'high'   THEN 2
                WHEN 'medium' THEN 3 WHEN 'low'    THEN 4
                ELSE 5 END,
            created_at DESC
        """,
        (user["id"],),
    ).fetchall()
    conn.close()

    goals = []
    for r in rows:
        try:
            props = json.loads(r["properties"] or "{}")
        except Exception:
            props = {}
        goals.append({
            "id":         r["id"],
            "label":      r["label"],
            "priority":   r["priority"],
            "status":     r["status"],
            "source":     r["source"],
            "target":     props.get("target"),
            "deadline":   props.get("deadline"),
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        })
    return {"goals": goals}


@router.patch("/{goal_id}")
async def update_goal(goal_id: int, body: GoalUpdate,
                      user: dict = Depends(get_current_user)):
    """Update a goal's priority, status, target, or deadline."""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM kg_nodes WHERE id=? AND user_id=? AND type='goal'",
        (goal_id, user["id"]),
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Goal not found")

    try:
        props = json.loads(row["properties"] or "{}")
    except Exception:
        props = {}
    if body.target   is not None: props["target"]   = body.target
    if body.deadline is not None: props["deadline"]  = body.deadline

    updates = {"properties": json.dumps(props)}
    if body.priority: updates["priority"] = body.priority
    if body.status:   updates["status"]   = body.status

    set_clause = ", ".join(f"{k}=?" for k in updates)
    values     = list(updates.values()) + [goal_id]
    conn.execute(
        f"UPDATE kg_nodes SET {set_clause}, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        values,
    )
    conn.commit()
    conn.close()
    return {"id": goal_id, "updated": True}


@router.delete("/{goal_id}")
async def archive_goal(goal_id: int, user: dict = Depends(get_current_user)):
    """Soft-delete (archive) a goal."""
    conn = get_db()
    conn.execute(
        "UPDATE kg_nodes SET status='archived', updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?",
        (goal_id, user["id"]),
    )
    conn.commit()
    conn.close()
    return {"id": goal_id, "status": "archived"}

