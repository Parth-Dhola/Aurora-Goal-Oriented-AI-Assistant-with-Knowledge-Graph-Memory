# Aurora — Technical Architecture & Operator Manual (v3.0)

This document serves as the comprehensive engineering guide and operator manual for Aurora. It details the internal mechanics of the Corrective RAG (CRAG) state graph, SQLite Knowledge Graph memory, Hybrid GraphRAG decomposition, Universal Multi-LLM provider engine, Android mobile app architecture, and automated CI/CD pipeline.

---

## Table of Contents
1. [Core Architectural Philosophy](#1-core-architectural-philosophy)
2. [Deep-Dive Component Mechanics](#2-deep-dive-component-mechanics)
   - [A. LangGraph CRAG Agent Pipeline](#a-langgraph-crag-agent-pipeline)
   - [B. SQLite Knowledge Graph (KG) Memory System](#b-sqlite-knowledge-graph-kg-memory-system)
   - [C. Hybrid GraphRAG Document Decomposition](#c-hybrid-graphrag-document-decomposition)
   - [D. Universal Multi-LLM Provider Engine](#d-universal-multi-llm-provider-engine)
3. [Step-by-Step Execution Manual](#3-step-by-step-execution-manual)
   - [Option A: Local Python & Conda Setup](#option-a-local-python--conda-setup)
   - [Option B: Production Docker & Docker Compose](#option-b-production-docker--docker-compose)
   - [Option C: Connecting Local Offline LLMs (llama.cpp / Ollama / LM Studio)](#option-c-connecting-local-offline-llms)
4. [Android Mobile App & Cross-Platform Client](#4-android-mobile-app--cross-platform-client)
5. [Telegram Bot Operations](#5-telegram-bot-operations)
6. [Obsidian Vault Knowledge Graph Visualization](#6-obsidian-vault-knowledge-graph-visualization)
7. [API & WebSocket Protocol Reference](#7-api--websocket-protocol-reference)
8. [Automated Testing & CI/CD Pipeline](#8-automated-testing--cicd-pipeline)
9. [Troubleshooting & FAQ](#9-troubleshooting--faq)

---

## 1. Core Architectural Philosophy

### Why Knowledge Graphs instead of Pure Vector DBs?
1. **Lack of Relational Reasoning**: A vector database cannot distinguish between *"I am studying Dynamic Programming"*, *"I struggle with Dynamic Programming"*, and *"I completed Dynamic Programming"*. They produce virtually identical embedding vectors.
2. **Temporal & Dependency Blindness**: Vector search cannot follow structured prerequisite chains (e.g., `Recursion` → `Memoization` → `Dynamic Programming`).

Aurora solves this by combining **Knowledge Graph Memory** (`kg_nodes` and `kg_edges` with relationship types and edge weights) with **Full-Text Document Retrieval (FTS5)**.

```
                      ┌────────────────────────────────────────┐
                      │              User Message              │
                      └───────────────────┬────────────────────┘
                                          │
                        ┌─────────────────┴─────────────────┐
                        │                                   │
                        ▼                                   ▼
        ┌───────────────────────────────┐   ┌───────────────────────────────┐
        │   Personal KG Traversal       │   │   Hybrid GraphRAG (FTS5)      │
        │ • Active Goals & Priorities   │   │ • Deep Textbook Notes         │
        │ • Prerequisites & Weak Areas  │   │ • Code Snippets & Formulas    │
        │ • Progress & Edge Strengths   │   │ • Linked [[Wikilinks]]        │
        └───────────────┬───────────────┘   └───────────────┬───────────────┘
                        │                                   │
                        └─────────────────┬─────────────────┘
                                          │
                                          ▼
                        ┌───────────────────────────────────┐
                        │ Context Builder: Markdown Brief   │
                        └─────────────────┬─────────────────┘
                                          │
                                          ▼
                        ┌───────────────────────────────────┐
                        │  LangGraph CRAG Self-Reflection   │
                        └───────────────────────────────────┘
```

---

## 2. Deep-Dive Component Mechanics

### A. LangGraph CRAG Agent Pipeline (`backend/services/crag_agent.py`)
Aurora's reasoning loop is implemented as a 7-node **Corrective RAG (CRAG)** state machine using LangGraph 0.2:

```
[extract_entities] ──► [retrieve_context] ──► [grade_context]
                                                    │
                      ┌─────────────────────────────┴─────────────────────────────┐
                      │ [is_relevant == True]                                     │ [is_relevant == False]
                      ▼                                                           ▼
                [generate]                                                  [web_search]
                      │                                                           │
                      ▼                                                           │
             [check_groundedness]                                                 │
                      │                                                           │
       ┌──────────────┴──────────────┐                                            │
  [Grounded]                    [Not Grounded]                                    │
       │                              │                                           │
       ▼                              └─────────────────► [web_search] ◄──────────┘
 [Final Actionable Response]                                     │
                                                                 ▼
                                                        [generate (with web)]
```

1. **`extract_entities`**: The LLM extracts explicit goals, topics, struggles (`WEAK_AT`, `STRUGGLING_WITH`), and achievements (`COMPLETED`) directly into SQLite.
2. **`retrieve_context`**: Traverses the personal graph from the root user node out to 2 degrees of separation, ranking nodes by recency and weight, combined with relevant document chunks.
3. **`grade_context`**: A self-reflection node that evaluates whether the retrieved brief contains sufficient context to formulate a personalized answer.
4. **`generate`**: Executes chain-of-thought generation synthesized specifically for the user's active goals and constraints.
5. **`check_groundedness`**: Verifies that the proposed solution does not hallucinate facts outside the verified context.
6. **`web_search`**: If context is missing or ungrounded, queries DuckDuckGo dynamically for up-to-date documentation and synthesizes the final response.

---

### B. SQLite Knowledge Graph (KG) Memory System (`backend/services/kg_service.py`)
The graph is persisted directly in SQLite (`aurora.db`):

- **`kg_nodes`**: `id`, `user_id`, `name`, `node_type` (`goal`, `topic`, `task`, `document`, `concept`), `properties` (JSON), `created_at`, `updated_at`.
- **`kg_edges`**: `source_id`, `target_id`, `relation_type` (`PREREQUISITE_FOR`, `PART_OF`, `STRUGGLING_WITH`, `COMPLETED`, `REFERENCES`), `weight` (0.0 to 1.0), `properties` (JSON).

#### Dynamic Weight Decay & Reinforcement:
- Every time a user mentions completing or reviewing a topic, the edge weight is reinforced: `w = min(1.0, w + 0.15)`.
- Dormant goals decay gracefully over time: `w = max(0.1, w * 0.95)` per week of inactivity.

---

### C. Hybrid GraphRAG Document Decomposition (`backend/services/document_service.py`)
When a user uploads a PDF or text file:
1. **Extraction**: `pypdf` extracts raw text and metadata.
2. **Chunking**: Text is split into overlapping chunks (1,000 characters, 150-character overlap).
3. **LLM Decomposition**: The active LLM analyzes the text and decomposes it into structured topic notes containing:
   - Topic Title & Summary
   - Key Definitions & Conceptual Explanations
   - Mathematical Formulations & Complexity Analysis (KaTeX LaTeX)
   - Code Implementations (Python/C++)
   - Prerequisite Relationships & Cross-Topic Links
4. **Graph Integration**: Each topic note is saved to the SQLite KG as a `concept` node and linked to the document node and related user goals.
5. **Full-Text Search (FTS5)**: Chunks are indexed in SQLite for high-speed keyword and BM25 retrieval.

---

### D. Universal Multi-LLM Provider Engine (`backend/services/llm_provider.py`)
Aurora features a unified provider interface supporting hot-swapping between cloud and offline models:

- **Google Gemini**: `gemini-3.1-flash-lite`, `gemini-1.5-pro` (Default cloud model)
- **Local Offline LLM**: Automatic discovery via OpenAI-compatible endpoints (`http://localhost:8080/v1/models` or Ollama `http://localhost:11434/v1/models`)
- **OpenAI**: `gpt-4o-mini`, `gpt-4o`
- **Groq**: `llama-3.3-70b-versatile` (Ultra low latency)
- **Anthropic**: `claude-3-5-sonnet-20241022`

#### Live Dynamic Filtering:
The backend queries `/api/llm/` and checks endpoint liveliness. Only configured providers (with valid API keys or active local servers) appear in the selection popup.

---

## 3. Step-by-Step Execution Manual

### Option A: Local Python & Conda Setup

#### 1. Setup Conda Environment
```bash
conda create -n aurora python=3.11 -y
conda activate aurora
pip install -r backend/requirements.txt
```

#### 2. Configure Environment (`.env`)
```env
LLM_PROVIDER=gemini
LLM_MODEL=gemini-3.1-flash-lite
GEMINI_API_KEY=your_gemini_key_here
SECRET_KEY=your_jwt_secret_key
TELEGRAM_TOKEN=your_telegram_bot_token
PORT=8000
DB_PATH=aurora.db
LOCAL_LLM_URL=http://localhost:8080/v1
LOCAL_LLM_MODEL=qwen3.5-2b
```

#### 3. Start Backend Server
```bash
cd backend
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```
> **Important**: Always specify `--host 0.0.0.0` so mobile devices on your Wi-Fi network can connect to `http://<YOUR_LOCAL_IP>:8000`.

- Swagger Docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Health Check: [http://localhost:8000/api/health](http://localhost:8000/api/health)

---

### Option B: Production Docker & Docker Compose

```bash
# Start backend API (port 8000) and MLflow UI (port 5001)
docker compose up -d --build

# Inspect logs
docker compose logs -f backend

# Stop services
docker compose down
```

---

### Option C: Connecting Local Offline LLMs

1. Start your local server:
   - **llama.cpp**: `./llama-server -m model.gguf --port 8080 -c 4096`
   - **Ollama**: `ollama run qwen3.5-2b`
   - **LM Studio**: Start Local Server on port `8080` (CORS enabled)
2. The backend automatically detects the local endpoint and adds it to the available model list.

---

## 4. Android Mobile App & Cross-Platform Client

Built with Kivy, featuring a modular architecture under `android-app/`:
- **`core/config.py`**: Auto-normalizing server URL parser (`http://` prefix injection) and session storage.
- **`core/api.py`**: REST and document upload handlers.
- **`ui/theme.py`**: Three distinct visual themes (`Aurora Glow`, `Warm Paper`, `Soft Slate`).
- **`ui/components/icon_button.py`**: Real image-backed icon buttons (`ATTACH`, `SEND`, `AURORA`, `GEMINI`, `LOGOUT`).
- **`ui/components/bubble.py`**: Chat cards with avatar icons, priority badges (`▲ Urgent`, `⚡ High`, `✦ Medium`, `• Low`), and formatted symbols.
- **`ui/screens/chat.py`**: Real-time WebSocket chat with vector OpenGL status dot (🟢 Connected, 🟡 Connecting, 🔴 Disconnected) and dynamic soft-keyboard avoidance.

### Running on Desktop (macOS / Linux / Windows):
```bash
cd android-app
python main.py
```

### Compiling Android APK:
1. Push code to GitHub.
2. In GitHub Actions, select **Build Android APK** → **Run workflow**.
3. Download the compiled `.apk` from the workflow Artifacts.

---

## 5. Telegram Bot Operations

Start the bot:
```bash
cd backend
python bot.py
```

### Available Commands:
- `/login` — Interactive username and password authentication flow
- `/ask <question>` — Send queries through the CRAG agent
- `/model` — 1-tap dynamic AI model switcher
- `/docs` — View uploaded study materials
- `/goals` — List active goals and priorities
- `/plan` — Generate a personalized daily focus schedule
- `/stats` — Productivity metrics and Knowledge Graph size
- `/logout` — Disconnect Telegram session

---

## 6. Obsidian Vault Knowledge Graph Visualization

Aurora synchronizes directly with Obsidian:
1. Open Obsidian → **Open folder as vault** → Select `obsidian-KG-vault/`.
2. Install the **Dataview** community plugin.
3. Open `_Overview.md` to see:
   - Live Goal Tracker with Progress Bars
   - Graph View with interlinked `[[Topic]]` and `[[Goal]]` notes
   - Decomposed textbook formulas, LaTeX proofs, and algorithm implementations.

To trigger a manual vault export:
```bash
curl -X POST http://localhost:8000/api/kg/export/obsidian -H "Authorization: Bearer <TOKEN>"
```

---

## 7. API & WebSocket Protocol Reference

### REST Endpoints:
| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Service health status |
| `POST` | `/api/auth/register` | Create user account |
| `POST` | `/api/auth/login` | Obtain JWT bearer token |
| `GET` | `/api/llm/` | List active model & available options |
| `POST` | `/api/llm/switch` | Hot-swap active LLM provider |
| `GET` | `/api/goals` | List personal goals |
| `POST` | `/api/goals` | Create explicit goal |
| `POST` | `/api/documents/upload` | Ingest PDF/Notes into Knowledge Graph |
| `GET` | `/api/documents/` | List uploaded documents |
| `GET` | `/api/kg/nodes` | Retrieve personal Knowledge Graph |
| `GET` | `/api/stats/` | Productivity analytics |

### WebSocket Chat Protocol:
- **Endpoint**: `ws://<HOST>:8000/ws/chat?token=<JWT_TOKEN>`
- **Client Message**: `{"message": "Plan my day", "session_id": "ws-1"}`
- **Server Events**:
  - `{"type": "connected", "message": "..."}`
  - `{"type": "thinking"}`
  - `{"type": "message", "reply": "...", "session_id": "..."}`
  - `{"type": "error", "detail": "..."}`

---

## 8. Automated Testing & CI/CD Pipeline

Aurora includes a 30-case automated test suite covering:
- Authentication & JWT security
- Goal & Task CRUD operations
- Knowledge Graph traversal & Obsidian export
- Document upload, chunking, and decomposition
- Multi-LLM provider status & dynamic switching

### Running Tests:
```bash
cd backend
pytest tests/ -v
```

### GitHub Actions CI/CD:
- **`ci-cd.yml`**: Runs on every push/PR to execute unit tests and build Docker images (<30 seconds).
- **`build-apk.yml`**: Runs only on manual `workflow_dispatch` trigger to build the Android APK.

---

## 9. Troubleshooting & FAQ

### 1. Mobile App Cannot Connect ("Connection Refused / Failed to connect")
- **Cause**: The backend server is bound to `127.0.0.1` (localhost only) or the phone is not on the same Wi-Fi network.
- **Fix**:
  1. Ensure the server is running with `uvicorn app:app --host 0.0.0.0 --port 8000`.
  2. Find your computer's local IP (`ifconfig` on macOS, `ipconfig` on Windows).
  3. In the mobile app login screen, enter `http://192.168.x.x:8000`.

### 2. Missing Icons in Kivy on Desktop
- **Cause**: Desktop SDL2 font rasterizers cannot render multi-byte color emojis.
- **Fix**: Aurora uses dedicated PNG image assets in `android-app/assets/icons/` (`IconButton`) and vector OpenGL shapes (`StatusDot`), guaranteeing 100% visibility across all platforms.

### 3. Local LLM Not Showing in Model Picker
- **Cause**: The local server (llama.cpp or Ollama) is not running on port `8080`.
- **Fix**: Start your local engine (`./llama-server --port 8080`). Aurora dynamically checks `http://localhost:8080/v1/models` and will automatically enable the option.
