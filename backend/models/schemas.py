"""
models/schemas.py — Pydantic Schemas for Aurora API Request & Response Validation
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# ── Auth Schemas ──────────────────────────────────────────────────────────────
class UserAuth(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=4, max_length=100)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str


class UserProfile(BaseModel):
    id: int
    username: str
    created_at: str


# ── Chat Schemas ──────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: Optional[str] = "default"


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    status: str = "success"


# ── Goals Schemas ─────────────────────────────────────────────────────────────
class GoalCreate(BaseModel):
    label: str = Field(..., min_length=1)
    priority: Optional[str] = "medium"
    target: Optional[str] = None
    deadline: Optional[str] = None
    properties: Optional[Dict[str, Any]] = None


class GoalUpdate(BaseModel):
    label: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    target: Optional[str] = None
    deadline: Optional[str] = None
    properties: Optional[Dict[str, Any]] = None


# ── Tasks Schemas ─────────────────────────────────────────────────────────────
class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1)
    description: Optional[str] = None
    priority: Optional[str] = "medium"
    category: Optional[str] = "general"
    due_date: Optional[str] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    category: Optional[str] = None
    due_date: Optional[str] = None


# ── Reminders Schemas ─────────────────────────────────────────────────────────
class ReminderCreate(BaseModel):
    title: str = Field(..., min_length=1)
    remind_at: str
    repeat: Optional[str] = "none"


# ── LLM Management Schemas ────────────────────────────────────────────────────
class LLMSwitchRequest(BaseModel):
    provider: str
    model: Optional[str] = None


class LLMStatusResponse(BaseModel):
    current: Dict[str, Any]
    options: List[Dict[str, Any]]
