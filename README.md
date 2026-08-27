# Aurora — Goal-Oriented AI Assistant with Knowledge Graph Memory

[![CI/CD](https://github.com/Parth-Dhola/Aurora-Goal-Oriented-AI-Assistant-with-Knowledge-Graph-Memory/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/Parth-Dhola/Aurora-Goal-Oriented-AI-Assistant-with-Knowledge-Graph-Memory/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.11-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688)
![LangGraph](https://img.shields.io/badge/LangGraph-0.2.28-orange)
![Docker](https://img.shields.io/badge/docker-compose-2496ED)
![MLflow](https://img.shields.io/badge/mlflow-2.3-0194E2)

> A stateful GenAI agent built with LangGraph + FastAPI. Uses a SQLite Knowledge Graph to accumulate structured facts and goals from every conversation, then builds a personalised context brief that guides each Gemini response via a CRAG self-reflection pipeline.

---

## Architecture

```
User Message
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│              LangGraph StateGraph (CRAG)                │
│  ┌──────────────────────────────────────────────────┐   │
│  │  extract_entities                                │   │
│  │    └─ Gemini: extract facts/goals → update KG    │   │
│  └─────────────────────┬────────────────────────────┘   │
│                        │                                │
│  ┌─────────────────────▼────────────────────────────┐   │
│  │  retrieve_context                                │   │
│  │    └─ KG traversal → markdown context brief      │   │
│  └─────────────────────┬────────────────────────────┘   │
│                        │                                │
│  ┌─────────────────────▼────────────────────────────┐   │
│  │  grade_context  (self-reflection evaluator)      │   │
│  │    └─ Gemini: "Is context relevant?" YES / NO    │   │
│  └────────┬──────────────────────────┬──────────────┘   │
│      RELEVANT                   NOT RELEVANT            │
│           │                         │                   │
│  ┌────────▼────────┐       ┌─────────▼───────────┐      │
│  │    generate     │       │     web_search      │      │
│  │   (CoT/ReAct)   │       │    (DuckDuckGo)     │      │
│  └────────┬────────┘       └─────────┬───────────┘      │
│           │                         │                   │
│  ┌────────▼──────────────┐          │                   │
│  │  check_groundedness   │          │                   │
│  │  "Is answer grounded  │          │                   │
│  │   in context?" Y / N  │          │                   │
│  └────────┬──────────────┘          │                   │
│      NOT GROUNDED ──────────► web_search                │
└─────────────────────────────────────────────────────────┘
     │
     ▼
SQLite (aurora.db)              checkpoints.db
  kg_nodes / kg_edges      ←→   LangGraph SqliteSaver
  chat_history                   (state per session)
  llm_logs (strategy + MLflow)
```

### Knowledge Graph Memory

Every conversation turn:
1. Gemini extracts structured facts and goals from the message
2. Nodes (`topic`, `goal`, `fact`) and edges (`STRUGGLING_WITH`, `COMPLETED`, etc.) are stored in SQLite
3. Repeated mentions strengthen edge weights (recency + frequency signal)
4. Before the next Gemini call, the graph is traversed to build a personalised markdown brief

Goals from two sources feed the same KG:
- **Explicit API** (`POST /api/goals`) — urgent/high priority, full structure
- **Chat extraction** — casual mentions detected automatically, any priority

---

## Features

| Feature | Description |
|---|---|
| **CRAG Agent** | LangGraph StateGraph with 7 nodes — extract, retrieve, grade, generate, groundedness check, web search |
| **Knowledge Graph** | SQLite kg_nodes + kg_edges — accumulates facts and goals across all sessions |
| **Goal Management** | `POST /api/goals` for explicit goals; chat extraction for casual ones |
| **Persistent Memory** | LangGraph SqliteSaver checkpoints full AgentState per session ID |
| **Web Fallback** | DuckDuckGo search when KG context is insufficient (no API key needed) |
| **MLflow Tracking** | Per-run: model, prompt_version, strategy, latency, token counts, KG nodes used |
| **JWT Auth** | Secure login/register, token-based access |
| **Real-time Chat** | WebSocket — no refreshing needed |
| **Android App** | Kivy app — login screen + real-time chat |
| **CI/CD** | GitHub Actions → Docker build → DockerHub → EC2 deploy |

---

## Tech Stack

| Layer | Tech |
|---|---|
| Agent | LangGraph 0.2 StateGraph + SqliteSaver checkpointer |
| Backend | FastAPI + Uvicorn (ASGI) |
| LLM | Google Gemini 3.1 Flash Lite |
| Memory | SQLite Knowledge Graph (kg_nodes + kg_edges) |
| Web Search | DuckDuckGo (no API key) |
| Auth | JWT (PyJWT) + SHA-256 password hashing |
| MLOps | MLflow experiment tracking (strategy A/B comparison) |
| Mobile | Kivy + buildozer (Android APK) |
| DevOps | Docker + docker-compose + GitHub Actions + Nginx |
| Cloud | AWS EC2 (free tier) |

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/Parth-Dhola/Aurora-Goal-Oriented-AI-Assistant-with-Knowledge-Graph-Memory.git
cd Aurora-Goal-Oriented-AI-Assistant-with-Knowledge-Graph-Memory

# 2. Set up secrets
cp .env.example .env
# Edit .env: add GEMINI_API_KEY and SECRET_KEY

# 3. Install
cd backend
pip install -r requirements.txt

# 4. Run
uvicorn app:app --reload --port 8000

# 5. Open API docs
open http://localhost:8000/docs
```

## Docker

```bash
docker compose up --build
# Backend:  http://localhost:8000
# MLflow:   http://localhost:5001
```

---

## API Reference

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/api/health` | GET | No | Health check |
| `/api/auth/register` | POST | No | Create account |
| `/api/auth/login` | POST | No | Get JWT token |
| `/api/auth/me` | GET | Yes | Current user |
| `/api/chat/` | POST | Yes | Send message through CRAG agent |
| `/api/chat/history` | GET | Yes | Chat history |
| `/api/goals/` | GET/POST | Yes | List / create goals |
| `/api/goals/{id}` | PATCH/DELETE | Yes | Update / archive goal |
| `/api/tasks/` | GET/POST | Yes | List / create tasks |
| `/api/tasks/{id}` | PATCH/DELETE | Yes | Update / delete task |
| `/api/stats/` | GET | Yes | Dashboard — tasks, LLM strategy breakdown, KG stats |
| `/api/reminders/` | GET/POST | Yes | List / create reminders |
| `/ws/chat?token=...` | WebSocket | Token in URL | Real-time chat |
| `/docs` | GET | No | Swagger UI |

---

## Project Structure

```
aurora/
├── backend/
│   ├── app.py                      # FastAPI entry point
│   ├── models/database.py          # SQLite schema (users, tasks, chat, KG, llm_logs)
│   ├── services/
│   │   ├── crag_agent.py           # LangGraph CRAG StateGraph ← core
│   │   ├── kg_service.py           # KG entity extraction + graph CRUD
│   │   ├── context_builder.py      # KG → markdown context brief
│   │   ├── mlflow_service.py       # MLflow logging (strategy + prompt versioning)
│   │   ├── llm_service.py          # chat() — wires agent + history + logging
│   │   └── auth_service.py         # JWT auth, password hashing
│   ├── routes/
│   │   ├── auth.py                 # /api/auth/
│   │   ├── chat.py                 # /api/chat/
│   │   ├── goals.py                # /api/goals/  ← new
│   │   ├── tasks.py                # /api/tasks/
│   │   ├── stats.py                # /api/stats/
│   │   ├── reminders.py            # /api/reminders/
│   │   └── websocket.py            # /ws/chat
│   ├── Dockerfile
│   └── requirements.txt
├── android-app/
├── .github/workflows/ci-cd.yml
├── docker-compose.yml
├── nginx.conf
└── .env.example
```

---

## GitHub Actions Secrets

| Secret | Value |
|---|---|
| `DOCKERHUB_USERNAME` | Your Docker Hub username |
| `DOCKERHUB_TOKEN` | Docker Hub access token |
| `EC2_HOST` | Your EC2 public IP |
| `EC2_SSH_KEY` | Contents of your EC2 `.pem` key file |

---
