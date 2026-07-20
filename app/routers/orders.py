from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.user_access import require_user
from app.orm_models.auth import User
from app.orm_models.db import get_db
from app.schemas.order import GiftUpdate
from app.services.orderService import OrderService

router = APIRouter(prefix="/api/orders", tags=["orders"])


class OrderCreate(BaseModel):
    board_id: int
    svg_content: str
    details: dict


@router.post("")
@require_user
def create_order(
    payload: OrderCreate,
    current_user: User,
    db: Session = Depends(get_db),
):
    return OrderService.create_order(
        payload.board_id,
        payload.svg_content,
        payload.details,
        current_user.id,
        db,
    )


@router.get("")
@require_user
def list_orders(current_user: User, db: Session = Depends(get_db)):
    return OrderService.list_orders(current_user.id, db)


@router.get("/{order_id}/svg")
@require_user
def get_order_svg(order_id: int, current_user: User, db: Session = Depends(get_db)):
    return OrderService.get_order_svg(order_id, current_user.id, db)


@router.patch("/{order_id}/gift")
@require_user
async def update_gift(order_id: int, payload: GiftUpdate, current_user: User, db: Session = Depends(get_db)):
    return await OrderService.update_gift(order_id, payload, current_user.id, db)


@router.get("/{order_id}/return-portal-url")
@require_user
def get_return_portal_url(order_id: int, current_user: User, db: Session = Depends(get_db)):
    return OrderService.get_return_portal_url(order_id, current_user.id, db)
