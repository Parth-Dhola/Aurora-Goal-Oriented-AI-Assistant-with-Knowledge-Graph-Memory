# Aurora — Complete Project Guide (v3.0)

## Overview

**Aurora** is an autonomous, goal-oriented AI productivity and learning assistant designed to help students and engineers master technical topics (like DSA and System Design), organize priorities, and track progress.

Aurora consists of:
1. **FastAPI Backend with CRAG Agent**: Corrective RAG state graph with LangGraph, SQLite Knowledge Graph memory, and DuckDuckGo search fallback.
2. **Hybrid GraphRAG & Document Knowledge Base**: Ingests PDFs & textbooks, decomposes them into hierarchical topic notes with LaTeX and formulas, and interconnects them in Obsidian.
3. **Knowledge Graph (KG) & Obsidian Visualization**: Tracks entities, habits, goals, and struggles as structured graphs exportable directly into Obsidian.
4. **Telegram Bot**: Full assistant access via Telegram with secure JWT login, document upload support, and auto-completing commands.
5. **Android App (Kivy)**: Mobile app with real-time WebSocket communication, Eye-Care Warm Paper theme switcher, and in-app file uploader.
6. **MLOps & CI/CD**: MLflow run & strategy tracking, Docker containerization, and GitHub Actions workflow.

---

## Architecture & System Design

### 1. Corrective RAG (CRAG) Agent (`backend/services/crag_agent.py`)

Rather than blindly answering questions, Aurora evaluates its own retrieved context before generating a response:

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
│   │ 1. extract_entities   │ ──► Gemini: extract facts/goals/weaknesses ──► SQLite KG   │
│   └──────────┬────────────┘                                                            │
│              │                                                                         │
│              ▼                                                                         │
│   ┌───────────────────────┐                                                            │
│   │ 2. retrieve_context   │ ◄── Traverses Personal KG & FTS5 Document Knowledge Base   │
│   └──────────┬────────────┘                                                            │
│              │                                                                         │
│              ▼                                                                         │
│   ┌───────────────────────┐                                                            │
│   │ 3. grade_context      │ ──► Gemini Self-Reflection: "Is context relevant?"         │
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

1. **`extract_entities`**: Automatically detects user facts, learning weaknesses, and casual goals from conversation and persists them to the Knowledge Graph.
2. **`retrieve_context`**: Queries `kg_nodes`, `kg_edges`, and `document_chunks` to assemble a fused markdown context brief.
3. **`grade_context`**: Grades whether the retrieved context is sufficient and relevant to answer the query.
4. **`generate`**: Synthesizes an actionable response using Gemini with Chain-of-Thought reasoning.
5. **`check_groundedness`**: Validates whether the answer is factually grounded without hallucinations.
6. **`web_search`**: Falls back to DuckDuckGo search if internal memory is insufficient or outdated.

---

## Project Structure

```
aurora-final/
├── .env                              # Secrets (gitignored)
├── .env.example                      # Configuration template
├── .gitignore                        # Git exclusion rules
├── LICENSE                           # MIT License
├── README.md                         # Project documentation
├── GUIDE.md                          # Detailed architecture & setup guide
├── docker-compose.yml                # Multi-container orchestration
├── nginx.conf                        # Reverse proxy & WebSocket config
│
├── backend/                          # FastAPI Backend
│   ├── app.py                        # FastAPI entry point & router registration
│   ├── bot.py                        # Telegram Bot interface
│   ├── requirements.txt              # Python dependencies
│   ├── Dockerfile                    # Backend container definition
│   ├── models/
│   │   └── database.py               # SQLite schema (users, tasks, KG, docs, llm_logs)
│   ├── routes/
│   │   ├── auth.py                   # /api/auth (JWT registration & login)
│   │   ├── chat.py                   # /api/chat (CRAG agent REST endpoint)
│   │   ├── goals.py                  # /api/goals (Goal management & priority tracking)
│   │   ├── documents.py              # /api/documents (PDF upload & topic notes)
│   │   ├── kg.py                     # /api/kg (KG nodes, edges & Obsidian export)
│   │   ├── tasks.py                  # /api/tasks (Daily task tracking)
│   │   ├── stats.py                  # /api/stats (Analytics & strategy breakdown)
│   │   ├── reminders.py              # /api/reminders (Notifications)
│   │   └── websocket.py              # /ws/chat (Real-time bidirectional chat)
│   ├── services/
│   │   ├── crag_agent.py             # LangGraph CRAG StateGraph core
│   │   ├── llm_provider.py           # Universal Multi-LLM provider engine (Gemini, OpenAI, Claude, Groq, Local)
│   │   ├── document_service.py       # PDF parsing + Deep KG decomposition
│   │   ├── kg_service.py             # Entity extraction & SQLite KG CRUD
│   │   ├── context_builder.py        # KG + Document Knowledge → context brief
│   │   ├── mlflow_service.py         # MLOps tracking for strategy & prompts
│   │   ├── llm_service.py            # Chat orchestration & logging
│   │   └── auth_service.py           # Password hashing & JWT verification
│   └── tests/
│       └── test_api.py               # Complete test suite (28 unit/integration tests)
│
├── android-app/                      # Android Mobile App (Kivy)
│   ├── main.py                       # Clean app entry point
│   ├── buildozer.spec                # Android APK build spec
│   ├── core/                         # Core networking & config
│   │   ├── config.py                 # Persistent config & URL normalization
│   │   └── api.py                    # API requests & document upload
│   └── ui/                           # Modular UI package
│       ├── theme.py                  # Aurora Glow, Warm Paper & Soft Slate themes
│       ├── screens/
│       │   ├── login.py              # Login & server settings screen
│       │   └── chat.py               # Real-time WebSocket chat screen
│       └── components/
│           ├── bubble.py             # Stylized chat bubble with avatar badges & Markdown formatter
│           └── file_picker.py        # Android storage-aware PDF picker
│
├── scripts/                          # Automation & Utilities
│   ├── sync_to_obsidian.py           # One-click KG sync into Obsidian vault
│   └── deploy.sh                     # Production deployment script
│
└── obsidian-KG-vault/                # Generated Obsidian Vault (gitignored)
    ├── _Overview.md                  # Master KG index & Dataview queries
    ├── Goals/                        # Goal notes with wikilinks & metadata
    ├── Topics/                       # Topic notes with relationships
    └── Documents/                    # In-depth structured study notes from uploaded PDFs
```

---

## Multi-LLM Provider Engine

Aurora allows switching between multiple cloud and local LLM providers via `.env`:

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

# 4. Groq (Ultra-Fast Inference)
LLM_PROVIDER=groq
LLM_MODEL=llama-3.3-70b-versatile
GROQ_API_KEY=your_key

# 5. Local LLM (Ollama, LM Studio, or vLLM — Offline & Private!)
LLM_PROVIDER=local
LLM_MODEL=llama3.2
LOCAL_LLM_URL=http://localhost:11434/v1
```

---

## Running with Docker (Recommended for Deployment)

Docker runs the entire Aurora ecosystem in isolated, production-ready containers.

### 1. Prerequisites
- Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Mac/Windows/Linux).
- Ensure `.env` is configured in the project root with your `GEMINI_API_KEY` and `SECRET_KEY`.

### 2. Start Services with Docker Compose
From the project root:
```bash
docker compose up --build
```
To run in the background (detached mode):
```bash
docker compose up -d --build
```

### 3. Check Running Containers & Logs
```bash
# View running containers
docker compose ps

# View live backend logs
docker compose logs -f backend

# View MLflow logs
docker compose logs -f mlflow
```

### 4. Access Services
- **Backend API & Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **MLflow Tracking Dashboard**: [http://localhost:5001](http://localhost:5001)

### 5. Stop Containers
```bash
docker compose down
```

---

## Running Directly with Python Scripts (Local Development)

### 1. Environment Setup
Create and activate the conda/virtual environment:
```bash
conda create -n aurora python=3.11 -y
conda activate aurora
```

Install backend dependencies:
```bash
cd backend
pip install -r requirements.txt
```

### 2. Configure `.env`
Copy the template and fill in your keys:
```bash
cp .env.example .env
```
Key variables:
- `GEMINI_API_KEY`: From [Google AI Studio](https://aistudio.google.com/app/apikey).
- `SECRET_KEY`: Long random string for JWT signing.
- `TELEGRAM_TOKEN`: (Optional) From [@BotFather](https://t.me/BotFather).
- `AURORA_API_BASE`: `http://localhost:8000/api`
- `AURORA_USERNAME` & `AURORA_PASSWORD`: Your credentials for CLI scripts.

---

### 3. Script Execution Reference

#### A. Run Backend API Server
```bash
cd backend
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```
> **Note on `--host 0.0.0.0`**: Binding to `0.0.0.0` allows devices on your local network (e.g. an Android phone on the same Wi-Fi) to connect to `http://<YOUR_LOCAL_IP>:8000`.
- Interactive Swagger docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Health check: [http://localhost:8000/api/health](http://localhost:8000/api/health)

#### B. Run the Telegram Bot
In a separate terminal:
```bash
cd backend
conda activate aurora
python bot.py
```
- Send `/start` to your bot on Telegram.
- Log in with `/login` flow.
- Send `/docs` to see study materials or drag & drop any `.pdf` to decompose it into Knowledge Graph notes!

#### C. Run the Android App (Kivy)
```bash
cd android-app
pip install kivy requests websocket-client
python main.py
```
- Supports real-time WebSocket chat.
- Tap `🌙 Theme` / `☀️ Light` in the header to switch between **Eye-Care Warm Paper** and **Soft Slate** themes.
- Tap `📎` to pick and upload study notes directly into the Knowledge Graph.

#### D. Sync Knowledge Graph to Obsidian
```bash
conda activate aurora
python scripts/sync_to_obsidian.py
```
- Automatically exports all nodes, edges, and document study notes into `obsidian-KG-vault/`.
- Opens Obsidian and reveals your visual Knowledge Graph (`Cmd + G`).

#### E. Production Deployment Script
```bash
bash scripts/deploy.sh
```
- Pulls latest main branch, rebuilds Docker images, and cleans up orphaned containers.

#### F. Run Automated Test Suite
```bash
cd backend
pytest tests/ -v
```
- Executes all 28 unit and integration tests covering auth, tasks, goals, documents, Knowledge Graph, and stats.

---

## Continuous Integration & Deployment (CI/CD)

The GitHub Actions workflow (`.github/workflows/ci-cd.yml`) automatically:
1. **Tests**: Runs the 28-test suite on Python 3.11 with coverage metrics.
2. **Build & Push**: Builds multi-arch Docker images and pushes to Docker Hub. *(Skips gracefully if `DOCKERHUB_USERNAME` secret is not configured)*.
3. **Deploy**: SSH deploys to your EC2 server. *(Skips gracefully if `EC2_HOST` secret is not configured)*.
