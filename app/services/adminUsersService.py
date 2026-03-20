from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional

from app.orm_models.auth import User, Role, UserRoles


class AdminUserService:

    @staticmethod
    def list_users(db: Session) -> list[User]:
        return db.query(User).all()

    @staticmethod
    def toggle_user_active(user_id: int, active: bool, current_user: User, db: Session) -> dict:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if user.id == current_user.id:
            raise HTTPException(status_code=400, detail="Cannot deactivate your own account")
        user.active = active
        db.commit()
        return {"message": f"User {'activated' if active else 'deactivated'}", "user_id": user_id}

    @staticmethod
    def assign_role(user_id: int, role_id: int, db: Session) -> dict:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        role = db.query(Role).filter(Role.id == role_id).first()
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")

        already = db.query(UserRoles).filter(
            UserRoles.user_id == user_id,
            UserRoles.role_id == role_id
        ).first()
        if already:
            raise HTTPException(status_code=400, detail="User already has this role")

        db.add(UserRoles(user_id=user_id, role_id=role_id))
        db.commit()
        return {"message": f"Role '{role.name}' assigned to user {user_id}"}

    @staticmethod
    def remove_role(user_id: int, role_id: int, db: Session) -> dict:
        link = db.query(UserRoles).filter(
            UserRoles.user_id == user_id,
            UserRoles.role_id == role_id
        ).first()
        if not link:
            raise HTTPException(status_code=404, detail="User does not have this role")
        db.delete(link)
        db.commit()
        return {"message": f"Role {role_id} removed from user {user_id}"}

    @staticmethod
    def list_roles(db: Session) -> list[Role]:
        return db.query(Role).all()

    @staticmethod
    def create_role(name: str, description: Optional[str], db: Session) -> Role:
        existing = db.query(Role).filter(Role.name == name).first()
        if existing:
            raise HTTPException(status_code=400, detail="Role already exists")
        role = Role(name=name, description=description)
        db.add(role)
        db.commit()
        db.refresh(role)
        return role

    @staticmethod
    def delete_role(role_id: int, db: Session) -> dict:
        role = db.query(Role).filter(Role.id == role_id).first()
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")
        if role.name == "admin":
            raise HTTPException(status_code=400, detail="Cannot delete the admin role")
        db.query(UserRoles).filter(UserRoles.role_id == role_id).delete()
        db.delete(role)
        db.commit()
        return {"message": f"Role '{role.name}' deleted"}