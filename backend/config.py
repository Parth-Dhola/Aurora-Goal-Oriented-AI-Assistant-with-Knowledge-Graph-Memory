"""
config.py — Centralized Typed Configuration for Aurora Backend
"""
import os
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv

# Locate and load root .env
_BACKEND_DIR = Path(__file__).parent.resolve()
_ROOT_DIR = _BACKEND_DIR.parent if (_BACKEND_DIR / "app.py").exists() and _BACKEND_DIR.name == "backend" else _BACKEND_DIR
load_dotenv(_ROOT_DIR / ".env")
load_dotenv()  # also check current working dir


@dataclass(frozen=True)
class Settings:
    # App info
    APP_NAME: str = "Aurora AI Assistant"
    VERSION: str = "3.0.0"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "production")
    DEBUG: bool = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")

    # Server binding
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    # Database
    DB_PATH: str = os.getenv("DB_PATH", str(_BACKEND_DIR / "aurora.db"))
    CHECKPOINT_DB_PATH: str = os.getenv("CHECKPOINT_DB_PATH", str(_BACKEND_DIR / "checkpoints.db"))

    # Security & JWT Auth
    SECRET_KEY: str = os.getenv("SECRET_KEY", "aurora-super-secret-production-key-change-in-env-987654321")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080")) # 7 days

    # LLM Providers
    DEFAULT_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini")
    DEFAULT_MODEL: str = os.getenv("LLM_MODEL", "gemini-3.1-flash-lite")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    LOCAL_LLM_URL: str = os.getenv("LOCAL_LLM_URL", "http://localhost:8080/v1")
    LOCAL_LLM_MODEL: str = os.getenv("LOCAL_LLM_MODEL", "qwen3.5-2b")

    # Telegram Bot
    TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN", "")

    # MLflow tracking
    MLFLOW_TRACKING_URI: str = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5001")

    # Storage & Vault Paths
    VAULT_DIR: Path = _ROOT_DIR / "obsidian-KG-vault"
    MAX_UPLOAD_SIZE_BYTES: int = 50 * 1024 * 1024  # 50 MB

    # Apollo Research Engine Integration
    APOLLO_ENABLED: bool = os.getenv("APOLLO_ENABLED", "True").lower() in ("true", "1", "yes")
    APOLLO_PATH: str = os.getenv("APOLLO_PATH", "/Users/apple/Downloads/Apollo")
    APOLLO_MCP_URL: str = os.getenv("APOLLO_MCP_URL", "http://localhost:8080/sse")


settings = Settings()

