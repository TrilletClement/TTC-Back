from sqlalchemy.orm import Session, selectinload
from app.orm_models.auth import User, Role, UserRoles


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_all(self) -> list[User]:
        # UserOut.roles forces Pydantic to touch .roles for every row —
        # selectinload (not joinedload: roles is many-to-many, a JOIN would
        # multiply/duplicate user rows before SQLAlchemy de-dupes them).
        return self.db.query(User).options(selectinload(User.roles)).all()

    def get_by_id(self, user_id: int) -> User | None:
        return self.db.query(User).filter(User.id == user_id).first()

    def list_roles(self) -> list[Role]:
        return self.db.query(Role).all()

    def get_role_by_id(self, role_id: int) -> Role | None:
        return self.db.query(Role).filter(Role.id == role_id).first()

    def get_role_by_name(self, name: str) -> Role | None:
        return self.db.query(Role).filter(Role.name == name).first()

    def get_user_role(self, user_id: int, role_id: int) -> UserRoles | None:
        return self.db.query(UserRoles).filter(
            UserRoles.user_id == user_id,
            UserRoles.role_id == role_id,
        ).first()

    def save(self, obj) -> None:
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)

    def delete(self, obj) -> None:
        self.db.delete(obj)
        self.db.commit()

    def delete_role_links(self, role_id: int) -> None:
        self.db.query(UserRoles).filter(UserRoles.role_id == role_id).delete()
        self.db.commit()

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()