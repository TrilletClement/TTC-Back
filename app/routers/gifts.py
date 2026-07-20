from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.user_access import require_user
from app.orm_models.auth import User
from app.orm_models.db import get_db
from app.domain.exceptions import ValidationError
from app.repositories.order_repo import OrderRepository
from app.services.giftService import GiftService

router = APIRouter(prefix="/api/gifts", tags=["gifts"])


def get_service(db: Session = Depends(get_db)) -> GiftService:
    return GiftService(OrderRepository(db))


def _handle(exc: Exception) -> HTTPException:
    if isinstance(exc, ValidationError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


@router.get("/{token}")
def get_claim_info(token: str, svc: GiftService = Depends(get_service)):
    try:
        return svc.get_claim_info(token)
    except ValidationError as e:
        raise _handle(e)


@router.post("/{token}/claim")
@require_user
def claim_gift(token: str, current_user: User, svc: GiftService = Depends(get_service)):
    try:
        return svc.claim_gift(token, current_user)
    except ValidationError as e:
        raise _handle(e)
