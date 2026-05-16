from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.core.user_access import require_admin
from app.orm_models.auth import User
from app.orm_models.db import get_db
from app.orm_models.order import Order, OrderDetails
from app.orm_models.board import Board

router = APIRouter(prefix="/api/admin/orders", tags=["admin-orders"])

ORDER_STATUSES = {"pending", "paid", "shipped", "cancelled"}


def _order_dict(o: Order, include_svg: bool = False) -> dict:
    sd = o.shipping_details
    bd = o.billing_details
    same_address = sd and bd and sd.id == bd.id
    return {
        "id":              o.id,
        "status":          o.status,
        "amount_cents":    o.amount_cents,
        "currency":        o.currency,
        "tracking_number": o.tracking_number,
        "created_at":      o.created_at.isoformat() if o.created_at else None,
        "paid_at":         o.paid_at.isoformat() if o.paid_at else None,
        "stripe_session_id": o.stripe_session_id,
        "board_id":        o.board_id,
        "board_name":      o.board.name if o.board else None,
        "user_id":         o.user_id,
        "user_email":      o.user.email if o.user else None,
        "shipping_details": _addr_dict(sd),
        "billing_details":  None if same_address else _addr_dict(bd),
        "same_address":     same_address,
        **({"svg_content": o.svg_content} if include_svg else {}),
    }


def _addr_dict(d: Optional[OrderDetails]) -> Optional[dict]:
    if not d:
        return None
    return {
        "id":           d.id,
        "firstName":    d.first_name,
        "lastName":     d.last_name,
        "phone":        d.phone,
        "addressLine1": d.address_line1,
        "city":         d.city,
        "postalCode":   d.postal_code,
        "country":      d.country,
    }


def _base_query(db: Session):
    return (
        db.query(Order)
        .options(
            joinedload(Order.shipping_details),
            joinedload(Order.billing_details),
            joinedload(Order.board),
            joinedload(Order.user),
        )
    )


@router.get("")
@require_admin
def list_orders(
    current_user: User,
    db: Session = Depends(get_db),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    sort: str = Query("date_desc"),
):
    q = _base_query(db)

    if status:
        q = q.filter(Order.status == status)

    orders = q.all()

    if search:
        s = search.strip().lower()
        orders = [
            o for o in orders
            if s in (o.user.email or "").lower()
            or (o.shipping_details and s in f"{o.shipping_details.first_name} {o.shipping_details.last_name}".lower())
            or (o.board and s in (o.board.name or "").lower())
            or s in str(o.id)
        ]

    reverse = sort in ("date_desc", "amount_desc")
    key = (lambda o: o.amount_cents or 0) if "amount" in sort else (lambda o: o.created_at or "")
    orders = sorted(orders, key=key, reverse=reverse)

    return [_order_dict(o) for o in orders]


@router.get("/{order_id}")
@require_admin
def get_order(order_id: int, current_user: User, db: Session = Depends(get_db)):
    o = _base_query(db).filter(Order.id == order_id).first()
    if not o:
        raise HTTPException(status_code=404, detail="Order not found")
    return _order_dict(o, include_svg=True)


class AddressPatch(BaseModel):
    firstName:    Optional[str] = None
    lastName:     Optional[str] = None
    phone:        Optional[str] = None
    addressLine1: Optional[str] = None
    city:         Optional[str] = None
    postalCode:   Optional[str] = None
    country:      Optional[str] = None


class OrderPatch(BaseModel):
    status:           Optional[str] = None
    tracking_number:  Optional[str] = None
    shipping_details: Optional[AddressPatch] = None


@router.patch("/{order_id}")
@require_admin
def patch_order(order_id: int, payload: OrderPatch, current_user: User, db: Session = Depends(get_db)):
    o = _base_query(db).filter(Order.id == order_id).first()
    if not o:
        raise HTTPException(status_code=404, detail="Order not found")

    if payload.status is not None:
        if payload.status not in ORDER_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid status. Allowed: {ORDER_STATUSES}")
        o.status = payload.status

    if payload.tracking_number is not None:
        o.tracking_number = payload.tracking_number or None

    if payload.shipping_details and o.shipping_details:
        sd = payload.shipping_details
        d = o.shipping_details
        if sd.firstName    is not None: d.first_name    = sd.firstName
        if sd.lastName     is not None: d.last_name     = sd.lastName
        if sd.phone        is not None: d.phone         = sd.phone or None
        if sd.addressLine1 is not None: d.address_line1 = sd.addressLine1
        if sd.city         is not None: d.city          = sd.city
        if sd.postalCode   is not None: d.postal_code   = sd.postalCode
        if sd.country      is not None: d.country       = sd.country

    db.commit()
    db.refresh(o)
    return _order_dict(o, include_svg=False)
