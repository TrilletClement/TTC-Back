from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.services.authService import AuthService
from app.core.security.jwt import create_access_token, get_current_user
from app.orm_models.db import get_db
from app.orm_models.auth import User

router = APIRouter(prefix="/api", tags=["auth"])

class LoginRequest(BaseModel):
    email: str
    password: str

@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    return AuthService.login(payload.email, payload.password, db)

@router.post("/register")
def register(payload: LoginRequest, db: Session = Depends(get_db)):
    return AuthService.register(payload.email, payload.password, db)

@router.get("/user/current")
def current_user(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return AuthService.get_user_by_email(current_user, db) 

