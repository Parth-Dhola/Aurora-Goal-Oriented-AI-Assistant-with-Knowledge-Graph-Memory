"""
routes/llm.py — Endpoints for inspecting and switching active LLM providers at runtime
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from services.auth_service import get_current_user
from services.llm_provider import (
    get_current_llm_info,
    get_available_llm_options,
    set_active_llm
)

router = APIRouter()


class LLMSwitchRequest(BaseModel):
    provider: str
    model: Optional[str] = None


@router.get("/")
async def get_llm_status(user: dict = Depends(get_current_user)):
    """Return active LLM provider and all supported options."""
    return {
        "current": get_current_llm_info(),
        "options": get_available_llm_options()
    }


@router.post("/switch")
async def switch_llm(req: LLMSwitchRequest, user: dict = Depends(get_current_user)):
    """Switch active LLM provider and model dynamically."""
    valid_providers = ["gemini", "openai", "anthropic", "groq", "local", "ollama"]
    if req.provider.lower() not in valid_providers:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid provider '{req.provider}'. Choose from {valid_providers}"
        )
    
    updated = set_active_llm(provider=req.provider, model=req.model)
    return {
        "status": "success",
        "message": f"Switched to {updated['provider']} ({updated['model']})",
        "current": updated
    }

