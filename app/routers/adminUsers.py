from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional

from app.core.security.jwt import get_current_user
from app.orm_models.db import get_db
from app.orm_models.auth import User
from app.services.adminUsersService import AdminUserService

router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])


# ── Admin guard ───────────────────────────────────────────────────────────────

def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if "admin" not in [role.name for role in current_user.roles]:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


# ── Pydantic schemas ──────────────────────────────────────────────────────────

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


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/", response_model=List[UserOut])
def list_users(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return AdminUserService.list_users(db)


@router.patch("/{user_id}/active")
def toggle_user_active(
    user_id: int,
    active: bool,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return AdminUserService.toggle_user_active(user_id, active, current_user, db)


@router.post("/{user_id}/roles")
def assign_role(
    user_id: int,
    payload: AssignRoleRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return AdminUserService.assign_role(user_id, payload.role_id, db)


@router.delete("/{user_id}/roles/{role_id}")
def remove_role(
    user_id: int,
    role_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return AdminUserService.remove_role(user_id, role_id, db)


@router.get("/roles", response_model=List[RoleOut])
def list_roles(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return AdminUserService.list_roles(db)


@router.post("/roles", response_model=RoleOut)
def create_role(
    payload: RoleCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return AdminUserService.create_role(payload.name, payload.description, db)


@router.delete("/roles/{role_id}")
def delete_role(
    role_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return AdminUserService.delete_role(role_id, db)