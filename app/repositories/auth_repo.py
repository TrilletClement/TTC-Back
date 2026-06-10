from sqlalchemy.orm import Session
from app.orm_models.auth import User


class AuthRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_email(self, email: str) -> User | None:
        return self.db.query(User).filter(User.email == email).first()

    def get_by_reset_token(self, token: str) -> User | None:
        return self.db.query(User).filter(User.reset_token == token).first()

    def get_by_confirmation_token(self, token: str) -> User | None:
        return self.db.query(User).filter(User.confirmation_token == token).first()

    def save(self, user: User) -> User:
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def commit(self) -> None:
        self.db.commit()