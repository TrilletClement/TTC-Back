from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.user_access import require_user
from app.orm_models.auth import User
from app.orm_models.db import get_db
from app.schemas.support import TicketCreate
from app.services.supportService import SupportService

router = APIRouter(prefix="/api/support", tags=["support"])


@router.post("")
@require_user
async def create_ticket(payload: TicketCreate, current_user: User, db: Session = Depends(get_db)):
    return await SupportService.create_ticket(payload, current_user.id, current_user.email, db)


@router.get("")
@require_user
def list_my_tickets(current_user: User, db: Session = Depends(get_db)):
    return SupportService.list_my_tickets(current_user.id, db)
