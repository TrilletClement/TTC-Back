from datetime import datetime, timedelta
import secrets
import uuid
import logging

from fastapi import HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.mail import send_confirmation_email
from app.core.security.jwt import create_access_token, hash_password, verify_password
from app.orm_models.auth import User

logger = logging.getLogger(__name__)

class AuthService:

    @staticmethod
    def login(email: str, password: str, db: Session) -> dict:
        user = db.query(User).filter(User.email == email).first()
        if not user or not verify_password(password, user.password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Incorrect email or password",
                                headers={"WWW-Authenticate": "Bearer"})
        if not user.active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="Compte non confirmé. Vérifiez votre email.")

        roles = [role.name for role in user.roles]
        access_token = create_access_token(user.email, roles=roles)
        return {"access_token": access_token, "token_type": "bearer"}

    @staticmethod
    async def register(email: str, password: str, db: Session, base_url: str, preferred_agency: str | None = None) -> dict:
        if not email or not password:
            raise HTTPException(status_code=400, detail="Email and password are required")
        
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            if existing_user.active:
                raise HTTPException(status_code=400, detail="Email already registered")
            else:
                raise HTTPException(status_code=400, detail="email-not-confirmed")

        confirmation_token = secrets.token_urlsafe(32)
        new_user = User(
            email=email,
            password=hash_password(password),
            fs_uniquifier=str(uuid.uuid4()),
            active=False,
            confirmation_token=confirmation_token,
            confirmation_token_expiry=datetime.utcnow() + timedelta(hours=24),
            preferred_agency=preferred_agency 
        )
        db.add(new_user)
        db.commit()

        confirmation_url = f"{settings.FRONTEND_URL}/confirm-email?token={confirmation_token}"
        await send_confirmation_email(email, confirmation_url)

        return {"message": "Inscription réussie. Vérifiez votre email pour confirmer votre compte."}

    @staticmethod
    def confirm_email(token: str, db: Session) -> dict:
        try:
            user = db.query(User).filter(
                User.confirmation_token == token
            ).first()

            if not user:
                raise HTTPException(status_code=400, detail="invalid-token")
            if user.active:
                raise HTTPException(status_code=400, detail="already-confirmed")
            if user.confirmation_token_expiry < datetime.utcnow():
                raise HTTPException(status_code=400, detail="token-expired")

            user.active = True
            user.confirmation_token = None
            user.confirmation_token_expiry = None
            db.commit()

            return {"status": "confirmed"}

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Erreur confirm_email: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="server-error")

    @staticmethod
    def get_user_by_email(user: User, db: Session):
        return {
            "id": user.id,
            "email": user.email,
            "active": user.active,
            "roleId": [role.id for role in user.roles],
            "roleName": [role.name for role in user.roles],
            "preferredAgency": user.preferred_agency,
        }
        
    @staticmethod
    def get_or_create_google_user(email: str, google_id: str, db: Session) -> User:
        user = db.query(User).filter(User.email == email).first()
        if user:
            if not user.google_id:
                user.google_id = google_id
                db.commit()
            return user

        user = User(
            email=email,
            password=None,
            google_id=google_id,
            fs_uniquifier=str(uuid.uuid4()),
            active=True,  # pas besoin de confirmation email
        )
        db.add(user)
        db.commit()
        return user