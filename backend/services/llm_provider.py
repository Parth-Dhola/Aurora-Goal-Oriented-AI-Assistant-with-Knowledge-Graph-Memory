"""
llm_provider.py — Universal Multi-LLM Provider Engine for Aurora

Supported Providers:
  1. gemini     : Google Gemini (3.1 Flash Lite, 1.5 Pro, 1.5 Flash)
  2. openai     : OpenAI (GPT-4o, GPT-4o-mini, o1)
  3. anthropic  : Anthropic (Claude 3.5 Sonnet, Claude 3.5 Haiku)
  4. groq       : Groq (Llama-3.3-70B-versatile, Mixtral-8x7b)
  5. local      : Local LLM via Ollama (http://localhost:11434/v1), LM Studio, or vLLM

Configured via environment variables:
  LLM_PROVIDER    : gemini | openai | anthropic | groq | local (default: gemini)
  LLM_MODEL       : Model name (e.g. gemini-3.1-flash-lite, gpt-4o-mini, llama3.2, claude-3-5-sonnet-20241022)
  LOCAL_LLM_URL   : http://localhost:11434/v1 (for local / ollama)
"""

import os
import re
import json
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()


class BaseLLMProvider:
    """Abstract interface for all LLM providers."""

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        raise NotImplementedError

    def generate_json(self, prompt: str, system_prompt: str = "") -> Dict[str, Any]:
        """Generate structured JSON output from prompt."""
        raw = self.generate(prompt, system_prompt=system_prompt)
        return self._extract_json(raw)

    def _extract_json(self, text: str) -> Dict[str, Any]:
        text = text.strip()
        if "```" in text:
            parts = text.split("```")
            for p in parts:
                p = p.strip()
                if p.startswith("json"):
                    p = p[4:].strip()
                if p.startswith("{"):
                    text = p
                    break
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            text = match.group()
        try:
            return json.loads(text)
        except Exception:
            return {}


class GoogleGeminiProvider(BaseLLMProvider):
    def __init__(self, model_name: str = "gemini-3.1-flash-lite", api_key: Optional[str] = None):
        import google.generativeai as genai
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if self.api_key:
            genai.configure(api_key=self.api_key)
        self.model_name = model_name
        self._genai = genai

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        full_prompt = f"{system_prompt}\n\n{prompt}".strip() if system_prompt else prompt
        model = self._genai.GenerativeModel(self.model_name)
        response = model.generate_content(full_prompt)
        return response.text if response and hasattr(response, "text") else ""


class OpenAICompatibleProvider(BaseLLMProvider):
    """Handles OpenAI, Groq, Ollama, LM Studio, and vLLM via standard OpenAI-compatible API."""

    def __init__(self, model_name: str, api_key: str = "dummy", base_url: Optional[str] = None):
        import requests
        self.model_name = model_name
        self.api_key = api_key or "not-needed"
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self.requests = requests

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": 0.3
        }
        try:
            r = self.requests.post(f"{self.base_url}/chat/completions", json=payload, headers=headers, timeout=60)
            if r.status_code == 200:
                data = r.json()
                content = data["choices"][0]["message"].get("content", "")
                if "<think>" in content and "</think>" in content:
                    content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
                return content
            elif r.status_code == 404:
                # Fallback to active models on Groq/OpenAI compatible servers
                fallbacks = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.6-27b", "groq/compound"]
                for fb in fallbacks:
                    if fb != self.model_name:
                        payload["model"] = fb
                        r_fb = self.requests.post(f"{self.base_url}/chat/completions", json=payload, headers=headers, timeout=60)
                        if r_fb.status_code == 200:
                            data = r_fb.json()
                            content = data["choices"][0]["message"].get("content", "")
                            if "<think>" in content and "</think>" in content:
                                content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
                            return content
                return f"[LLM Error 404]: Model '{self.model_name}' not found on endpoint."
            else:
                return f"[LLM Error {r.status_code}]: {r.text}"
        except Exception as e:
            return f"[LLM Connection Error]: {e}"


class AnthropicProvider(BaseLLMProvider):
    """Handles Anthropic Claude API."""

    def __init__(self, model_name: str = "claude-3-5-sonnet-20241022", api_key: Optional[str] = None):
        import requests
        self.model_name = model_name
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.requests = requests

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        payload = {
            "model": self.model_name,
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": prompt}]
        }
        if system_prompt:
            payload["system"] = system_prompt
        try:
            r = self.requests.post("https://api.anthropic.com/v1/messages", json=payload, headers=headers, timeout=60)
            if r.status_code == 200:
                data = r.json()
                return data["content"][0]["text"]
            else:
                return f"[Anthropic Error {r.status_code}]: {r.text}"
        except Exception as e:
            return f"[Anthropic Error]: {e}"


_PROVIDER_CACHE: Dict[str, BaseLLMProvider] = {}


_ACTIVE_OVERRIDE: Dict[str, Optional[str]] = {"provider": None, "model": None}

def set_active_llm(provider: str, model: Optional[str] = None) -> Dict[str, Any]:
    """Dynamically switch the active LLM provider and model at runtime."""
    provider = provider.lower().strip()
    _ACTIVE_OVERRIDE["provider"] = provider
    if model:
        _ACTIVE_OVERRIDE["model"] = model.strip()
    else:
        defaults = {
            "gemini": "gemini-3.1-flash-lite",
            "openai": "gpt-4o-mini",
            "anthropic": "claude-3-5-sonnet-20241022",
            "groq": "openai/gpt-oss-120b",
            "local": os.getenv("LLM_MODEL", "qwen3.5-2b")
        }
        _ACTIVE_OVERRIDE["model"] = defaults.get(provider, "gemini-3.1-flash-lite")

    return get_current_llm_info()


def get_available_llm_options(only_configured: bool = False) -> list:
    """Return all supported LLM providers with available models and active status."""
    load_dotenv(override=True)
    curr = get_current_llm_info()

    # Check if local LLM is currently active or alive on network
    local_url = os.getenv("LOCAL_LLM_URL", "")
    local_models = []
    local_configured = False
    if local_url:
        try:
            import requests
            r = requests.get(f"{local_url}/models", timeout=0.3)
            if r.status_code == 200:
                local_configured = True
                data = r.json()
                if "data" in data and isinstance(data["data"], list):
                    local_models = [m["id"] for m in data["data"] if "id" in m]
                elif "models" in data and isinstance(data["models"], list):
                    local_models = [m.get("name", m.get("id", "")) for m in data["models"]]
        except Exception:
            local_configured = False
    elif os.getenv("LLM_PROVIDER") in ("local", "ollama", "lmstudio", "vllm"):
        local_configured = True

    if not local_models:
        local_model_default = os.getenv("LOCAL_LLM_MODEL", "qwen3.5-2b")
        local_models = [local_model_default, "llama3.2", "mistral", "deepseek-r1"]
    else:
        local_model_default = local_models[0]

    options = [
        {
            "id": "gemini",
            "name": "Google Gemini",
            "default_model": "gemini-3.1-flash-lite",
            "models": ["gemini-3.1-flash-lite", "gemini-1.5-pro", "gemini-1.5-flash"],
            "configured": bool(os.getenv("GEMINI_API_KEY")),
            "active": curr["provider"] == "gemini"
        },
        {
            "id": "local",
            "name": "Local LLM",
            "default_model": local_model_default,
            "models": local_models,
            "configured": local_configured,
            "active": curr["provider"] in ("local", "ollama", "lmstudio", "vllm")
        },
        {
            "id": "openai",
            "name": "OpenAI",
            "default_model": "gpt-4o-mini",
            "models": ["gpt-4o-mini", "gpt-4o", "o1-mini"],
            "configured": bool(os.getenv("OPENAI_API_KEY")),
            "active": curr["provider"] == "openai"
        },
        {
            "id": "groq",
            "name": "Groq",
            "default_model": "openai/gpt-oss-120b",
            "models": ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.6-27b", "groq/compound"],
            "configured": bool(os.getenv("GROQ_API_KEY")),
            "active": curr["provider"] == "groq"
        },
        {
            "id": "anthropic",
            "name": "Claude",
            "default_model": "claude-3-5-sonnet-20241022",
            "models": ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022"],
            "configured": bool(os.getenv("ANTHROPIC_API_KEY")),
            "active": curr["provider"] == "anthropic"
        }
    ]
    if only_configured:
        return [opt for opt in options if opt["configured"]]
    return options


def get_llm_provider(
    provider_name: Optional[str] = None,
    model_name: Optional[str] = None
) -> BaseLLMProvider:
    """
    Factory to retrieve or instantiate the configured LLM provider.
    Honors runtime overrides, falling back to environment variables.
    """
    provider = (
        provider_name
        or _ACTIVE_OVERRIDE["provider"]
        or os.getenv("LLM_PROVIDER", "gemini")
    ).lower()

    model = (
        model_name
        or _ACTIVE_OVERRIDE["model"]
        or os.getenv("LLM_MODEL")
    )
    
    cache_key = f"{provider}:{model or ''}"
    if cache_key in _PROVIDER_CACHE:
        return _PROVIDER_CACHE[cache_key]

    instance: BaseLLMProvider

    if provider == "gemini":
        target_model = model or "gemini-3.1-flash-lite"
        instance = GoogleGeminiProvider(model_name=target_model)

    elif provider == "openai":
        target_model = model or "gpt-4o-mini"
        api_key = os.getenv("OPENAI_API_KEY", "")
        instance = OpenAICompatibleProvider(model_name=target_model, api_key=api_key)

    elif provider == "anthropic":
        target_model = model or "claude-3-5-sonnet-20241022"
        instance = AnthropicProvider(model_name=target_model)

    elif provider == "groq":
        target_model = model or "openai/gpt-oss-120b"
        api_key = os.getenv("GROQ_API_KEY", "")
        instance = OpenAICompatibleProvider(
            model_name=target_model,
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1"
        )

    elif provider in ("local", "ollama", "lmstudio", "vllm"):
        target_model = model or "qwen3.5-2b"
        local_url = os.getenv("LOCAL_LLM_URL", "http://localhost:11434/v1")
        instance = OpenAICompatibleProvider(
            model_name=target_model,
            api_key="local-not-needed",
            base_url=local_url
        )

    else:
        target_model = model or "gemini-3.1-flash-lite"
        instance = GoogleGeminiProvider(model_name=target_model)

    _PROVIDER_CACHE[cache_key] = instance
    return instance


def get_current_llm_info() -> Dict[str, Any]:
    """Return details about the currently active LLM provider and model."""
    provider = (
        _ACTIVE_OVERRIDE["provider"]
        or os.getenv("LLM_PROVIDER", "gemini")
    ).lower()

    default_models = {
        "gemini": "gemini-3.1-flash-lite",
        "openai": "gpt-4o-mini",
        "anthropic": "claude-3-5-sonnet-20241022",
        "groq": "openai/gpt-oss-120b",
        "local": os.getenv("LLM_MODEL", "qwen3.5-2b")
    }
    model = _ACTIVE_OVERRIDE["model"] or os.getenv("LLM_MODEL", default_models.get(provider, "gemini-3.1-flash-lite"))
    return {
        "provider": provider,
        "model": model,
        "is_local": provider in ("local", "ollama", "lmstudio", "vllm"),
        "local_url": os.getenv("LOCAL_LLM_URL", "http://localhost:11434/v1") if provider in ("local", "ollama") else None
    }

