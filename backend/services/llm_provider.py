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
                return data["choices"][0]["message"]["content"]
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


def get_llm_provider(
    provider_name: Optional[str] = None,
    model_name: Optional[str] = None
) -> BaseLLMProvider:
    """
    Factory to retrieve or instantiate the configured LLM provider.
    Defaults to LLM_PROVIDER in .env (or 'gemini').
    """
    provider = (provider_name or os.getenv("LLM_PROVIDER", "gemini")).lower()
    
    cache_key = f"{provider}:{model_name or ''}"
    if cache_key in _PROVIDER_CACHE:
        return _PROVIDER_CACHE[cache_key]

    instance: BaseLLMProvider

    if provider == "gemini":
        model = model_name or os.getenv("LLM_MODEL", "gemini-3.1-flash-lite")
        instance = GoogleGeminiProvider(model_name=model)

    elif provider == "openai":
        model = model_name or os.getenv("LLM_MODEL", "gpt-4o-mini")
        api_key = os.getenv("OPENAI_API_KEY", "")
        instance = OpenAICompatibleProvider(model_name=model, api_key=api_key)

    elif provider == "anthropic":
        model = model_name or os.getenv("LLM_MODEL", "claude-3-5-sonnet-20241022")
        instance = AnthropicProvider(model_name=model)

    elif provider == "groq":
        model = model_name or os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
        api_key = os.getenv("GROQ_API_KEY", "")
        instance = OpenAICompatibleProvider(
            model_name=model,
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1"
        )

    elif provider in ("local", "ollama", "lmstudio", "vllm"):
        model = model_name or os.getenv("LLM_MODEL", "llama3.2")
        local_url = os.getenv("LOCAL_LLM_URL", "http://localhost:11434/v1")
        instance = OpenAICompatibleProvider(
            model_name=model,
            api_key="local-not-needed",
            base_url=local_url
        )

    else:
        # Fallback to Gemini
        model = model_name or "gemini-3.1-flash-lite"
        instance = GoogleGeminiProvider(model_name=model)

    _PROVIDER_CACHE[cache_key] = instance
    return instance


def get_current_llm_info() -> Dict[str, str]:
    """Return details about the currently active LLM provider and model."""
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    default_models = {
        "gemini": "gemini-3.1-flash-lite",
        "openai": "gpt-4o-mini",
        "anthropic": "claude-3-5-sonnet-20241022",
        "groq": "llama-3.3-70b-versatile",
        "local": "llama3.2"
    }
    model = os.getenv("LLM_MODEL", default_models.get(provider, "gemini-3.1-flash-lite"))
    return {
        "provider": provider,
        "model": model,
        "is_local": provider in ("local", "ollama", "lmstudio", "vllm"),
        "local_url": os.getenv("LOCAL_LLM_URL", "http://localhost:11434/v1") if provider in ("local", "ollama") else None
    }
