# Aurora — Goal-Oriented AI Assistant with Knowledge Graph Memory

[![CI/CD](https://github.com/Parth-Dhola/Aurora-Goal-Oriented-AI-Assistant-with-Knowledge-Graph-Memory/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/Parth-Dhola/Aurora-Goal-Oriented-AI-Assistant-with-Knowledge-Graph-Memory/actions)
[![Build APK](https://github.com/Parth-Dhola/Aurora-Goal-Oriented-AI-Assistant-with-Knowledge-Graph-Memory/actions/workflows/build-apk.yml/badge.svg)](https://github.com/Parth-Dhola/Aurora-Goal-Oriented-AI-Assistant-with-Knowledge-Graph-Memory/actions/workflows/build-apk.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11-blue)](https://www.python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2.28-orange)](https://github.com/langchain-ai/langgraph)
[![Docker](https://img.shields.io/badge/docker-compose-2496ED)](https://www.docker.com)
[![MLflow](https://img.shields.io/badge/mlflow-2.3-0194E2)](https://mlflow.org)

> A stateful GenAI agent built with LangGraph + FastAPI. Uses a SQLite Knowledge Graph and Document Knowledge Base to accumulate structured facts, goals, and study materials, then builds a personalised context brief that guides each Gemini response via a CRAG self-reflection pipeline.

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
│  │  retrieve_context (Hybrid GraphRAG)              │   │
│  │    └─ KG traversal + Document chunks → brief     │   │
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
  documents / chunks             (state per session)
  llm_logs (strategy + MLflow)
```

### Knowledge Graph & Document Memory
Every conversation turn and document upload:
1. **Entity Extraction**: Gemini extracts structured facts, habits, and goals from user messages.
2. **Hybrid GraphRAG**: PDFs/textbooks are decomposed into deep topic notes with LaTeX formulas and `[[wikilinks]]` in Obsidian, with concepts linked into `kg_nodes` and `kg_edges`.
3. **Graph Traversal**: Before generating a response, the graph is traversed to construct an enriched, personalized markdown context brief.

---

## Features

| Feature | Description |
|---|---|
| **CRAG Agent** | 7-node LangGraph StateGraph — extract, retrieve, grade, generate, check groundedness, web search |
| **Hybrid GraphRAG** | Ingests PDFs & textbooks, extracts hierarchical topics, algorithms, and links them to the KG |
| **Knowledge Graph** | SQLite `kg_nodes` + `kg_edges` — accumulates structured facts, goals, and prerequisites |
| **Obsidian Vault Sync** | One-click export (`scripts/sync_to_obsidian.py`) creating an interconnected interactive graph in Obsidian |
| **Telegram Bot** | Full assistant with `/login`, `/ask`, `/goals`, `/docs`, and direct PDF/TXT file upload |
| **Android App** | Kivy mobile app with **Eye-Care Warm Paper** light & dark themes, WebSockets, and in-app file uploader |
| **Context Preview & Debug** | `/api/chat/context-preview` endpoint to inspect the exact context brief passed to Gemini |
| **MLflow Tracking** | Real-time logging of strategy (`graph_hit`, `direct`, `web_fallback`), latency, and KG nodes used |
| **JWT Authentication** | Secure token-based access and password hashing |
| **CI/CD Automation** | GitHub Actions running 28 automated tests, multi-arch Docker builds, and cloud APK compilation |

---

## Tech Stack

| Layer | Tech |
|---|---|
| Agent | LangGraph 0.2 StateGraph + SqliteSaver checkpointer |
| Backend | FastAPI + Uvicorn (ASGI) |
| LLM | Google Gemini 3.1 Flash Lite |
| Memory | SQLite Knowledge Graph (`kg_nodes` + `kg_edges`) + FTS5 Document Chunks |
| Web Search | DuckDuckGo (no API key required) |
| Auth | JWT (PyJWT) + SHA-256 password hashing |
| MLOps | MLflow experiment tracking (strategy benchmarking) |
| Mobile | Kivy (Android APK with Eye-Care theme) |
| DevOps | Docker + Docker Compose + GitHub Actions + Nginx |

---

## Quick Start

### 1. Local Setup
```bash
# 1. Clone repository
git clone https://github.com/Parth-Dhola/Aurora-Goal-Oriented-AI-Assistant-with-Knowledge-Graph-Memory.git
cd Aurora-Goal-Oriented-AI-Assistant-with-Knowledge-Graph-Memory

# 2. Configure environment
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY and SECRET_KEY

# 3. Install dependencies
cd backend
pip install -r requirements.txt

# 4. Start backend API
uvicorn app:app --reload --port 8000
```
- Interactive API Docs: [http://localhost:8000/docs](http://localhost:8000/docs)

### 2. Docker & Docker Compose
```bash
docker compose up -d --build
# Backend API:  http://localhost:8000
# MLflow UI:    http://localhost:5001
```

---

## API Reference

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/api/health` | GET | No | Health check |
| `/api/auth/register` | POST | No | Create user account |
| `/api/auth/login` | POST | No | Obtain JWT token |
| `/api/auth/me` | GET | Yes | Get current authenticated user |
| `/api/chat/` | POST | Yes | Send message through CRAG agent (`debug: true` supported) |
| `/api/chat/context-preview` | GET | Yes | Inspect the exact KG + Document context brief passed to LLM |
| `/api/chat/history` | GET | Yes | View chat history |
| `/api/goals/` | GET/POST | Yes | List / create explicit goals |
| `/api/goals/{id}` | PATCH/DELETE | Yes | Update / archive goal |
| `/api/documents/upload` | POST | Yes | Upload PDF / notes → auto-generate topic notes & KG |
| `/api/documents/` | GET | Yes | List uploaded study documents |
| `/api/documents/{id}` | GET/DELETE | Yes | View document topic notes / delete document |
| `/api/kg/nodes` | GET | Yes | Knowledge Graph nodes (JSON) |
| `/api/kg/edges` | GET | Yes | Knowledge Graph edges & relations (JSON) |
| `/api/kg/export/obsidian` | GET | Yes | Download Obsidian Vault (.zip) |
| `/api/tasks/` | GET/POST | Yes | List / create tasks |
| `/api/tasks/{id}` | PATCH/DELETE | Yes | Update / delete task |
| `/api/stats/` | GET | Yes | Dashboard — tasks, LLM strategy breakdown, KG stats |
| `/api/reminders/` | GET/POST | Yes | List / create reminders |
| `/ws/chat?token=...` | WebSocket | Token in URL | Real-time bidirectional chat |
| `/docs` | GET | No | Swagger UI documentation |

---

## Android Mobile App & APK Build

### Running Locally
```bash
cd android-app
pip install kivy requests websocket-client
python main.py
```
- Includes **Eye-Care Warm Paper** light & dark themes with one-tap header switcher.
- Tap `📎` to pick and upload PDFs directly into your Knowledge Graph.

### Building APK
1. Push code to GitHub.
2. In the **Actions** tab, trigger the **Build Android APK** workflow.
3. Download the compiled `.apk` directly from **Artifacts** at the bottom of the completed run.

---

## Project Structure

```
aurora/
├── backend/
│   ├── app.py                      # FastAPI entry point
│   ├── bot.py                      # Telegram bot interface
│   ├── models/database.py          # SQLite schema (users, tasks, chat, KG, docs, llm_logs)
│   ├── services/
│   │   ├── crag_agent.py           # LangGraph CRAG StateGraph ← core
│   │   ├── document_service.py     # PDF parsing + Deep KG decomposition
│   │   ├── kg_service.py           # KG entity extraction + graph CRUD
│   │   ├── context_builder.py      # KG + Document Knowledge → markdown context brief
│   │   ├── mlflow_service.py       # MLflow logging (strategy + prompt versioning)
│   │   ├── llm_service.py          # chat() — wires agent + history + logging
│   │   └── auth_service.py         # JWT auth, password hashing
│   ├── routes/
│   │   ├── auth.py                 # /api/auth/
│   │   ├── chat.py                 # /api/chat/ & context-preview
│   │   ├── goals.py                # /api/goals/
│   │   ├── documents.py            # /api/documents/ (PDF upload & notes)
│   │   ├── kg.py                   # /api/kg/ (Obsidian export)
│   │   ├── tasks.py                # /api/tasks/
│   │   ├── stats.py                # /api/stats/
│   │   ├── reminders.py            # /api/reminders/
│   │   └── websocket.py            # /ws/chat
│   ├── Dockerfile
│   └── requirements.txt
├── android-app/
│   ├── main.py                     # Kivy UI + Eye-Care themes + file uploader
│   └── buildozer.spec              # Android APK spec
├── .github/workflows/
│   ├── ci-cd.yml                   # Automated 28-test suite + Docker push
│   └── build-apk.yml               # Automated Android APK compilation workflow
├── docker-compose.yml
├── nginx.conf
└── .env.example
```
