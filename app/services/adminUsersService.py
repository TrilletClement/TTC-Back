from typing import Optional

from app.domain.exceptions import NotFoundError, BusinessError
from app.orm_models.auth import User, Role, UserRoles
from app.repositories.user_repo import UserRepository


class AdminUserService:
    def __init__(self, repo: UserRepository):
        self.repo = repo

    def list_users(self) -> list[User]:
        return self.repo.list_all()

    def toggle_user_active(self, user_id: int, active: bool, current_user: User) -> dict:
        user = self.repo.get_by_id(user_id)
        if not user:
            raise NotFoundError("User", user_id)
        if user.id == current_user.id:
            raise BusinessError("Cannot deactivate your own account")
        user.active = active
        self.repo.commit()
        return {"message": f"User {'activated' if active else 'deactivated'}", "user_id": user_id}

    def assign_role(self, user_id: int, role_id: int) -> dict:
        if not self.repo.get_by_id(user_id):
            raise NotFoundError("User", user_id)
        role = self.repo.get_role_by_id(role_id)
        if not role:
            raise NotFoundError("Role", role_id)
        if self.repo.get_user_role(user_id, role_id):
            raise BusinessError("User already has this role")
        self.repo.save(UserRoles(user_id=user_id, role_id=role_id))
        return {"message": f"Role '{role.name}' assigned to user {user_id}"}

    def remove_role(self, user_id: int, role_id: int) -> dict:
        link = self.repo.get_user_role(user_id, role_id)
        if not link:
            raise NotFoundError("UserRole", f"{user_id}/{role_id}")
        self.repo.delete(link)
        return {"message": f"Role {role_id} removed from user {user_id}"}

    def list_roles(self) -> list[Role]:
        return self.repo.list_roles()

    def create_role(self, name: str, description: Optional[str]) -> Role:
        if self.repo.get_role_by_name(name):
            raise BusinessError("Role already exists")
        role = Role(name=name, description=description)
        self.repo.save(role)
        return role

    def delete_role(self, role_id: int) -> dict:
        role = self.repo.get_role_by_id(role_id)
        if not role:
            raise NotFoundError("Role", role_id)
        if role.name == "admin":
            raise BusinessError("Cannot delete the admin role")
        self.repo.delete_role_links(role_id)
        self.repo.delete(role)
        return {"message": f"Role '{role.name}' deleted"}