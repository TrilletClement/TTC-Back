import secrets
import uuid
from datetime import datetime, timedelta
from typing import Optional
import logging

from app.core.config import settings
from app.core.mail import send_confirmation_email
from app.core.security.jwt import create_access_token, hash_password, verify_password
from app.domain.exceptions import NotFoundError, BusinessError, ValidationError
from app.orm_models.auth import User
from app.repositories.auth_repo import AuthRepository

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self, repo: AuthRepository):
        self.repo = repo

    def login(self, email: str, password: str) -> dict:
        user = self.repo.get_by_email(email)
        if not user or not verify_password(password, user.password):
            raise BusinessError("Incorrect email or password")
        if not user.active:
            raise BusinessError("Compte non confirmé. Vérifiez votre email.")
        roles = [role.name for role in user.roles]
        return {"access_token": create_access_token(user.email, roles=roles), "token_type": "bearer"}

    async def register(self, email: str, password: str, base_url: str, preferred_agency: str = "") -> dict:
        if not email or not password:
            raise ValidationError("Email and password are required")

        existing = self.repo.get_by_email(email)
        if existing:
            raise BusinessError("Email already registered" if existing.active else "email-not-confirmed")

        token = secrets.token_urlsafe(32)
        user  = User(
            email=email,
            password=hash_password(password),
            fs_uniquifier=str(uuid.uuid4()),
            active=False,
            confirmation_token=token,
            confirmation_token_expiry=datetime.utcnow() + timedelta(hours=24),
            preferred_agency=preferred_agency,
        )
        self.repo.save(user)
        await send_confirmation_email(email, f"{settings.FRONTEND_URL}/confirm-email?token={token}")
        return {"message": "Inscription réussie. Vérifiez votre email pour confirmer votre compte."}

    def confirm_email(self, token: str) -> dict:
        user = self.repo.get_by_confirmation_token(token)
        if not user:
            raise ValidationError("invalid-token")
        if user.active:
            raise ValidationError("already-confirmed")
        if user.confirmation_token_expiry < datetime.utcnow():
            raise ValidationError("token-expired")

        user.active = True
        user.confirmation_token = None
        user.confirmation_token_expiry = None
        self.repo.commit()
        return {"status": "confirmed"}

    def get_current_user_info(self, user: User) -> dict:
        return {
            "id":                user.id,
            "email":             user.email,
            "active":            user.active,
            "roleId":            [role.id   for role in user.roles],
            "roleName":          [role.name for role in user.roles],
            "preferredAgency":   user.preferred_agency,
            "alertDisplayPref":  user.alert_display_pref,
        }

    def update_preferences(self, user: User, preferred_agency: Optional[str],
                            alert_display_pref: Optional[str] = None) -> dict:
        user.preferred_agency = preferred_agency
        if alert_display_pref is not None and alert_display_pref not in {"off", "icon", "banner"}:
            raise ValidationError(f"Invalid alert_display_pref '{alert_display_pref}'")
        user.alert_display_pref = alert_display_pref
        self.repo.commit()
        return {"message": "Préférences mises à jour"}

    async def forgot_password(self, email: str) -> dict:
        user = self.repo.get_by_email(email)
        if user:
            token = secrets.token_urlsafe(32)
            user.reset_token        = token
            user.reset_token_expiry = datetime.utcnow() + timedelta(hours=1)
            self.repo.commit()
            try:
                from app.core.mail import send_reset_email
                await send_reset_email(user.email, f"{settings.FRONTEND_URL}/reset-password?token={token}")
                logger.info(f"Email envoyé à {user.email}")
            except Exception as e:
                logger.error(f"Erreur envoi email: {e}")
        return {"message": "Si cet email existe, un lien a été envoyé"}

    def reset_password(self, token: str, password: str) -> dict:
        user = self.repo.get_by_reset_token(token)
        if not user or user.reset_token_expiry < datetime.utcnow():
            raise ValidationError("Token invalide ou expiré")
        user.password           = hash_password(password)
        user.reset_token        = None
        user.reset_token_expiry = None
        self.repo.commit()
        return {"message": "Mot de passe mis à jour"}

    async def resend_confirmation(self, email: str) -> dict:
        user = self.repo.get_by_email(email)
        if user and not user.active:
            token = secrets.token_urlsafe(32)
            user.confirmation_token        = token
            user.confirmation_token_expiry = datetime.utcnow() + timedelta(hours=24)
            self.repo.commit()
            await send_confirmation_email(user.email, f"{settings.FRONTEND_URL}/confirm-email?token={token}")
            logger.info(f"Email renvoyé à {user.email}")
        return {"message": "Si ce compte existe, un nouvel email a été envoyé"}

    def create_oauth_handoff(self, user: User) -> str:
        token = secrets.token_urlsafe(32)
        user.oauth_handoff_token = token
        user.oauth_handoff_token_expiry = datetime.utcnow() + timedelta(minutes=2)
        self.repo.commit()
        return token

    def exchange_oauth_handoff(self, token: str) -> dict:
        user = self.repo.get_by_oauth_handoff_token(token)
        if not user or not user.oauth_handoff_token_expiry or user.oauth_handoff_token_expiry < datetime.utcnow():
            raise ValidationError("invalid-or-expired-code")
        user.oauth_handoff_token = None
        user.oauth_handoff_token_expiry = None
        self.repo.commit()
        roles = [role.name for role in user.roles]
        return {"access_token": create_access_token(user.email, roles=roles), "token_type": "bearer"}

    def get_or_create_google_user(self, email: str, google_id: str) -> User:
        user = self.repo.get_by_email(email)
        if user:
            if not user.google_id:
                user.google_id = google_id
                self.repo.commit()
            return user

        user = User(
            email=email,
            password=None,
            google_id=google_id,
            fs_uniquifier=str(uuid.uuid4()),
            active=True,
        )
        return self.repo.save(user)