from fastapi import APIRouter, Depends
from pydantic import BaseModel
from models.database import get_db
from services.auth_service import get_current_user

router = APIRouter()

class ReminderCreate(BaseModel):
    title: str
    remind_at: str
    repeat: str = "none"

@router.get("/")
async def get_reminders(user: dict = Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute("SELECT * FROM reminders ORDER BY remind_at ASC").fetchall()
    conn.close()
    return {"reminders": [dict(r) for r in rows]}

@router.post("/", status_code=201)
async def create_reminder(body: ReminderCreate, user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO reminders (title, remind_at, repeat) VALUES (?,?,?)",
        (body.title, body.remind_at, body.repeat)
    )
    conn.commit()
    rid = cursor.lastrowid
    conn.close()
    return {"id": rid, "status": "created"}

@router.delete("/{rid}")
async def delete_reminder(rid: int, user: dict = Depends(get_current_user)):
    conn = get_db()
    conn.execute("DELETE FROM reminders WHERE id=?", (rid,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}
