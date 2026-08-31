# Aurora — Technical Architecture & Comprehensive Operator Guide (v3.0)

This guide provides an in-depth engineering walkthrough of Aurora's architecture, memory systems, CRAG agent pipeline, Multi-LLM engine, and step-by-step execution manuals across all interfaces (CLI, Telegram, Android App, Docker, and Obsidian).

---

## Table of Contents
1. [Core Architectural Philosophy](#1-core-architectural-philosophy)
2. [Deep-Dive Component Mechanics](#2-deep-dive-component-mechanics)
   - [LangGraph CRAG Agent Pipeline](#a-langgraph-crag-agent-pipeline)
   - [SQLite Knowledge Graph (KG) Memory System](#b-sqlite-knowledge-graph-kg-memory-system)
   - [Hybrid GraphRAG Document Decomposition](#c-hybrid-graphrag-document-decomposition)
   - [Universal Multi-LLM Provider Engine](#d-universal-multi-llm-provider-engine)
3. [Step-by-Step Execution Manual](#3-step-by-step-execution-manual)
   - [Option A: Local Python & Conda Setup](#option-a-local-python--conda-setup)
   - [Option B: Production Docker & Docker Compose](#option-b-production-docker--docker-compose)
   - [Option C: Connecting Local Offline LLMs (llama.cpp / Ollama / LM Studio)](#option-c-connecting-local-offline-llms)
4. [Android Mobile App & APK Compilation](#4-android-mobile-app--apk-compilation)
5. [Telegram Bot Operations](#5-telegram-bot-operations)
6. [Obsidian Vault Knowledge Graph Visualization](#6-obsidian-vault-knowledge-graph-visualization)
7. [API & WebSocket Protocol Reference](#7-api--websocket-protocol-reference)
8. [Troubleshooting & FAQ](#8-troubleshooting--faq)

---

## 1. Core Architectural Philosophy

### Why Knowledge Graphs instead of Pure Vector DBs?
Standard RAG architectures store text chunks in vector databases (e.g. Pinecone, Chroma, FAISS) and retrieve the top-$k$ nearest neighbors via cosine similarity. While effective for static semantic search, flat vector retrieval suffers from two critical flaws in personalized goal tracking:
1. **Lack of Relational Reasoning**: A vector database cannot distinguish between *"I am studying Dynamic Programming"*, *"I struggle with Dynamic Programming"*, and *"I completed Dynamic Programming"*. They all produce virtually identical embeddings.
2. **Temporal & Dependency Blindness**: Vector search cannot follow structured prerequisite chains (e.g., `Recursion` $\rightarrow$ `Memoization` $\rightarrow$ `Dynamic Programming`).

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

1. **`extract_entities`**: The LLM extracts explicit goals, current topics, struggles (`WEAK_AT`, `STRUGGLING_WITH`), and achievements (`COMPLETED`) directly into SQLite.
2. **`retrieve_context`**: Traverses the personal graph from the root user node out to 2 degrees of separation, ranking nodes by recency and weight, combined with relevant document chunks.
3. **`grade_context`**: A self-reflection node that evaluates whether the retrieved brief contains sufficient context to formulate a personalized answer.
4. **`generate`**: Executes chain-of-thought generation synthesized specifically for the user's active goals and constraints.
5. **`check_groundedness`**: Verifies that the proposed solution does not hallucinate facts outside the verified context.
6. **`web_search`**: If context is missing or ungrounded, queries DuckDuckGo dynamically for up-to-date documentation and synthesizes the final response.

---

### B. SQLite Knowledge Graph (KG) Memory System (`backend/services/kg_service.py`)
The graph is persisted directly in SQLite (`aurora.db`):
- **`kg_nodes`**: Nodes representing `goal`, `topic`, `habit`, `concept`, or `person`.
- **`kg_edges`**: Directed edges representing relationships (`STUDYING`, `WEAK_AT`, `COMPLETED`, `TARGETS`, `PREREQUISITE_OF`, `PART_OF`).
- **Edge Weight Reinforcement**: Every time a user mentions or interacts with an existing concept, the edge `weight` is incremented and `last_reinforced_at` is updated.

---

### C. Hybrid GraphRAG Document Decomposition (`backend/services/document_service.py`)
When a user uploads a PDF or study guide:
1. **Text Extraction & Chunking**: `pypdf` extracts raw text and indexes chunks into SQLite FTS5 for fast sub-millisecond keyword lookup.
2. **LLM Knowledge Graph Decomposition**: The LLM analyzes the entire document structure and automatically generates:
   - Topic hierarchy and core concepts.
   - Interlinked Obsidian markdown notes with LaTeX formulas (`$$\mathcal{O}(V + E)$$`).
   - Graph nodes and edges linking prerequisite concepts to the user's Knowledge Graph.

---

### D. Universal Multi-LLM Provider Engine (`backend/services/llm_provider.py`)
Aurora is model-agnostic. The unified `BaseLLMProvider` factory handles:
- **`gemini`**: Google Gemini 3.1 Flash Lite / 1.5 Pro via `google.generativeai`.
- **`openai`**: GPT-4o, GPT-4o-mini via standard OpenAI API.
- **`anthropic`**: Claude 3.5 Sonnet / Haiku.
- **`groq`**: Ultra-fast inference with Llama 3.3 70B.
- **`local`**: Local LLMs via OpenAI-compatible endpoints (**llama.cpp server**, **Ollama**, **LM Studio**, **vLLM**).

---

## 3. Step-by-Step Execution Manual

### Option A: Local Python & Conda Setup

#### 1. Setup Environment
```bash
# Clone the repository
git clone https://github.com/Parth-Dhola/Aurora-Goal-Oriented-AI-Assistant-with-Knowledge-Graph-Memory.git
cd Aurora-Goal-Oriented-AI-Assistant-with-Knowledge-Graph-Memory

# Create conda environment
conda create -n aurora python=3.11 -y
conda activate aurora

# Install dependencies
cd backend
pip install -r requirements.txt
```

#### 2. Configure Environment (`.env`)
```bash
cp .env.example .env
```
Set your keys and credentials:
```env
LLM_PROVIDER=gemini
LLM_MODEL=gemini-3.1-flash-lite
GEMINI_API_KEY=your_gemini_key
SECRET_KEY=long-random-string-for-jwt
TELEGRAM_TOKEN=your_telegram_bot_token
AURORA_API_BASE=http://localhost:8000/api
```

#### 3. Start Backend API Server
```bash
cd backend
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```
> **Why `--host 0.0.0.0`?** Binding to `0.0.0.0` allows your Android mobile device on the same Wi-Fi network to connect to your computer at `http://<YOUR_LOCAL_IP>:8000`.

- Interactive API Docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Health Check: [http://localhost:8000/api/health](http://localhost:8000/api/health)

#### 4. Start Telegram Bot (Optional)
In a separate terminal:
```bash
cd backend
conda activate aurora
python bot.py
```

---

### Option B: Production Docker & Docker Compose

Docker runs the backend API and MLflow tracking server in production-ready isolated containers.

```bash
# Build and run containers in background
docker compose up -d --build

# View real-time logs
docker compose logs -f backend

# Stop containers
docker compose down
```

Services:
- **Backend API & Swagger**: `http://localhost:8000/docs`
- **MLflow Tracking Dashboard**: `http://localhost:5001`

---

### Option C: Connecting Local Offline LLMs (llama.cpp / Ollama / LM Studio)

To run Aurora completely offline and privately with zero cloud API dependencies:

#### 1. Start your local LLM server
- **llama.cpp**:
  ```bash
  ./llama-server -m qwen3.5-2b.gguf --port 8080 -c 4096
  ```
- **Ollama**:
  ```bash
  ollama run llama3.2
  ```

#### 2. Update `.env`
```env
LLM_PROVIDER=local
LLM_MODEL=qwen3.5-2b
LOCAL_LLM_URL=http://localhost:8080/v1
```

#### 3. Restart Backend
All CRAG agent interactions, Knowledge Graph extractions, and document note parsing will now run 100% locally on your machine.

---

## 4. Android Mobile App & APK Compilation

The mobile app is built with Kivy and features:
- **Live Status Dot**: 🟢 Connected, 🟡 Connecting, 🔴 Disconnected.
- **Theme Icon Switcher**: `◈` Aurora Glow, `☼` Warm Paper (Eye-Care), `☾` Soft Slate.
- **Dynamic Model Switcher**: Tap the header button (`⚡ LOCAL`, `🤖 GEMINI`, `🚀 GROQ`) to switch AI providers on the fly.
- **Android Storage Document Picker**: Browse `/storage/emulated/0/Download` directly with one-tap quick-jump folder buttons.
- **Dynamic Soft-Keyboard Avoidance**: Prevents the Android keyboard from obscuring your text input.

### Running Mobile App Locally on Desktop:
```bash
cd android-app
pip install kivy requests websocket-client
python main.py
```

### Building the Android APK:
1. Push your latest code to GitHub:
   ```bash
   git push origin main
   ```
2. Navigate to **[GitHub Actions](https://github.com/Parth-Dhola/Aurora-Goal-Oriented-AI-Assistant-with-Knowledge-Graph-Memory/actions)**.
3. Select **Build Android APK** $\rightarrow$ **Run workflow**.
4. Once completed, download the compiled `.apk` from the **Artifacts** section at the bottom of the run page.

---

## 5. Telegram Bot Operations

The Telegram Bot provides complete mobile access to Aurora:

| Command | Action |
|---|---|
| `/start` | Welcome message and account status |
| `/login` | Interactive secure login flow |
| `/logout` | Sign out and clear stored session |
| `/model` or `/llm` | **Interactive AI Model Switcher** (Local, Gemini, Groq, OpenAI, Claude) |
| `/ask <query>` | Query the CRAG agent with Knowledge Graph context |
| `/plan` | Generate an actionable daily plan aligned with your active goals |
| `/docs` | List all uploaded study documents and generated topic notes |
| `/goals` | List all active goals and their priorities |
| `/addgoal <name> [priority]` | Create a new explicit goal (e.g. `/addgoal Master Graphs high`) |
| `/stats` | View productivity statistics and Knowledge Graph metrics |
| `/help` | Complete command listing |

> **Direct File Ingestion**: Simply send or forward any `.pdf` or `.txt` file directly to the bot in Telegram. Aurora will automatically parse it, decompose it into topics, and connect it to your Knowledge Graph!

---

## 6. Obsidian Vault Knowledge Graph Visualization

Aurora can export your entire personal Knowledge Graph and study materials into an interactive **Obsidian Vault**:

```bash
cd scripts
python sync_to_obsidian.py
```

### Vault Structure:
- `obsidian-KG-vault/_Overview.md`: Master dashboard with Dataview tables of goals, weaknesses, and recent topics.
- `obsidian-KG-vault/Goals/`: Goal notes with target dates, status, and backlinks.
- `obsidian-KG-vault/Topics/`: Interconnected topic notes with `[[wikilinks]]`.
- `obsidian-KG-vault/Documents/`: Structured deep study notes with LaTeX formulas and algorithm summaries.

To explore the graph visually: Open Obsidian $\rightarrow$ **Open folder as vault** $\rightarrow$ select `obsidian-KG-vault/` $\rightarrow$ Open **Graph View** (`Ctrl+G` / `Cmd+G`).

---

## 7. API & WebSocket Protocol Reference

### REST Endpoints
- `POST /api/auth/register` & `POST /api/auth/login`: User management & JWT authentication.
- `POST /api/chat/`: Run queries through the CRAG agent (`{"message": "...", "debug": true}`).
- `GET /api/chat/context-preview`: View the exact raw markdown context brief constructed for the LLM.
- `GET /api/llm/`: List active LLM provider and available models.
- `POST /api/llm/switch`: Switch active LLM provider (`{"provider": "local", "model": "qwen3.5-2b"}`).
- `POST /api/documents/upload`: Multipart upload for `.pdf` and `.txt` files.
- `GET /api/kg/export/obsidian`: Export complete Obsidian Vault as a `.zip` archive.
- `GET /api/stats/`: Analytics dashboard (task completion rates, active LLM, strategy hit rates).

### Real-Time WebSocket Protocol (`/ws/chat?token=...`)
- **Client $\rightarrow$ Server**:
  ```json
  {"message": "Plan my day", "session_id": "android-session"}
  ```
- **Server $\rightarrow$ Client**:
  - `{"type": "thinking"}`: Emitted while CRAG self-reflection is running.
  - `{"type": "message", "reply": "..."}`: Emitted when the final response is synthesized.

---

## 8. Troubleshooting & FAQ

#### Q1: Android App shows "Cannot connect to server"
- Ensure your backend server was started with `--host 0.0.0.0`:
  ```bash
  uvicorn app:app --host 0.0.0.0 --port 8000 --reload
  ```
- Ensure your mobile device is connected to the same Wi-Fi network.
- In the app login screen, enter `http://<YOUR_COMPUTER_LOCAL_IP>:8000` (e.g. `192.168.0.128:8000`).

#### Q2: How do I run Aurora with zero internet connection?
1. Start llama.cpp or Ollama locally with `qwen3.5-2b` or `llama3.2`.
2. In `.env`, set:
   ```env
   LLM_PROVIDER=local
   LLM_MODEL=qwen3.5-2b
   LOCAL_LLM_URL=http://localhost:8080/v1
   ```
3. Aurora will run 100% locally with zero internet access required.

#### Q3: How do I run the automated test suite?
```bash
cd backend
pytest tests/ -v
```
All 28 unit and integration tests validate authentication, task management, goal tracking, Knowledge Graph CRUD, and document parsing.
