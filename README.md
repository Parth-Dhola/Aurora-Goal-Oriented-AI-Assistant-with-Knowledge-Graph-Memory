# Aurora — Goal-Oriented AI Assistant with Knowledge Graph Memory

[![CI/CD](https://github.com/Parth-Dhola/Aurora-Goal-Oriented-AI-Assistant-with-Knowledge-Graph-Memory/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/Parth-Dhola/Aurora-Goal-Oriented-AI-Assistant-with-Knowledge-Graph-Memory/actions)
[![Android APK](https://img.shields.io/badge/Android%20APK-Ready%20(Buildozer)-success.svg)](https://github.com/Parth-Dhola/Aurora-Goal-Oriented-AI-Assistant-with-Knowledge-Graph-Memory/actions/workflows/build-apk.yml)
[![Tests](https://img.shields.io/badge/tests-33%20passed-brightgreen.svg)](https://github.com/Parth-Dhola/Aurora-Goal-Oriented-AI-Assistant-with-Knowledge-Graph-Memory/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11-blue)](https://www.python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2.28-orange)](https://github.com/langchain-ai/langgraph)
[![Docker](https://img.shields.io/badge/docker-compose-2496ED)](https://www.docker.com)
[![MLflow](https://img.shields.io/badge/mlflow-2.3-0194E2)](https://mlflow.org)

> A stateful GenAI assistant built with LangGraph + FastAPI. Uses a SQLite Knowledge Graph and Document Knowledge Base to accumulate structured facts, goals, and study materials, then builds a personalised context brief that guides each response via a CRAG self-reflection pipeline across **Gemini, Local LLMs (llama.cpp/Ollama), OpenAI, Claude, and Groq**.

---

## Architecture Overview

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
│   │ 4. generate   │     │ 6. Apollo Research    │ ◄── Multi-Source Research (arXiv,    │
│   │  (CoT/ReAct)  │     │    Engine (MCP)       │     Semantic Scholar, GitHub, DDG)   │
│   └───────┬───────┘     └───────────┬───────────┘     + FlashRank Anti-Poisoning       │
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
│  │  3 Themes + PDF Upload│   │  /paper, /docs, /plan │   │  Swagger Docs & Auth     │  │
│  │  OpenGL Status Dot    │   │  /model 1-Tap Switch  │   │  Multi-LLM Switcher      │  │
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
| **CRAG Agent** | 7-node LangGraph StateGraph — extract, retrieve, grade, generate, check groundedness, Apollo research |
| **Apollo Research (MCP)** | Anti-poisoned multi-source research engine querying **arXiv**, **Semantic Scholar**, **GitHub**, and **DuckDuckGo** with **FlashRank CPU reranking** ([Apollo Repo](https://github.com/Parth-Dhola/Apollo-AntiPoison-Research-MCP)) |
| **Multi-LLM Engine** | Dynamic runtime switching between **Gemini**, **Local LLMs (llama.cpp/Ollama)**, **OpenAI**, **Claude**, and **Groq** |
| **Hybrid GraphRAG** | Ingests PDFs & textbooks, extracts hierarchical topics, algorithms, and links them to the KG |
| **Obsidian Vault Sync** | Bi-directional Markdown export of your Knowledge Graph with live `[[wikilinks]]` and Dataview tables |
| **Modular Android App** | Kivy mobile/desktop app with real PNG icon assets, OpenGL vector status dot, soft keyboard avoidance, and 3 themes |
| **Telegram Bot** | Full conversational interface with `/paper` research query, 1-tap `/model` switcher, file ingestion, and goal tracking |
| **CI/CD & Pytest** | 33 automated test cases with manual 1-click APK build workflow |

---

## Quickstart

### Prerequisites
- Python 3.11
- Anaconda or Miniconda
- (Optional) Docker & Docker Compose
- (Optional) Ollama, LM Studio, or llama.cpp for local offline AI

---

### Option A: Local Python & Conda Setup

```bash
# 1. Clone repository
git clone https://github.com/Parth-Dhola/Aurora-Goal-Oriented-AI-Assistant-with-Knowledge-Graph-Memory.git
cd Aurora-Goal-Oriented-AI-Assistant-with-Knowledge-Graph-Memory

# 2. Create and activate conda environment
conda create -n aurora python=3.11 -y
conda activate aurora

# 3. Install dependencies
pip install -r backend/requirements.txt

# 4. Configure environment variables
cp .env.example .env
# Open .env and insert your GEMINI_API_KEY, SECRET_KEY, and TELEGRAM_TOKEN

# 5. Start the FastAPI backend server (bound to 0.0.0.0 for LAN & mobile access)
cd backend
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

Once running:
- **API Docs (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check**: [http://localhost:8000/api/health](http://localhost:8000/api/health)

---

### Option B: Run with Docker Compose

```bash
# Start backend (port 8000) and MLflow tracking server (port 5001)
docker compose up -d

# View logs
docker compose logs -f backend
```

---

### Running the Android / Desktop Client

You can run and test the app immediately on your desktop:

```bash
cd android-app
python main.py
```

- When connecting from your **phone on Wi-Fi**, set the Server URL to your computer's local IP: `http://192.168.x.x:8000`.

---

### Running the Telegram Bot

```bash
cd backend
python bot.py
```

Available commands in Telegram:
- `/login` — Authenticate your Aurora account
- `/ask <message>` — Chat with your personal Knowledge Graph
- `/model` — 1-tap dynamic AI brain switching
- `/docs` — List uploaded study documents
- `/goals` — View your current goals & priorities
- `/plan` — Plan your day based on your active goals
- `/logout` — Disconnect session

---

## Multi-LLM Provider Configuration

Aurora supports hot-swapping AI models on the fly via the API, Telegram Bot, or Android App:

| Provider | Setting in `.env` | Model Name | Description |
|---|---|---|---|
| **Google Gemini (Default)** | `LLM_PROVIDER=gemini` | `gemini-3.1-flash-lite` | Ultra-fast cloud inference |
| **Local Offline LLM** | `LLM_PROVIDER=local` | `qwen3.5-2b` / `llama3.2` | 100% offline via llama.cpp, Ollama, or LM Studio |
| **Groq** | `LLM_PROVIDER=groq` | `llama-3.3-70b-versatile` | Ultra low-latency cloud inference |
| **OpenAI** | `LLM_PROVIDER=openai` | `gpt-4o-mini` | OpenAI cloud API |
| **Anthropic** | `LLM_PROVIDER=anthropic` | `claude-3-5-sonnet-20241022`| Deep reasoning Claude model |

### Using Local Models (Ollama / llama.cpp / LM Studio)
1. Start your local server on port `8080` (or `11434` for Ollama).
2. Set in `.env`:
   ```env
   LOCAL_LLM_URL=http://localhost:8080/v1
   LOCAL_LLM_MODEL=qwen3.5-2b
   ```
3. Aurora automatically discovers available models from `/v1/models` and enables dynamic switching!

---

## Project Structure

```
.
├── backend/
│   ├── app.py                      # FastAPI app entry point & route definitions
│   ├── bot.py                      # Telegram Bot with /model switcher
│   ├── config.py                   # Global settings and environment loader
│   ├── models/
│   │   ├── database.py             # SQLite connection & table schemas
│   │   └── schemas.py              # Pydantic validation models
│   ├── routes/
│   │   ├── auth.py                 # JWT authentication (register/login)
│   │   ├── chat.py                 # REST chat endpoint
│   │   ├── websocket.py            # Real-time WebSocket chat
│   │   ├── documents.py            # Document upload & chunk management
│   │   ├── goals.py                # Goal creation, updates & archiving
│   │   ├── tasks.py                # Task management
│   │   ├── kg.py                   # Knowledge Graph nodes & Obsidian sync
│   │   ├── llm.py                  # Dynamic Multi-LLM status & switcher
│   │   └── stats.py                # Productivity metrics
│   ├── services/
│   │   ├── crag_agent.py           # 7-node LangGraph Corrective RAG state machine
│   │   ├── llm_provider.py         # Multi-LLM provider abstraction & hot-swapping
│   │   ├── document_service.py     # PDF text extraction & topic decomposition
│   │   ├── graph_rag.py            # Hybrid graph traversal + FTS5 search
│   │   └── obsidian_sync.py        # Markdown vault exporter
│   └── tests/
│       └── test_api.py             # 30 automated integration & unit test cases
├── android-app/
│   ├── main.py                     # App entry point
│   ├── buildozer.spec              # Buildozer APK configuration
│   ├── core/                       # App config & API client
│   ├── ui/                         # Themes, screens (login, chat), and components
│   └── assets/icons/               # High-res visual PNG icon assets
├── obsidian-KG-vault/              # Synchronized Knowledge Graph vault
├── docker-compose.yml              # Multi-container orchestration (Backend + MLflow)
├── GUIDE.md                        # In-depth operator and engineering guide
└── README.md                       # Project overview
```

---

## Testing & Verification

Run the automated test suite:

```bash
cd backend
pytest tests/ -v
```

Output:
```
======================== 30 passed in 0.47s ========================
```

---

## License

Distributed under the MIT License. See `LICENSE` for more information.
