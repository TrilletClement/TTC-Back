from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.user_access import require_admin
from app.orm_models.auth import User
from app.orm_models.db import get_db
from app.domain.exceptions import NotFoundError, BusinessError, ValidationError
from app.repositories.support_repo import SupportRepository
from app.services.adminSupportService import AdminSupportService
from app.schemas.support import TicketReply

router = APIRouter(prefix="/api/admin/support", tags=["admin-support"])


def get_service(db: Session = Depends(get_db)) -> AdminSupportService:
    return AdminSupportService(SupportRepository(db))


def _handle(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (BusinessError, ValidationError)):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


@router.get("")
@require_admin
def list_tickets(
    current_user: User,
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    archived: bool = Query(False),
    svc: AdminSupportService = Depends(get_service),
):
    try:
        return svc.list_tickets(status, search, archived)
    except (NotFoundError, BusinessError, ValidationError) as e:
        raise _handle(e)


@router.get("/{ticket_id}")
@require_admin
def get_ticket(ticket_id: int, current_user: User, svc: AdminSupportService = Depends(get_service)):
    try:
        return svc.get_ticket(ticket_id)
    except (NotFoundError, BusinessError, ValidationError) as e:
        raise _handle(e)


@router.post("/{ticket_id}/archive")
@require_admin
def archive_ticket(ticket_id: int, current_user: User, svc: AdminSupportService = Depends(get_service)):
    try:
        return svc.archive(ticket_id)
    except (NotFoundError, BusinessError, ValidationError) as e:
        raise _handle(e)


@router.post("/{ticket_id}/reply")
@require_admin
async def reply(ticket_id: int, payload: TicketReply, current_user: User, svc: AdminSupportService = Depends(get_service)):
    try:
        return await svc.reply(ticket_id, payload)
    except (NotFoundError, BusinessError, ValidationError) as e:
        raise _handle(e)
