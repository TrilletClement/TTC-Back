import logging
from datetime import datetime
from app.core.config import settings

log = logging.getLogger(__name__)

import stripe
from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.orm_models.auth import User
from app.orm_models.board import Board
from app.orm_models.order import Order, OrderDetails
from app.orm_models.price import BoardTypePrice, PriceVersion

stripe.api_key = settings.STRIPE_SECRET_KEY
WEBHOOK_SECRET = settings.STRIPE_WEBHOOK_SECRET

_base = settings.FRONTEND_URL.rstrip("/")
SUCCESS_URL = f"{_base}/orders?success=true&session_id={{CHECKOUT_SESSION_ID}}"
CANCEL_URL  = f"{_base}/cart?cancelled=true"


def _make_order_details(user_id: int, addr) -> OrderDetails:
    return OrderDetails(
        user_id       = user_id,
        first_name    = addr.firstName,
        last_name     = addr.lastName,
        phone         = getattr(addr, "phone", None),
        address_line1 = addr.addressLine1,
        city          = addr.city,
        postal_code   = addr.postalCode,
        country       = addr.country,
    )


def _compute_price(board: Board, version: PriceVersion, db: Session) -> int:
    """Return the server-authoritative unit price in cents for a board."""
    if not board.board_type_id:
        raise HTTPException(
            status_code=400,
            detail=f"Board '{board.name}' has no board type assigned — cannot compute price",
        )
    entry = db.query(BoardTypePrice).filter_by(
        price_version_id=version.id,
        board_type_id=board.board_type_id,
    ).first()
    if not entry:
        raise HTTPException(
            status_code=400,
            detail=f"No price configured for the board type of '{board.name}' in the current price version",
        )
    return entry.reduced_price_cents or entry.base_price_cents


class PaymentService:

    @staticmethod
    def create_checkout_session(payload, current_user: User, db: Session):
        if not payload.items:
            raise HTTPException(status_code=400, detail="Cart is empty")

        current_version = (
            db.query(PriceVersion)
            .order_by(PriceVersion.created_at.desc())
            .first()
        )
        if not current_version:
            raise HTTPException(status_code=400, detail="No price version configured")

        # Validate ownership and compute server-side prices in one pass
        item_boards: list[tuple] = []  # (item, board, unit_amount)
        for item in payload.items:
            board = db.query(Board).filter_by(id=item.boardId, owner_id=current_user.id).first()
            if not board:
                raise HTTPException(
                    status_code=404,
                    detail=f"Board #{item.boardId} not found or not owned by you",
                )
            unit_amount = _compute_price(board, current_version, db)
            item_boards.append((item, board, unit_amount))

        try:
            line_items = [
                {
                    "price_data": {
                        "currency": "eur",
                        "unit_amount": unit_amount,
                        "product_data": {
                            "name": item.boardName or board.name or f"Board #{item.boardId}",
                        },
                    },
                    "quantity": 1,
                }
                for item, board, unit_amount in item_boards
            ]

            shipping = payload.shipping
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=line_items,
                mode="payment",
                customer_email=current_user.email,
                metadata={
                    "user_id":       str(current_user.id),
                    "board_ids":     ",".join(str(i.boardId) for i in payload.items),
                    "customer_name": f"{shipping.firstName} {shipping.lastName}",
                    "city":          shipping.city,
                    "country":       shipping.country,
                },
                success_url=SUCCESS_URL,
                cancel_url=CANCEL_URL,
            )

            # Shipping address
            shipping_details = _make_order_details(current_user.id, shipping)
            db.add(shipping_details)
            db.flush()

            # Billing address — same row as shipping when not supplied
            if payload.billing:
                billing_details = _make_order_details(current_user.id, payload.billing)
                db.add(billing_details)
                db.flush()
            else:
                billing_details = shipping_details

            # One Order row per cart item, amount_cents from server-computed price
            for item, board, unit_amount in item_boards:
                order = Order(
                    stripe_session_id   = session.id,
                    status              = "pending",
                    board_id            = item.boardId,
                    user_id             = current_user.id,
                    shipping_details_id = shipping_details.id,
                    billing_details_id  = billing_details.id,
                    svg_content         = item.svg,
                    amount_cents        = unit_amount,
                    currency            = "eur",
                    price_version_id    = current_version.id,
                )
                db.add(order)

            db.commit()
            return {"url": session.url}

        except stripe.StripeError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @staticmethod
    def get_payment_status(session_id: str, current_user: User, db: Session):
        order = db.query(Order).filter_by(
            stripe_session_id=session_id,
            user_id=current_user.id,
        ).first()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        try:
            session = stripe.checkout.Session.retrieve(session_id)
            return {
                "status":         session.payment_status,
                "order_id":       order.id,
                "order_status":   order.status,
                "customer_email": session.customer_email,
                "amount_total":   session.amount_total,
                "currency":       session.currency,
            }
        except stripe.StripeError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @staticmethod
    async def handle_webhook(request: Request, db: Session):
        payload    = await request.body()
        sig_header = request.headers.get("stripe-signature")

        try:
            event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid payload")
        except stripe.SignatureVerificationError:
            raise HTTPException(status_code=400, detail="Invalid signature")

        if event["type"] == "checkout.session.completed":
            PaymentService._confirm_order(event["data"]["object"], db)
        elif event["type"] in ("checkout.session.expired", "payment_intent.payment_failed"):
            PaymentService._cancel_pending_orders(event["data"]["object"], db)

        return {"status": "ok"}

    @staticmethod
    def _confirm_order(session, db: Session):
        orders = db.query(Order).filter_by(stripe_session_id=session["id"]).all()

        stripe_total   = getattr(session, "amount_total", None) or 0
        expected_total = sum(o.amount_cents for o in orders)
        if stripe_total != expected_total:
            log.warning(
                "Amount mismatch for session %s: expected %d¢, Stripe reports %d¢",
                session["id"], expected_total, stripe_total,
            )

        for order in orders:
            if order.status == "pending":
                order.status  = "paid"
                order.paid_at = datetime.utcnow()
        db.commit()

    @staticmethod
    def _cancel_pending_orders(obj, db: Session):
        metadata   = getattr(obj, "metadata", None)
        session_id = getattr(obj, "id", None) or (
            metadata["stripe_session_id"] if metadata and "stripe_session_id" in metadata else None
        )
        if not session_id:
            return
        for order in db.query(Order).filter_by(stripe_session_id=session_id, status="pending").all():
            order.status = "cancelled"
        db.commit()
