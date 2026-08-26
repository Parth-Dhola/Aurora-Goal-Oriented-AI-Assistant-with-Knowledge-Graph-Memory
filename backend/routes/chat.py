from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from services.llm_service import chat, clear_history, get_chat_history
from services.auth_service import get_current_user

router = APIRouter()

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"

class ClearRequest(BaseModel):
    session_id: str = "default"

@router.post("/")
async def send_message(body: ChatRequest, user: dict = Depends(get_current_user)):
    try:
        reply = chat(body.message, f"{body.session_id}-{user['id']}", user_id=user["id"])
        return {"reply": reply, "session_id": body.session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history")
async def get_history(session_id: str = "default", user: dict = Depends(get_current_user)):
    history = get_chat_history(f"{session_id}-{user['id']}", limit=50)
    return {"history": history}

@router.post("/clear")
async def clear(body: ClearRequest, user: dict = Depends(get_current_user)):
    try:
        clear_history(f"{body.session_id}-{user['id']}")
        return {"status": "cleared"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
