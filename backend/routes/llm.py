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
    """Return active LLM provider, all supported options, and Apollo MCP status."""
    from services.apollo_service import is_apollo_available
    mcp_online = is_apollo_available()
    return {
        "current": get_current_llm_info(),
        "options": get_available_llm_options(only_configured=True),
        "mcp": {
            "name": "Apollo Anti-Poison & Anti-Hallucination Research MCP",
            "online": mcp_online,
            "status": "online" if mcp_online else "offline",
            "sources": ["arXiv", "Semantic Scholar", "GitHub", "DuckDuckGo"] if mcp_online else ["DuckDuckGo"],
            "reranker": "FlashRank CPU Cross-Encoder (<25ms)" if mcp_online else "none",
            "anti_poison": "active" if mcp_online else "inactive",
            "repo_url": "https://github.com/Parth-Dhola/Apollo-AntiPoison-AntiHallucination-Research-MCP"
        }
    }


@router.get("/mcp")
async def get_mcp_status(user: dict = Depends(get_current_user)):
    """Return detailed status of the Apollo Anti-Poison & Anti-Hallucination Research MCP Server."""
    from services.apollo_service import is_apollo_available
    mcp_online = is_apollo_available()
    return {
        "name": "Apollo Anti-Poison & Anti-Hallucination Research MCP",
        "online": mcp_online,
        "status": "online" if mcp_online else "offline",
        "sources": ["arXiv", "Semantic Scholar", "GitHub", "DuckDuckGo"] if mcp_online else ["DuckDuckGo"],
        "reranker": "FlashRank CPU Cross-Encoder (<25ms)" if mcp_online else "none",
        "anti_poison": "active" if mcp_online else "inactive",
        "repo_url": "https://github.com/Parth-Dhola/Apollo-AntiPoison-AntiHallucination-Research-MCP"
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

