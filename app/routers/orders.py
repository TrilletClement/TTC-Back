from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.services.orderService import OrderService
from app.core.security.jwt import get_current_user
from app.orm_models.db import get_db
from app.orm_models.auth import User

router = APIRouter(prefix="/api/orders", tags=["orders"])


class OrderCreate(BaseModel):
    board_id: int
    svg_content: str
    details: dict
    led_colors: dict


@router.post("")
def create_order(
    payload: OrderCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user_id = current_user.id if current_user else None

    return OrderService.create_order(
        payload.board_id,
        payload.svg_content,
        payload.details,
        payload.led_colors,
        user_id,
        db
    )


@router.get("")
def list_orders(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return OrderService.list_orders(db)


@router.get("/{order_id}/svg")
def get_order_svg(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user_id = current_user.id if current_user else None
    return OrderService.get_order_svg(order_id, user_id, db)

