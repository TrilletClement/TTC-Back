from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import secrets
from app.services.authService import AuthService
from app.core.security.jwt import create_access_token, get_current_user
from app.orm_models.db import get_db
from app.orm_models.auth import User
from app.core.mail import send_reset_email
from app.core.config import settings

import logging
import os
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["auth"])

class LoginRequest(BaseModel):
    email: str
    password: str

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    password: str

@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    return AuthService.login(payload.email, payload.password, db)

@router.post("/token")
def token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    return AuthService.login(form_data.username, form_data.password, db)

@router.post("/register")
def register(payload: LoginRequest, db: Session = Depends(get_db)):
    return AuthService.register(payload.email, payload.password, db)

@router.get("/user/current")
def current_user(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)):
    return AuthService.get_user_by_email(current_user, db)

import logging
logger = logging.getLogger(__name__)

@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if user:
        token = secrets.token_urlsafe(32)
        user.reset_token = token
        user.reset_token_expiry = datetime.utcnow() + timedelta(hours=1)
        db.commit()

        reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
        
        try:
            await send_reset_email(user.email, reset_url)
            logger.info(f"Email envoyé à {user.email}")
        except Exception as e:
            logger.error(f"Erreur envoi email: {e}")

    return {"message": "Si cet email existe, un lien a été envoyé"}

@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.reset_token == payload.token).first()
    
    if not user or user.reset_token_expiry < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Token invalide ou expiré")
    user.password = AuthService.hash_password(payload.password)
    user.reset_token = None
    user.reset_token_expiry = None
    db.commit()
    return {"message": "Mot de passe mis à jour"}