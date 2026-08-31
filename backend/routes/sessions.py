"""
routes/sessions.py — Multi-Session Thread Management API

Endpoints:
  GET    /api/sessions/                     — List user's sessions
  POST   /api/sessions/                     — Create a new session
  GET    /api/sessions/{session_id}/messages — Get session history
  DELETE /api/sessions/{session_id}         — Delete a session
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from services.auth_service import get_current_user
from services.session_service import (
    list_user_sessions,
    create_user_session,
    get_session_messages,
    delete_user_session
)

router = APIRouter()


class CreateSessionRequest(BaseModel):
    title: Optional[str] = None
    session_id: Optional[str] = None


@router.get("/")
async def get_sessions(user: dict = Depends(get_current_user)):
    """List all chat sessions for the authenticated user."""
    sessions = list_user_sessions(user["id"])
    return {"sessions": sessions}


@router.post("/")
async def new_session(body: CreateSessionRequest, user: dict = Depends(get_current_user)):
    """Create a new chat session."""
    try:
        session = create_user_session(user["id"], title=body.title, session_id=body.session_id)
        return {"status": "created", "session": session}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{session_id}/messages")
async def get_messages(session_id: str, user: dict = Depends(get_current_user)):
    """Get message history for a specific session."""
    messages = get_session_messages(user["id"], session_id)
    return {"session_id": session_id, "messages": messages}


@router.delete("/{session_id}")
async def remove_session(session_id: str, user: dict = Depends(get_current_user)):
    """Delete a chat session and its history."""
    delete_user_session(user["id"], session_id)
    return {"status": "deleted", "session_id": session_id}
