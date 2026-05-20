from typing import Optional
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.user_access import require_user
from app.orm_models.auth import User
from app.orm_models.db import get_db
from app.services.paymentService import PaymentService

router = APIRouter(prefix="/api/payments", tags=["payments"])


class CartItem(BaseModel):
    boardId: int
    boardName: Optional[str] = None
    svg: Optional[str] = None


class CartPayload(BaseModel):
    items: list[CartItem]
    shipping_country: str = ""


@router.post("/create-session")
@require_user
def create_checkout_session(
    payload: CartPayload,
    current_user: User,
    db: Session = Depends(get_db),
):
    return PaymentService.create_checkout_session(payload, current_user, db)


@router.get("/status/{session_id}")
@require_user
def get_payment_status(
    session_id: str,
    current_user: User,
    db: Session = Depends(get_db),
):
    return PaymentService.get_payment_status(session_id, current_user, db)


@router.post("/cancel-session/{session_id}")
@require_user
def cancel_session(session_id: str, current_user: User, db: Session = Depends(get_db)):
    """Called when user lands on the cancel URL after abandoning Stripe checkout."""
    return PaymentService.cancel_session(session_id, current_user, db)


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """Public endpoint called directly by Stripe — no auth."""
    return await PaymentService.handle_webhook(request, db)
