from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.user_access import require_user
from app.orm_models.auth import User
from app.orm_models.db import get_db
from app.services.orderService import OrderService

router = APIRouter(prefix="/api/orders", tags=["orders"])


class OrderCreate(BaseModel):
    board_id: int
    svg_content: str
    details: dict
    led_colors: dict


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
        payload.led_colors,
        current_user.id,
        db,
    )


@router.get("")
@require_user
def list_orders(current_user: User, db: Session = Depends(get_db)):
    return OrderService.list_orders(db)


@router.get("/{order_id}/svg")
@require_user
def get_order_svg(order_id: int, current_user: User, db: Session = Depends(get_db)):
    return OrderService.get_order_svg(order_id, current_user.id, db)
