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

    def get_by_oauth_handoff_token(self, token: str) -> User | None:
        return self.db.query(User).filter(User.oauth_handoff_token == token).first()

    def save(self, user: User) -> User:
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def commit(self) -> None:
        self.db.commit()

    def delete_push_data_of(self, user_id: int) -> None:
        """Phones (FCM tokens) and departure alerts: personal, nothing to keep."""
        from app.orm_models.departure_alert import DepartureAlert, PushDevice
        self.db.query(PushDevice).filter(PushDevice.user_id == user_id).delete(synchronize_session=False)
        self.db.query(DepartureAlert).filter(DepartureAlert.user_id == user_id).delete(synchronize_session=False)

    def archive_boards_of(self, user_id: int) -> None:
        # Imported here: the board model pulls in the GTFS models.
        from app.orm_models.board import Board
        self.db.query(Board).filter(Board.owner_id == user_id).update({Board.archived: True})
