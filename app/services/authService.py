from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.orm_models.auth import User
from app.core.security.jwt import create_access_token, verify_password, hash_password
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
