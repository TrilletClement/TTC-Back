from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.orm_models.auth import User
from app.core.security.jwt import create_access_token, verify_password, hash_password, create_confirmation_token, verify_confirmation_token
from app.core.mail import send_confirmation_email
import uuid

class AuthService:
    @staticmethod
    def login(email: str, password: str, db: Session) -> dict:
        user = db.query(User).filter(User.email == email).first()
        if not user or not verify_password(password, user.password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Incorrect email or password",
                                headers={"WWW-Authenticate": "Bearer"})
        roles = [role.name for role in user.roles]
        access_token = create_access_token(user.email, roles=roles)
        return {"access_token": access_token, "token_type": "bearer"}

    @staticmethod
    def register(email: str, password: str, db: Session) -> dict:
        if not email or not password:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email and password are required")
        if db.query(User).filter(User.email == email).first():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
        new_user = User(email=email, password=hash_password(password), fs_uniquifier=str(uuid.uuid4()))
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return {"message": "User registered successfully", "email": email}

    @staticmethod
    def get_user_by_email(user: User, db: Session):
        return {"id": user.id, "email": user.email, "active": user.active, "roleId": [role.id for role in user.roles]}
    
    @staticmethod
    async def register(email: str, password: str, db: Session, base_url: str) -> dict:
        if not email or not password:
            raise HTTPException(status_code=400, detail="Email and password are required")
        if db.query(User).filter(User.email == email).first():
            raise HTTPException(status_code=400, detail="Email already registered")

        new_user = User(
            email=email,
            password=hash_password(password),
            fs_uniquifier=str(uuid.uuid4()),
            active=False  # ← inactif jusqu'à confirmation
        )
        db.add(new_user)
        db.commit()

        token = create_confirmation_token(email)
        confirmation_url = f"{base_url}/api/auth/confirm-email?token={token}"
        await send_confirmation_email(email, confirmation_url)

        return {"message": "Inscription réussie. Vérifiez votre email pour confirmer votre compte."}

    @staticmethod
    def confirm_email(token: str, db: Session) -> dict:
        email = verify_confirmation_token(token)
        if not email:
            raise HTTPException(status_code=400, detail="Lien de confirmation invalide ou expiré")

        user = db.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=404, detail="Utilisateur introuvable")
        if user.active:
            return {"message": "Email déjà confirmé"}

        user.active = True
        db.commit()
        return {"message": "Email confirmé avec succès. Vous pouvez maintenant vous connecter."}
