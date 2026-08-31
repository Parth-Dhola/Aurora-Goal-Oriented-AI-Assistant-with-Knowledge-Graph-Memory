from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from services.llm_service import chat
from services.auth_service import verify_token
from services.session_service import touch_session
import json

router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self.active: dict[int, WebSocket] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        self.active[user_id] = websocket
        print(f"[WS] User {user_id} connected. Total: {len(self.active)}")

    def disconnect(self, user_id: int):
        self.active.pop(user_id, None)
        print(f"[WS] User {user_id} disconnected. Total: {len(self.active)}")


manager = ConnectionManager()


@router.websocket("/chat")
async def websocket_chat(websocket: WebSocket, token: str = Query(...)):
    try:
        payload = verify_token(token)
        user_id = int(payload["sub"])
        username = payload["username"]
    except Exception:
        await websocket.close(code=4001)
        return

    await manager.connect(user_id, websocket)
    await websocket.send_json({
        "type": "connected",
        "message": f"Connected as {username}. Send a message to Aurora!"
    })

    try:
        while True:
            data = await websocket.receive_json()
            user_message = data.get("message", "").strip()
            session_id = data.get("session_id", f"ws-{user_id}")
            if not user_message:
                continue
            touch_session(user_id, session_id, auto_title_from_msg=user_message)
            await websocket.send_json({"type": "thinking"})
            try:
                reply = chat(user_message, session_id, user_id=user_id)
                await websocket.send_json({"type": "message", "reply": reply, "session_id": session_id})
            except Exception as e:
                await websocket.send_json({"type": "error", "detail": str(e)})
    except WebSocketDisconnect:
        manager.disconnect(user_id)
    except Exception as e:
        manager.disconnect(user_id)
        print(f"[WS] Error for user {user_id}: {e}")
