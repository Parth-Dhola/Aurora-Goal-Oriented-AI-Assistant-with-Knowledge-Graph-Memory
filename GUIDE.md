# Aurora — Complete Project Guide

## What Aurora Is

Aurora is a cross-platform AI productivity assistant. It has three parts:
- **Backend** — a FastAPI server that handles all logic
- **Telegram bot** — Aurora on Telegram (from v1)
- **Android app** — a Kivy app that talks to the backend via WebSocket

---

## Part 1 — Project Structure

```
aurora-final/
├── backend/
│   ├── app.py                    ← FastAPI entry point. Wires everything together.
│   ├── models/
│   │   └── database.py           ← SQLite setup. Creates all tables on startup.
│   ├── services/
│   │   ├── auth_service.py       ← JWT auth logic. Passwords, tokens, user lookup.
│   │   └── llm_service.py        ← Gemini API. Sends messages, saves history.
│   ├── routes/
│   │   ├── auth.py               ← /api/auth/register, /login, /me
│   │   ├── chat.py               ← /api/chat/ (protected, uses LLM)
│   │   ├── tasks.py              ← /api/tasks/ CRUD
│   │   ├── stats.py              ← /api/stats/ dashboard data
│   │   ├── reminders.py          ← /api/reminders/ CRUD
│   │   └── websocket.py          ← /ws/chat (real-time WebSocket)
│   └── requirements.txt
├── android-app/
│   ├── main.py                   ← Kivy Android app. Login + real-time chat.
│   └── buildozer.spec            ← APK build configuration.
├── .env.example                  ← Template for secrets.
└── GUIDE.md                      ← This file.
```

---

## Part 2 — How Each Technology Works

### FastAPI (replaces Flask)

Flask is synchronous — it handles one request at a time. FastAPI is asynchronous — it can handle thousands of requests simultaneously. This matters for WebSockets.

```python
# Flask style (old)
@app.route("/api/chat/", methods=["POST"])
def send_message():
    data = request.get_json()      # manual JSON parsing
    return jsonify({"reply": ...}) # manual JSON response

# FastAPI style (new)
class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"

@router.post("/")
async def send_message(body: ChatRequest):  # Pydantic validates automatically
    return {"reply": ...}                   # dict auto-converted to JSON
```

**Key differences:**
- `async def` instead of `def` — enables concurrent handling
- `BaseModel` (Pydantic) replaces `request.get_json()` — validates automatically
- Returns dict directly — no `jsonify()` needed
- Auto-generates `/docs` (Swagger UI) — interactive API testing for free

### JWT Authentication

JWT (JSON Web Token) is a way to prove who you are without sending your password every time.

**How it works:**
1. You send username + password to `/api/auth/login`
2. Server checks the password, creates a signed token (a long string)
3. You store that token in your app
4. Every future request includes the token in the header: `Authorization: Bearer <token>`
5. Server verifies the token is valid (not expired, not tampered with)

**What a JWT token contains:**
```
xxxxx.yyyyy.zzzzz
  │      │      │
header  payload  signature
         │
    { user_id, username, expires_at }
```

Anyone can read the payload (it's base64 encoded). But only the server can verify it's genuine, using the SECRET_KEY. This means you never send your password again after login.

**In the code:**
```python
# Creating a token (after successful login)
def create_token(user_id: int, username: str) -> str:
    payload = {
        "sub": str(user_id),      # "sub" = subject, standard JWT field
        "username": username,
        "exp": datetime.utcnow() + timedelta(hours=168),  # 7 days
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

# Verifying a token (on every protected request)
def verify_token(token: str) -> dict:
    payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    return payload  # contains user_id and username
```

**Protecting an endpoint:**
```python
@router.get("/api/stats/")
async def get_stats(user: dict = Depends(get_current_user)):
    # If token is missing or invalid, FastAPI auto-returns 401
    # If valid, user = {"id": 1, "username": "parth"}
    return {...}
```

The `Depends(get_current_user)` is a FastAPI dependency. It runs `get_current_user` automatically before your function. If authentication fails, your function never runs.

### WebSockets (real-time, no refreshing)

HTTP is like sending a letter — you send a request, wait for a response, connection closes. To get new data, you send another letter. This is why chat apps without WebSockets feel slow.

WebSocket is like a phone call — connection stays open. Either side can speak at any time. This is why messages appear instantly.

**HTTP flow (old):**
```
User types message → POST /api/chat/ → wait 2 seconds → response arrives → display
To check for new messages: poll every 2 seconds (wasteful)
```

**WebSocket flow (new):**
```
User connects once → connection stays open
User sends message → server receives instantly → Aurora replies → client receives instantly
No polling. No refreshing. Feels like WhatsApp.
```

**How WebSocket authentication works:**
Regular HTTP sends the token in a header. WebSockets don't have headers after the initial connection. So we pass the token as a URL parameter:
```
ws://localhost:8000/ws/chat?token=YOUR_JWT_TOKEN
```

The server reads it from the URL, verifies it, and either accepts or rejects the connection.

**The message loop:**
```python
@router.websocket("/chat")
async def websocket_chat(websocket: WebSocket, token: str = Query(...)):
    # 1. Verify token
    payload = verify_token(token)
    
    # 2. Accept connection
    await websocket.accept()
    
    # 3. Keep listening forever
    while True:
        data = await websocket.receive_json()    # waits for user message
        await websocket.send_json({"type": "thinking"})  # instant feedback
        reply = chat(data["message"])            # call Gemini (1-3 seconds)
        await websocket.send_json({"type": "message", "reply": reply})
```

**Message types the server sends:**
- `{"type": "connected"}` — sent once on connect, welcome message
- `{"type": "thinking"}` — sent immediately when message received, before Gemini replies
- `{"type": "message", "reply": "..."}` — Aurora's actual reply
- `{"type": "error", "detail": "..."}` — if something goes wrong

### Kivy (Python Android app)

Kivy lets you write Python that runs on Android. You define UI elements as Python objects. No XML, no Java, no Kotlin needed.

**Key concepts:**

**Screens and ScreenManager** — like pages in an app. `ScreenManager` handles switching between them.
```python
sm = ScreenManager()
sm.add_widget(LoginScreen(name="login"))
sm.add_widget(ChatScreen(name="chat"))
# Switch: sm.current = "chat"
```

**Layouts** — how widgets are arranged:
- `BoxLayout(orientation="vertical")` — stacks widgets top to bottom
- `BoxLayout(orientation="horizontal")` — places widgets side by side
- `ScrollView` — makes content scrollable

**Clock.schedule_once** — WebSocket runs in a background thread. Kivy UI can only be updated from the main thread. `Clock.schedule_once` safely bridges this:
```python
# WRONG — calling UI from background thread crashes
def _ws_message(self, ws, raw):
    self.add_bubble("Aurora says...")  # crashes

# RIGHT — schedule UI update on main thread
def _ws_message(self, ws, raw):
    Clock.schedule_once(lambda dt: self.add_bubble("Aurora says..."), 0)
```

**Threading** — API calls take time. If you run them on the main thread, the UI freezes. Running in a background thread keeps the app responsive:
```python
threading.Thread(target=self._auth, args=("/auth/login",), daemon=True).start()
# daemon=True means the thread dies when the app closes
```

### Password Hashing

Never store plain text passwords. If your database is stolen, attackers get everything.

**How hashing works:**
```python
def hash_password(password: str) -> str:
    salt = os.urandom(32).hex()          # random 64-char string
    hashed = sha256(salt + password)     # irreversible transformation
    return f"{salt}:{hashed}"           # store both
```

A salt is random data added before hashing. Two users with the same password get different hashes. This prevents "rainbow table" attacks (precomputed hash databases).

**Verifying:**
```python
def verify_password(plain, stored):
    salt, hashed = stored.split(":")
    check = sha256(salt + plain)         # rehash with same salt
    return check == hashed               # compare
```

---

## Part 3 — Run Steps

### Step 1 — Backend setup

```bash
cd aurora-final/backend
conda activate aurora
pip install -r requirements.txt
```

### Step 2 — Create .env

```bash
cp ../.env.example .env
```

Open `.env` and set:
- `GEMINI_API_KEY` — from aistudio.google.com/app/apikey
- `SECRET_KEY` — any long random string, e.g. `mysecretkey123changethis`

### Step 3 — Run the backend

```bash
uvicorn app:app --reload --port 8000
```

You should see:
```
[Aurora DB] All tables ready.
[Aurora] Ready!
[Aurora] Docs → http://localhost:8000/docs
```

### Step 4 — Test in browser (easiest)

Open `http://localhost:8000/docs`

1. Click `POST /api/auth/register` → Try it out → enter username + password → Execute
2. Copy the `access_token` from the response
3. Click the 🔒 **Authorize** button at the top of the page
4. Enter: `Bearer <paste your token here>` → Authorize
5. Now try `POST /api/chat/` → enter `{"message": "plan my day"}` → Execute
6. Aurora replies in the response!

### Step 5 — Test WebSocket in browser console

Get your token first, then open Chrome DevTools (F12) → Console:

```javascript
const token = "paste_your_token_here"
const ws = new WebSocket(`ws://localhost:8000/ws/chat?token=${token}`)
ws.onmessage = (e) => console.log(JSON.parse(e.data))
ws.send(JSON.stringify({"message": "plan my day", "session_id": "test"}))
```

Watch the console — you'll see `{"type":"thinking"}` appear immediately, then `{"type":"message","reply":"..."}` a second later. That's real-time WebSocket working.

### Step 6 — Run Android app locally (Mac)

Keep backend running. Open a new terminal:

```bash
cd aurora-final/android-app
pip install kivy requests websocket-client
python main.py
```

A window opens. Register an account. Chat screen appears. Messages go in real-time via WebSocket.

### Step 7 — Run on real Android device

Your Mac and Android phone must be on the same WiFi.

**Find your Mac's IP:**
System Settings → WiFi → Details → IP Address (e.g. `192.168.1.17`)

**Edit `android-app/main.py`:**
```python
API_BASE = "http://192.168.1.17:8000/api"   # your Mac IP
WS_BASE  = "ws://192.168.1.17:8000/ws"
```

**Restart backend to accept connections from the network:**
```bash
uvicorn app:app --reload --port 8000 --host 0.0.0.0
```

`--host 0.0.0.0` means "accept from any device", not just localhost.

Run the Kivy app on your Mac to test. It should connect to the backend over your WiFi.

### Step 8 — Build Android APK

This builds a real `.apk` file you can install on any Android phone.

```bash
# Install buildozer (APK builder)
pip install buildozer

# First time only — installs Android SDK/NDK (~2GB, takes 20-30 min)
cd aurora-final/android-app
buildozer android debug
```

APK will appear at:
```
aurora-final/android-app/bin/aurora-1.0-debug.apk
```

Transfer to your Android phone (via USB or Google Drive) → install → open Aurora.

**Enable unknown sources on Android:**
Settings → Security → Install unknown apps → allow your file manager

---

## Part 4 — Resume Impact

After this project you can say:

> "Built a cross-platform AI productivity assistant — FastAPI backend with JWT authentication, WebSocket real-time chat, Gemini LLM integration with MLflow experiment tracking, Telegram bot with 7 commands, Android app built in Python (Kivy), fully Dockerised with GitHub Actions CI/CD deploying to AWS EC2."

**Skills this adds to your resume:**
- FastAPI, Uvicorn, ASGI
- JWT authentication
- WebSockets
- Pydantic data validation
- Android development (Kivy, buildozer)
- SQLite, Docker, GitHub Actions (from v1)
- Gemini API, MLflow (from v1)

---

## Part 5 — Common Errors and Fixes

| Error | Cause | Fix |
|---|---|---|
| `pkg_resources not found` | MLflow + conda conflict | `pip install setuptools==69.5.1 --force-reinstall --no-deps` |
| `Port 8000 already in use` | Another process | `lsof -i :8000` then kill it, or use different port |
| `Connection refused` on Android | Wrong IP or backend not running | Check IP, run with `--host 0.0.0.0` |
| `401 Unauthorized` | Token expired or missing | Login again to get fresh token |
| `422 Unprocessable Entity` | Missing required field | Check request body has all required fields |
| WebSocket `4001` close code | Invalid JWT token | Re-login and use fresh token in WS URL |
| Kivy window black | Missing display drivers | Normal on some Macs, app still works |
