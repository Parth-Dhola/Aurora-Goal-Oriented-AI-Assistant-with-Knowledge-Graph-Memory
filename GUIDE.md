# Aurora — Complete Project Guide (v3.0)

## Overview

**Aurora** is an autonomous, goal-oriented AI productivity and learning assistant designed to help students and engineers master technical topics (like DSA and System Design), organize priorities, and track progress.

Aurora consists of:
1. **FastAPI Backend with CRAG Agent**: Corrective RAG state graph with LangGraph, SQLite Knowledge Graph memory, and DuckDuckGo search fallback.
2. **Knowledge Graph (KG) & Obsidian Visualization**: Tracks entities, habits, goals, and struggles as structured graphs exportable directly into Obsidian.
3. **Telegram Bot**: Full assistant access via Telegram with secure JWT login and auto-completing commands.
4. **Android App (Kivy)**: Mobile app with real-time WebSocket communication and quick suggestion chips.
5. **MLOps & CI/CD**: MLflow run & strategy tracking, Docker containerization, and GitHub Actions workflow.

---

## Architecture & System Design

### 1. Corrective RAG (CRAG) Agent (`backend/services/crag_agent.py`)

Rather than blindly answering questions, Aurora evaluates its own retrieved context before generating a response:

```
User Message
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│              LangGraph StateGraph (CRAG)                │
│  ┌──────────────────────────────────────────────────┐   │
│  │  extract_entities                                │   │
│  │    └─ Gemini: extract facts/goals → update KG   │   │
│  └─────────────────────┬────────────────────────────┘   │
│                        │                                │
│  ┌─────────────────────▼────────────────────────────┐   │
│  │  retrieve_context                                │   │
│  │    └─ KG traversal → markdown context brief     │   │
│  └─────────────────────┬────────────────────────────┘   │
│                        │                                │
│  ┌─────────────────────▼────────────────────────────┐   │
│  │  grade_context  (self-reflection evaluator)      │   │
│  │    └─ Gemini: "Is context relevant?" YES / NO   │   │
│  └────────┬──────────────────────────┬──────────────┘   │
│      RELEVANT                   NOT RELEVANT            │
│           │                         │                   │
│  ┌────────▼────────┐       ┌─────────▼───────────┐      │
│  │    generate     │       │     web_search       │      │
│  │   (CoT/ReAct)   │       │    (DuckDuckGo)      │      │
│  └────────┬────────┘       └─────────┬───────────┘      │
│           │                         │                   │
│  ┌────────▼──────────────┐          │                   │
│  │  check_groundedness   │          │                   │
│  │  "Is answer grounded  │          │                   │
│  │   in context?" Y / N  │          │                   │
│  └────────┬──────────────┘          │                   │
│      NOT GROUNDED ──────────► web_search                │
└─────────────────────────────────────────────────────────┘
```

1. **`extract_entities`**: Automatically detects user facts, learning weaknesses, and casual goals from conversation and persists them to the Knowledge Graph.
2. **`retrieve_context`**: Queries `kg_nodes` and `kg_edges` to assemble a prioritized markdown context brief.
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
│   │   └── database.py               # SQLite schema (users, tasks, KG, chats, logs)
│   ├── routes/
│   │   ├── auth.py                   # /api/auth (JWT registration & login)
│   │   ├── chat.py                   # /api/chat (CRAG agent REST endpoint)
│   │   ├── goals.py                  # /api/goals (Goal management & priority tracking)
│   │   ├── kg.py                     # /api/kg (KG nodes, edges & Obsidian export)
│   │   ├── tasks.py                  # /api/tasks (Daily task tracking)
│   │   ├── stats.py                  # /api/stats (Analytics & strategy breakdown)
│   │   ├── reminders.py              # /api/reminders (Notifications)
│   │   └── websocket.py              # /ws/chat (Real-time bidirectional chat)
│   ├── services/
│   │   ├── crag_agent.py             # LangGraph CRAG StateGraph core
│   │   ├── kg_service.py             # Entity extraction & SQLite KG CRUD
│   │   ├── context_builder.py        # KG graph traversal → context brief
│   │   ├── mlflow_service.py         # MLOps tracking for strategy & prompts
│   │   ├── llm_service.py            # Chat orchestration & logging
│   │   └── auth_service.py           # Password hashing & JWT verification
│   └── tests/
│       └── test_api.py               # Complete test suite (23 unit/integration tests)
│
├── android-app/                      # Android Mobile App (Kivy)
│   ├── main.py                       # App UI, WebSockets & suggestion chips
│   └── buildozer.spec                # Android APK build spec
│
├── scripts/                          # Automation & Utilities
│   ├── sync_to_obsidian.py           # One-click KG sync into Obsidian vault
│   └── deploy.sh                     # Production deployment script
│
└── obsidian-KG-vault/                # Generated Obsidian Vault (gitignored)
    ├── _Overview.md                  # Master KG index & Dataview queries
    ├── Goals/                        # Goal notes with wikilinks & metadata
    └── Topics/                       # Topic notes with relationships
```

---

## Setup & Running Guide

### 1. Environment Setup

Create a conda environment or Python virtual environment:
```bash
conda create -n aurora python=3.11 -y
conda activate aurora
```

Install backend dependencies:
```bash
cd backend
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Create `.env` in the root folder (or copy from `.env.example`):
```bash
cp .env.example .env
```

Fill in your secrets:
- `GEMINI_API_KEY`: Get from [Google AI Studio](https://aistudio.google.com/app/apikey).
- `SECRET_KEY`: Random 32+ character string.
- `TELEGRAM_TOKEN`: (Optional) From [@BotFather](https://t.me/BotFather) on Telegram.
- `AURORA_API_BASE`: `http://localhost:8000/api`
- `AURORA_USERNAME` & `AURORA_PASSWORD`: Your credentials for local scripts.

### 3. Run the Backend API

```bash
cd backend
uvicorn app:app --reload --port 8000
```
- Swagger Documentation: [http://localhost:8000/docs](http://localhost:8000/docs)
- Health Check: [http://localhost:8000/api/health](http://localhost:8000/api/health)

### 4. Run the Telegram Bot

In a separate terminal:
```bash
cd backend
conda activate aurora
python bot.py
```
Send `/start` to your bot on Telegram and log in using `/login <username> <password>`.

### 5. Visualize the Knowledge Graph in Obsidian

1. Ensure the backend server is running.
2. Run the sync script:
   ```bash
   conda activate aurora
   python scripts/sync_to_obsidian.py
   ```
3. The script exports all nodes/edges as Markdown with YAML frontmatter into `obsidian-KG-vault/`.
4. Open `obsidian-KG-vault` as a vault in Obsidian.
5. Press **`Cmd + G`** (or `Ctrl + G`) to view the interactive Knowledge Graph.

### 6. Run the Android App (Locally or on Device)

```bash
cd android-app
pip install kivy requests websocket-client
python main.py
```

### 7. Run Test Suite

```bash
cd backend
pytest tests/ -v
```
All 23 unit & integration tests validate authentication, tasks, goals, Knowledge Graph endpoints, reminders, and stats without making external network calls.

---

## Docker & Production Deployment

### Run with Docker Compose
```bash
docker compose up --build
```
- Backend runs on `http://localhost:8000`
- MLflow dashboard runs on `http://localhost:5001`

### Continuous Integration (CI/CD)
The `.github/workflows/ci-cd.yml` workflow automatically:
1. Runs the test suite on Python 3.11.
2. Builds and tags multi-architecture Docker images.
3. Pushes images to Docker Hub (`${{ secrets.DOCKERHUB_USERNAME }}/aurora-backend:latest`).
4. (Optional) Deploys to EC2 if `EC2_HOST` and `EC2_SSH_KEY` secrets are configured.
