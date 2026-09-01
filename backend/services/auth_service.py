import os
import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Optional
from dotenv import load_dotenv
import jwt
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from models.database import get_db

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "aurora-super-secret-key-32-bytes-long-for-hmac-sha256-production")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24 * 7
security = HTTPBearer()


def hash_password(password: str) -> str:
    salt = os.urandom(32).hex()
    hashed = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return f"{salt}:{hashed}"


def verify_password(plain_password: str, stored_hash: str) -> bool:
    try:
        salt, hashed = stored_hash.split(":")
        check = hashlib.sha256(f"{salt}{plain_password}".encode()).hexdigest()
        return hmac.compare_digest(check, hashed)
    except Exception:
        return False


def create_token(user_id: int, username: str) -> str:
    payload = {
        "sub": str(user_id),
        "username": username,
        "exp": datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS),
        "iat": datetime.utcnow()
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired — please login again")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def create_user(username: str, password: str) -> dict:
    db = get_db()
    existing = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if existing:
        db.close()
        raise HTTPException(status_code=400, detail="Username already taken")
    password_hash = hash_password(password)
    cursor = db.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        (username, password_hash)
    )
    db.commit()
    user_id = cursor.lastrowid
    db.close()
    return {"id": user_id, "username": username}


def authenticate_user(username: str, password: str) -> Optional[dict]:
    db = get_db()
    user = db.execute(
        "SELECT id, username, password_hash FROM users WHERE username = ?", (username,)
    ).fetchone()
    db.close()
    if not user or not verify_password(password, user["password_hash"]):
        return None
    return {"id": user["id"], "username": user["username"]}


def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)) -> dict:
    payload = verify_token(credentials.credentials)
    return {"id": int(payload["sub"]), "username": payload["username"]}
