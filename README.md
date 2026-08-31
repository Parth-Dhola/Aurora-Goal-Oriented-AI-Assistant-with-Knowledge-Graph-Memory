# Aurora — Goal-Oriented AI Assistant with Knowledge Graph Memory

[![CI/CD](https://github.com/Parth-Dhola/Aurora-Goal-Oriented-AI-Assistant-with-Knowledge-Graph-Memory/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/Parth-Dhola/Aurora-Goal-Oriented-AI-Assistant-with-Knowledge-Graph-Memory/actions)
[![Build APK](https://github.com/Parth-Dhola/Aurora-Goal-Oriented-AI-Assistant-with-Knowledge-Graph-Memory/actions/workflows/build-apk.yml/badge.svg)](https://github.com/Parth-Dhola/Aurora-Goal-Oriented-AI-Assistant-with-Knowledge-Graph-Memory/actions/workflows/build-apk.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11-blue)](https://www.python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2.28-orange)](https://github.com/langchain-ai/langgraph)
[![Docker](https://img.shields.io/badge/docker-compose-2496ED)](https://www.docker.com)
[![MLflow](https://img.shields.io/badge/mlflow-2.3-0194E2)](https://mlflow.org)

> A stateful GenAI agent built with LangGraph + FastAPI. Uses a SQLite Knowledge Graph and Document Knowledge Base to accumulate structured facts, goals, and study materials, then builds a personalised context brief that guides each response via a CRAG self-reflection pipeline across **Gemini, OpenAI, Claude, Groq, or Local LLMs (Ollama)**.

---

## Architecture

```
                                ┌──────────────────────┐
                                │     User Message     │
                                └──────────┬───────────┘
                                           │
                                           ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        LangGraph Corrective RAG (CRAG) Agent                           │
│                                                                                        │
│   ┌───────────────────────┐                                                            │
│   │ 1. extract_entities   │ ──► LLM: extract facts/goals/weaknesses ──► SQLite KG      │
│   └──────────┬────────────┘                                                            │
│              │                                                                         │
│              ▼                                                                         │
│   ┌───────────────────────┐                                                            │
│   │ 2. retrieve_context   │ ◄── Traverses Personal KG & FTS5 Document Knowledge Base   │
│   └──────────┬────────────┘                                                            │
│              │                                                                         │
│              ▼                                                                         │
│   ┌───────────────────────┐                                                            │
│   │ 3. grade_context      │ ──► Self-Reflection Evaluator: "Is context relevant?"      │
│   └──────────┬────────────┘                                                            │
│              │                                                                         │
│       ┌──────┴──────────────┐                                                          │
│   [Relevant]          [Not Relevant]                                                   │
│       │                     │                                                          │
│       ▼                     ▼                                                          │
│   ┌───────────────┐     ┌───────────────────────┐                                      │
│   │ 4. generate   │     │ 6. web_search         │ ◄── DuckDuckGo Search                │
│   │  (CoT/ReAct)  │     │    (Live fallback)    │                                      │
│   └───────┬───────┘     └───────────┬───────────┘                                      │
│           │                         │                                                  │
│           ▼                         │                                                  │
│   ┌───────────────────────┐         │                                                  │
│   │ 5. check_groundedness │         │                                                  │
│   │  (Fact-check filter)  │         │                                                  │
│   └───────┬───────────────┘         │                                                  │
│           │                         │                                                  │
│   [Not Grounded] ───────────────────┘                                                  │
│           │                                                                            │
│       [Grounded]                                                                       │
│           │                                                                            │
│           ▼                                                                            │
│   ┌───────────────────────┐                                                            │
│   │ Final Actionable Plan │                                                            │
│   └───────────────────────┘                                                            │
└────────────────────────────────────────────────────────────────────────────────────────┘
                                           │
                                           ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                            Multi-Channel Interface & Storage                           │
│                                                                                        │
│  ┌───────────────────────┐   ┌───────────────────────┐   ┌──────────────────────────┐  │
│  │   Android App (Kivy)  │   │  Telegram Bot (v20+)  │   │  FastAPI REST / WS API   │  │
│  │  3 Themes + PDF Attach│   │  /docs, /plan, /goals │   │  Swagger Docs & Auth     │  │
│  └───────────────────────┘   └───────────────────────┘   └──────────────────────────┘  │
│                                                                                        │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐  │
│  │ SQLite Database (aurora.db)                                                      │  │
│  │ ├─ kg_nodes & kg_edges (Personal Knowledge Graph & Study Material)               │  │
│  │ ├─ documents & document_chunks (Hybrid GraphRAG Full-Text Search)                │  │
│  │ ├─ checkpoints.db (LangGraph Session State Checkpointer)                         │  │
│  │ └─ llm_logs (MLflow Experiment Tracking & Strategy Auditing)                     │  │
│  └──────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                        │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐  │
│  │ Interactive Obsidian Vault (obsidian-KG-vault/)                                  │  │
│  │ ├─ _Overview.md (Master Knowledge Graph & Dataview Dashboard)                    │  │
│  │ ├─ Goals/ & Topics/ (Interlinked [[wikilinks]])                                  │  │
│  │ └─ Documents/ (Deep Topic Notes with LaTeX & Complexity Formulations)            │  │
│  └──────────────────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Features

| Feature | Description |
|---|---|
| **CRAG Agent** | 7-node LangGraph StateGraph — extract, retrieve, grade, generate, check groundedness, web search |
| **Multi-LLM Engine** | Switch seamlessly between **Gemini**, **OpenAI**, **Claude**, **Groq**, or **Local LLMs (Ollama)** |
| **Hybrid GraphRAG** | Ingests PDFs & textbooks, extracts hierarchical topics, algorithms, and links them to the KG |
| **Knowledge Graph** | SQLite `kg_nodes` + `kg_edges` — accumulates structured facts, goals, and prerequisites |
| **Obsidian Vault Sync** | One-click export (`scripts/sync_to_obsidian.py`) creating an interconnected interactive graph in Obsidian |
| **Telegram Bot** | Full assistant with `/login`, `/ask`, `/goals`, `/docs`, and direct PDF/TXT file upload |
| **Modular Android App** | Kivy mobile app with **Aurora Glow**, **Warm Paper**, & **Soft Slate** themes + Storage File Picker |
| **Context Preview & Debug** | `/api/chat/context-preview` endpoint to inspect the exact context brief passed to LLM |
| **MLflow Tracking** | Real-time logging of strategy (`graph_hit`, `direct`, `web_fallback`), latency, and KG nodes used |
| **JWT Authentication** | Secure token-based access and password hashing |
| **CI/CD Automation** | GitHub Actions running 28 automated tests, multi-arch Docker builds, and cloud APK compilation |

---

## Multi-LLM Provider Engine

Aurora supports multiple LLM providers out of the box via `.env`:

```bash
# 1. Google Gemini (Default)
LLM_PROVIDER=gemini
LLM_MODEL=gemini-3.1-flash-lite
GEMINI_API_KEY=your_key

# 2. OpenAI
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=your_key

# 3. Anthropic Claude
LLM_PROVIDER=anthropic
LLM_MODEL=claude-3-5-sonnet-20241022
ANTHROPIC_API_KEY=your_key

# 4. Groq (Ultra-Fast)
LLM_PROVIDER=groq
LLM_MODEL=llama-3.3-70b-versatile
GROQ_API_KEY=your_key

# 5. Local LLM (Ollama, LM Studio, or vLLM — Offline & Private!)
LLM_PROVIDER=local
LLM_MODEL=llama3.2
LOCAL_LLM_URL=http://localhost:11434/v1
```

---

## Quick Start

### 1. Local Setup
```bash
# 1. Clone repository
git clone https://github.com/Parth-Dhola/Aurora-Goal-Oriented-AI-Assistant-with-Knowledge-Graph-Memory.git
cd Aurora-Goal-Oriented-AI-Assistant-with-Knowledge-Graph-Memory

# 2. Configure environment
cp .env.example .env
# Edit .env and add your LLM API keys and SECRET_KEY

# 3. Install dependencies
cd backend
pip install -r requirements.txt

# 4. Start backend API (--host 0.0.0.0 allows Android phone to connect over Wi-Fi)
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
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
| `/api/stats/` | GET | Yes | Dashboard — tasks, active LLM provider, strategy breakdown, KG stats |
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
- Includes **Aurora Glow**, **Warm Paper**, and **Soft Slate** themes with one-tap header switcher.
- Tap `+ DOC` to pick and upload PDFs from Android storage directly into your Knowledge Graph.
- Dynamic soft-keyboard avoidance lifts inputs smoothly above the keyboard.

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
│   │   ├── crag_agent.py           # LangGraph CRAG StateGraph core
│   │   ├── llm_provider.py         # Universal Multi-LLM provider engine (Gemini, OpenAI, Claude, Groq, Local)
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
│   ├── main.py                     # Clean app entry point
│   ├── buildozer.spec              # Android APK build spec
│   ├── core/                       # Core networking & config
│   │   ├── config.py               # Persistent config & URL normalization
│   │   └── api.py                  # API requests & document upload
│   └── ui/                         # Modular UI package
│       ├── theme.py                # Aurora Glow, Warm Paper & Soft Slate themes
│       ├── screens/
│       │   ├── login.py            # Login & server settings screen
│       │   └── chat.py             # Real-time WebSocket chat screen
│       └── components/
│           ├── bubble.py           # Stylized chat bubble with avatar badges & Markdown formatter
│           └── file_picker.py      # Android storage-aware PDF picker
├── .github/workflows/
│   ├── ci-cd.yml                   # Automated 28-test suite + Docker push
│   └── build-apk.yml               # Automated Android APK compilation workflow
├── docker-compose.yml
├── nginx.conf
└── .env.example
```
