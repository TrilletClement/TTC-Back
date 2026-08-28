from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.user_access import require_admin
from app.domain.exceptions import NotFoundError, BusinessError
from app.orm_models.auth import User
from app.orm_models.db import get_db
from app.repositories.user_repo import UserRepository
from app.schemas.user import AssignRoleRequest, RoleCreate, RoleOut, UserOut
from app.services.adminUsersService import AdminUserService

router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])


def get_service(db: Session = Depends(get_db)) -> AdminUserService:
    return AdminUserService(UserRepository(db))


def _handle(exc: NotFoundError | BusinessError) -> HTTPException:
    return HTTPException(
        status_code=404 if isinstance(exc, NotFoundError) else 400,
        detail=str(exc),
    )


@router.get("/", response_model=list[UserOut])
@require_admin
def list_users(svc: AdminUserService = Depends(get_service)):
    return svc.list_users()


@router.patch("/{user_id}/active")
@require_admin
def toggle_user_active(
    user_id: int,
    active: bool,
    current_user: User,
    svc: AdminUserService = Depends(get_service),
):
    try:
        return svc.toggle_user_active(user_id, active, current_user)
    except (NotFoundError, BusinessError) as e:
        raise _handle(e)


@router.post("/{user_id}/roles")
@require_admin
def assign_role(
    user_id: int,
    payload: AssignRoleRequest,
    current_user: User,
    svc: AdminUserService = Depends(get_service),
):
    try:
        return svc.assign_role(user_id, payload.role_id, current_user)
    except (NotFoundError, BusinessError) as e:
        raise _handle(e)


@router.delete("/{user_id}/roles/{role_id}")
@require_admin
def remove_role(user_id: int, role_id: int, current_user: User, svc: AdminUserService = Depends(get_service)):
    try:
        return svc.remove_role(user_id, role_id, current_user)
    except (NotFoundError, BusinessError) as e:
        raise _handle(e)


@router.get("/roles", response_model=list[RoleOut])
@require_admin
def list_roles(svc: AdminUserService = Depends(get_service)):
    return svc.list_roles()


@router.post("/roles", response_model=RoleOut)
@require_admin
def create_role(payload: RoleCreate, current_user: User, svc: AdminUserService = Depends(get_service)):
    try:
        return svc.create_role(payload.name, payload.description, current_user)
    except (NotFoundError, BusinessError) as e:
        raise _handle(e)


@router.delete("/roles/{role_id}")
@require_admin
def delete_role(role_id: int, current_user: User, svc: AdminUserService = Depends(get_service)):
    try:
        return svc.delete_role(role_id, current_user)
    except (NotFoundError, BusinessError) as e:
        raise _handle(e)