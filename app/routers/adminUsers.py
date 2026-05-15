from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional

from app.core.user_access import require_admin
from app.orm_models.auth import User
from app.orm_models.db import get_db
from app.services.adminUsersService import AdminUserService

router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])


class RoleOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class UserOut(BaseModel):
    id: int
    email: str
    active: bool
    roles: List[RoleOut] = []

    class Config:
        from_attributes = True


class RoleCreate(BaseModel):
    name: str
    description: Optional[str] = None


class AssignRoleRequest(BaseModel):
    role_id: int


@router.get("/", response_model=List[UserOut])
@require_admin
def list_users(db: Session = Depends(get_db)):
    return AdminUserService.list_users(db)


@router.patch("/{user_id}/active")
@require_admin
def toggle_user_active(
    user_id: int,
    active: bool,
    current_user: User,
    db: Session = Depends(get_db),
):
    return AdminUserService.toggle_user_active(user_id, active, current_user, db)


@router.post("/{user_id}/roles")
@require_admin
def assign_role(
    user_id: int,
    payload: AssignRoleRequest,
    db: Session = Depends(get_db),
):
    return AdminUserService.assign_role(user_id, payload.role_id, db)


@router.delete("/{user_id}/roles/{role_id}")
@require_admin
def remove_role(user_id: int, role_id: int, db: Session = Depends(get_db)):
    return AdminUserService.remove_role(user_id, role_id, db)


@router.get("/roles", response_model=List[RoleOut])
@require_admin
def list_roles(db: Session = Depends(get_db)):
    return AdminUserService.list_roles(db)


@router.post("/roles", response_model=RoleOut)
@require_admin
def create_role(payload: RoleCreate, db: Session = Depends(get_db)):
    return AdminUserService.create_role(payload.name, payload.description, db)


@router.delete("/roles/{role_id}")
@require_admin
def delete_role(role_id: int, db: Session = Depends(get_db)):
    return AdminUserService.delete_role(role_id, db)
