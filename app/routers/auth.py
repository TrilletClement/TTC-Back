import secrets
from fastapi.responses import RedirectResponse
import httpx
from fastapi import Request
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.services.authService import AuthService
from app.core.security.jwt import create_access_token, get_current_user
from app.orm_models.db import get_db
from app.orm_models.auth import User
from app.core.mail import send_confirmation_email, send_reset_email
from app.core.config import settings
from app.core.security.jwt import hash_password

import urllib.parse
import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["auth"])

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

class RegisterRequest(BaseModel):
    email: str
    password: str
    turnstileToken: str
    preferred_agency: str

class LoginRequest(BaseModel):
    email: str
    password: str

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    password: str
    
class ResendConfirmRequest(BaseModel):
    email: str
class PreferencesUpdate(BaseModel):
    preferred_agency: str | None = None

@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    return AuthService.login(payload.email, payload.password, db)

@router.post("/token")
def token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    return AuthService.login(form_data.username, form_data.password, db)

@router.post("/register")
async def register(
    payload: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    remote_ip = request.client.host if request.client else None
    is_human = await verify_turnstile(payload.turnstileToken, remote_ip)
    if not is_human:
        raise HTTPException(status_code=400, detail="Validation CAPTCHA échouée")

    base_url = str(request.base_url).rstrip("/")
    return await AuthService.register(payload.email, payload.password, db, base_url) 

@router.get("/confirm-email")
def confirm_email(token: str, db: Session = Depends(get_db)):
    return AuthService.confirm_email(token, db)

@router.get("/user/current")
def current_user(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)):
    return AuthService.get_user_by_email(current_user, db)

@router.patch("/user/preferences")
def update_preferences(
    payload: PreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_user.preferred_agency = payload.preferred_agency
    db.commit()
    return {"message": "Préférences mises à jour"}

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
    user.password = hash_password(payload.password)
    user.reset_token = None
    user.reset_token_expiry = None
    db.commit()
    return {"message": "Mot de passe mis à jour"}

async def verify_turnstile(token: str, remote_ip: str = None) -> bool:
    async with httpx.AsyncClient() as client:
        data = {
            "secret": settings.TURNSTILE_SECRET_KEY,
            "response": token,
        }
        if remote_ip:
            data["remoteip"] = remote_ip

        response = await client.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data=data
        )
        result = response.json()
        return result.get("success", False)
    
    
@router.post("/resend-confirmation")
async def resend_confirmation(payload: ResendConfirmRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    
    logger.info(f"Resend confirmation pour: {payload.email}")
    logger.info(f"User trouvé: {user is not None}")
    if user:
        logger.info(f"User active: {user.active}")
    
    if user and not user.active:
        token = secrets.token_urlsafe(32)
        user.confirmation_token = token
        user.confirmation_token_expiry = datetime.utcnow() + timedelta(hours=24)
        db.commit()
        confirmation_url = f"{settings.FRONTEND_URL}/confirm-email?token={token}"
        await send_confirmation_email(user.email, confirmation_url)
        logger.info(f"Email renvoyé à {user.email}")
    
    return {"message": "Si ce compte existe, un nouvel email a été envoyé"}

@router.get("/auth/google")
def google_login():
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
    }
    url = f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url)

@router.get("/auth/google/callback")
async def google_callback(code: str, db: Session = Depends(get_db)):
    async with httpx.AsyncClient() as client:
        # Échange code → tokens
        token_resp = await client.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        })
        token_data = token_resp.json()
        if "error" in token_data:
            raise HTTPException(status_code=400, detail="Échec OAuth Google")

        # Récupération du profil
        userinfo_resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {token_data['access_token']}"}
        )
        userinfo = userinfo_resp.json()

    email = userinfo.get("email")
    google_id = userinfo.get("sub")

    if not email:
        raise HTTPException(status_code=400, detail="Email non fourni par Google")

    user = AuthService.get_or_create_google_user(email, google_id, db)
    roles = [role.name for role in user.roles]
    jwt = create_access_token(user.email, roles=roles)

    frontend_url = f"{settings.FRONTEND_URL}/auth/callback?token={jwt}"
    return RedirectResponse(frontend_url)


