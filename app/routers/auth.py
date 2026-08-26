import urllib.parse
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.security.jwt import create_access_token, get_current_user
from app.domain.exceptions import BusinessError, ValidationError
from app.orm_models.auth import User
from app.orm_models.db import get_db
from app.repositories.auth_repo import AuthRepository
from app.schemas.auth import (ForgotPasswordRequest, LoginRequest,
                               PreferencesUpdate, RegisterRequest,
                               ResendConfirmRequest, ResetPasswordRequest)
from app.services.authService import AuthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["auth"])

GOOGLE_AUTH_URL     = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL    = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


def get_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(AuthRepository(db))


def _handle(exc: BusinessError | ValidationError) -> HTTPException:
    if isinstance(exc, ValidationError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


async def verify_turnstile(token: str, remote_ip: str = None) -> bool:
    async with httpx.AsyncClient() as client:
        data = {"secret": settings.TURNSTILE_SECRET_KEY, "response": token}
        if remote_ip:
            data["remoteip"] = remote_ip
        response = await client.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify", data=data
        )
        return response.json().get("success", False)


@router.post("/login")
@limiter.limit("10/minute")
def login(request: Request, payload: LoginRequest, svc: AuthService = Depends(get_service)):
    try:
        return svc.login(payload.email, payload.password)
    except BusinessError as e:
        raise HTTPException(status_code=401, detail=str(e), headers={"WWW-Authenticate": "Bearer"})


@router.post("/token")
@limiter.limit("10/minute")
def token(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), svc: AuthService = Depends(get_service)):
    try:
        return svc.login(form_data.username, form_data.password)
    except BusinessError as e:
        raise HTTPException(status_code=401, detail=str(e), headers={"WWW-Authenticate": "Bearer"})


@router.post("/register")
@limiter.limit("5/minute")
async def register(payload: RegisterRequest, request: Request, svc: AuthService = Depends(get_service)):
    if not await verify_turnstile(payload.turnstileToken, request.client.host if request.client else None):
        raise HTTPException(status_code=400, detail="Validation CAPTCHA échouée")
    try:
        return await svc.register(payload.email, payload.password, str(request.base_url).rstrip("/"), payload.preferred_agency)
    except (BusinessError, ValidationError) as e:
        raise _handle(e)


@router.get("/confirm-email")
def confirm_email(token: str, svc: AuthService = Depends(get_service)):
    try:
        return svc.confirm_email(token)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/user/current")
def current_user(current_user: User = Depends(get_current_user), svc: AuthService = Depends(get_service)):
    return svc.get_current_user_info(current_user)


@router.patch("/user/preferences")
def update_preferences(
    payload: PreferencesUpdate,
    current_user: User = Depends(get_current_user),
    svc: AuthService = Depends(get_service),
):
    try:
        return svc.update_preferences(current_user, payload.preferred_agency, payload.alert_display_pref)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/forgot-password")
@limiter.limit("5/minute")
async def forgot_password(request: Request, payload: ForgotPasswordRequest, svc: AuthService = Depends(get_service)):
    return await svc.forgot_password(payload.email)


@router.post("/reset-password")
@limiter.limit("10/minute")
def reset_password(request: Request, payload: ResetPasswordRequest, svc: AuthService = Depends(get_service)):
    try:
        return svc.reset_password(payload.token, payload.password)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/resend-confirmation")
@limiter.limit("5/minute")
async def resend_confirmation(request: Request, payload: ResendConfirmRequest, svc: AuthService = Depends(get_service)):
    return await svc.resend_confirmation(payload.email)


@router.get("/auth/google")
def google_login():
    params = {
        "client_id":     settings.GOOGLE_CLIENT_ID,
        "redirect_uri":  settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope":         "openid email profile",
        "access_type":   "offline",
    }
    return RedirectResponse(f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}")


@router.get("/auth/google/callback")
async def google_callback(code: str, svc: AuthService = Depends(get_service)):
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(GOOGLE_TOKEN_URL, data={
            "code":          code,
            "client_id":     settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri":  settings.GOOGLE_REDIRECT_URI,
            "grant_type":    "authorization_code",
        })
        token_data = token_resp.json()
        if "error" in token_data:
            raise HTTPException(status_code=400, detail="Échec OAuth Google")

        userinfo = (await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        )).json()

    email     = userinfo.get("email")
    google_id = userinfo.get("sub")
    if not email:
        raise HTTPException(status_code=400, detail="Email non fourni par Google")

    user  = svc.get_or_create_google_user(email, google_id)
    roles = [role.name for role in user.roles]
    jwt   = create_access_token(user.email, roles=roles)
    return RedirectResponse(f"{settings.FRONTEND_URL}/auth/callback?token={jwt}")