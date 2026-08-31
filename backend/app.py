from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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
from routes.sessions  import router as sessions_router
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="Aurora AI Assistant",
    description="""
Personal AI assistant with goal-aware Knowledge Graph memory powered by LangGraph + Gemini.

## How to use the docs
1. **Register** → `POST /api/auth/register` with any username + password
2. **Copy** the `access_token` from the response
3. **Click** the 🔒 Authorize button → enter `Bearer <your_token>`
4. All protected endpoints now work!

## Set a goal explicitly
`POST /api/goals` with `{"label": "Lose Weight", "priority": "high", "target": "10kg", "deadline": "December 2026"}`

## Or just chat — Aurora extracts goals automatically
`POST /api/chat/` → `{"message": "I really want to improve my typing speed"}`

## WebSocket (real-time chat)
`ws://localhost:8000/ws/chat?token=YOUR_TOKEN`
    """,
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router,      prefix="/api/auth",      tags=["Auth"])
app.include_router(chat_router,      prefix="/api/chat",      tags=["Chat"])
app.include_router(goals_router,     prefix="/api/goals",     tags=["Goals"])
app.include_router(tasks_router,     prefix="/api/tasks",     tags=["Tasks"])
app.include_router(stats_router,     prefix="/api/stats",     tags=["Stats"])
app.include_router(reminders_router, prefix="/api/reminders", tags=["Reminders"])
app.include_router(kg_router,        prefix="/api/kg",        tags=["Knowledge Graph"])
app.include_router(documents_router, prefix="/api/documents", tags=["Documents & Hybrid RAG"])
app.include_router(llm_router,       prefix="/api/llm",       tags=["LLM Provider"])
app.include_router(sessions_router,  prefix="/api/sessions",  tags=["Sessions"])
app.include_router(ws_router,        prefix="/ws",            tags=["WebSocket"])


@app.on_event("startup")
async def startup():
    print("[Aurora] Starting up...")
    init_db()
    print("[Aurora] Ready!")
    print("[Aurora] Docs → http://localhost:8000/docs")


@app.get("/api/health", tags=["Health"])
async def health():
    return {"status": "ok", "app": "Aurora", "version": "3.0.0"}
