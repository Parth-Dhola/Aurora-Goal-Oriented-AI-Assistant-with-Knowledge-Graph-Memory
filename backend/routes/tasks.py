from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from models.database import get_db
from services.auth_service import get_current_user
from datetime import datetime

router = APIRouter()

class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    priority: str = "medium"
    category: str = "general"
    due_date: Optional[str] = None

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    category: Optional[str] = None
    due_date: Optional[str] = None
    status: Optional[str] = None

@router.get("/")
async def get_tasks(status: Optional[str] = None, user: dict = Depends(get_current_user)):
    conn = get_db()
    if status:
        rows = conn.execute("SELECT * FROM tasks WHERE status=? ORDER BY created_at DESC", (status,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()
    conn.close()
    return {"tasks": [dict(r) for r in rows]}

@router.get("/today")
async def today_tasks(user: dict = Depends(get_current_user)):
    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM tasks
        WHERE (due_date=? OR due_date IS NULL) AND status='pending'
        ORDER BY CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END
    """, (today,)).fetchall()
    conn.close()
    return {"tasks": [dict(r) for r in rows]}

@router.post("/", status_code=201)
async def create_task(body: TaskCreate, user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO tasks (title, description, priority, category, due_date) VALUES (?,?,?,?,?)",
        (body.title, body.description, body.priority, body.category, body.due_date)
    )
    conn.commit()
    task_id = cursor.lastrowid
    conn.close()
    return {"id": task_id, "status": "created"}

@router.patch("/{task_id}")
async def update_task(task_id: int, body: TaskUpdate, user: dict = Depends(get_current_user)):
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    fields, values = [], []
    if data.get("status") == "done":
        fields.append("completed_at = ?")
        values.append(datetime.now().isoformat())
    for key, value in data.items():
        fields.append(f"{key} = ?")
        values.append(value)
    values.append(task_id)
    conn = get_db()
    conn.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id=?", values)
    conn.commit()
    conn.close()
    return {"status": "updated"}

@router.delete("/{task_id}")
async def delete_task(task_id: int, user: dict = Depends(get_current_user)):
    conn = get_db()
    conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}
