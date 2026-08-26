from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from services.auth_service import create_user, authenticate_user, create_token, get_current_user
from fastapi import HTTPException

router = APIRouter()

class AuthRequest(BaseModel):
    username: str
    password: str

@router.post("/register", status_code=201)
async def register(body: AuthRequest):
    user = create_user(body.username, body.password)
    token = create_token(user["id"], user["username"])
    return {"access_token": token, "token_type": "bearer", "username": user["username"]}

@router.post("/login")
async def login(body: AuthRequest):
    user = authenticate_user(body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_token(user["id"], user["username"])
    return {"access_token": token, "token_type": "bearer", "username": user["username"]}

@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    return {"id": user["id"], "username": user["username"]}
