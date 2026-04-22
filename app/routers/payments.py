from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security.jwt import get_current_user
from app.orm_models.auth import User
from app.orm_models.db import get_db
from app.services.paymentService import PaymentService

router = APIRouter(prefix="/api/payments", tags=["payments"])


class CartItem(BaseModel):
    boardId: int
    boardName: str | None = None
    ledColors: str | None = None


class Customer(BaseModel):
    firstName: str
    lastName: str
    email: str
    addressLine1: str
    city: str
    postalCode: str
    country: str


class CartPayload(BaseModel):
    items: list[CartItem]
    customer: Customer


@router.post("/create-session")
def create_checkout_session(
    payload: CartPayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return PaymentService.create_checkout_session(payload, current_user, db)


@router.get("/status/{session_id}")
def get_payment_status(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return PaymentService.get_payment_status(session_id, current_user, db)


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    return await PaymentService.handle_webhook(request, db)