"""
routes/chat.py — Chat API & Context Inspection Endpoints

Endpoints:
  POST /api/chat/                — Send message through CRAG agent (optional debug=true)
  GET  /api/chat/context-preview — View exact KG + Document context brief for any query
  GET  /api/chat/history         — View past chat history
  POST /api/chat/clear           — Clear chat history
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Optional
from services.llm_service import chat, clear_history, get_chat_history
from services.auth_service import get_current_user
from services.context_builder import build_context_md

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    debug: bool = False


class ClearRequest(BaseModel):
    session_id: str = "default"


@router.post("/")
async def send_message(body: ChatRequest, user: dict = Depends(get_current_user)):
    """
    Send a message through the LangGraph CRAG Agent.
    If debug=True, returns the reply along with the exact Knowledge Graph context brief and strategy.
    """
    try:
        session_key = f"{body.session_id}-{user['id']}"
        if body.debug:
            details = chat(body.message, session_key, user_id=user["id"], return_details=True)
            return {
                "reply": details["reply"],
                "session_id": body.session_id,
                "debug": {
                    "strategy": details["strategy"],
                    "kg_nodes_used": details["kg_nodes_used"],
                    "context_relevant": details["context_relevant"],
                    "latency_ms": details["latency_ms"],
                    "injected_context": details["context_md"]
                }
            }
        else:
            reply = chat(body.message, session_key, user_id=user["id"], return_details=False)
            return {"reply": reply, "session_id": body.session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/context-preview")
async def preview_context(
    query: Optional[str] = Query("", description="Optional query to test Hybrid Document & KG matching"),
    user: dict = Depends(get_current_user)
):
    """
    Preview the exact Knowledge Graph + Document context brief
    that is constructed and passed to Gemini for this user.
    """
    context_md, count = build_context_md(user_id=user["id"], query=query or "")
    return {
        "user_id": user["id"],
        "query": query,
        "nodes_and_chunks_count": count,
        "has_context": bool(context_md.strip()),
        "context_brief": context_md
    }


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
