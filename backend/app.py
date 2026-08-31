"""
app.py — Main FastAPI Application Entrypoint for Aurora AI Assistant
"""
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from models.database import init_db
from routes.auth      import router as auth_router
from routes.chat      import router as chat_router
from routes.tasks     import router as tasks_router
from routes.stats     import router as stats_router
from routes.reminders import router as reminders_router
from routes.websocket import router as ws_router
from routes.goals     import router as goals_router
from routes.kg        import router as kg_router
from routes.documents import router as documents_router
from routes.llm       import router as llm_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Production lifespan event handler replacing deprecated @app.on_event."""
    print(f"[{settings.APP_NAME}] Initializing database tables and Knowledge Graph...")
    init_db()
    print(f"[{settings.APP_NAME}] System initialized successfully!")
    print(f"[{settings.APP_NAME}] API Docs: http://localhost:{settings.PORT}/docs")
    yield
    print(f"[{settings.APP_NAME}] Graceful shutdown complete.")


app = FastAPI(
    title=settings.APP_NAME,
    description="""
Personal AI assistant with goal-aware Knowledge Graph memory powered by LangGraph + Gemini.

## Features & APIs
- **Auth**: Register and authenticate with JWT bearer tokens (`/api/auth`)
- **Chat**: Corrective RAG (CRAG) cyclical reasoning agent (`/api/chat`, `/ws/chat`)
- **Knowledge Graph**: Node and edge relationships with Obsidian sync (`/api/kg`)
- **Documents**: Deep Hybrid GraphRAG decomposition for PDFs and notes (`/api/documents`)
- **Multi-LLM**: Dynamic runtime AI brain switcher (`/api/llm`)
- **Goals & Tasks**: Personal goal hierarchy and task progress tracking (`/api/goals`, `/api/tasks`)
    """,
    version=settings.VERSION,
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Production performance middleware: tracks request latency and adds X-Process-Time header."""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = f"{process_time:.4f}s"
    return response


# Include modular route controllers
app.include_router(auth_router,      prefix="/api/auth",      tags=["Auth"])
app.include_router(chat_router,      prefix="/api/chat",      tags=["Chat"])
app.include_router(goals_router,     prefix="/api/goals",     tags=["Goals"])
app.include_router(tasks_router,     prefix="/api/tasks",     tags=["Tasks"])
app.include_router(stats_router,     prefix="/api/stats",     tags=["Stats"])
app.include_router(reminders_router, prefix="/api/reminders", tags=["Reminders"])
app.include_router(kg_router,        prefix="/api/kg",        tags=["Knowledge Graph"])
app.include_router(documents_router, prefix="/api/documents", tags=["Documents & Hybrid RAG"])
app.include_router(llm_router,       prefix="/api/llm",       tags=["LLM Provider"])
app.include_router(ws_router,        prefix="/ws",            tags=["WebSocket"])


@app.get("/api/health", tags=["Health"])
async def health():
    """Health check endpoint for Docker container orchestration and load balancers."""
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "active_provider": settings.DEFAULT_PROVIDER
    }
