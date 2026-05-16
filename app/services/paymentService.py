from datetime import datetime
from app.core.config import settings

import stripe
from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.orm_models.auth import User
from app.orm_models.board import Board
from app.orm_models.order import Order, OrderDetails
from app.orm_models.price import PriceVersion

stripe.api_key  = settings.STRIPE_SECRET_KEY
WEBHOOK_SECRET  = settings.STRIPE_WEBHOOK_SECRET

SUCCESS_URL = "https://transport.trillet.be/orders?success=true&session_id={CHECKOUT_SESSION_ID}"
CANCEL_URL  = "https://transport.trillet.be/cart?cancelled=true"


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


class PaymentService:

    @staticmethod
    def create_checkout_session(payload, current_user: User, db: Session):
        if not payload.items:
            raise HTTPException(status_code=400, detail="Cart is empty")

        for item in payload.items:
            board = db.query(Board).filter_by(id=item.boardId, owner_id=current_user.id).first()
            if not board:
                raise HTTPException(
                    status_code=404,
                    detail=f"Board #{item.boardId} not found or not owned by you"
                )

        current_version = (
            db.query(PriceVersion)
            .order_by(PriceVersion.created_at.desc())
            .first()
        )

        try:
            line_items = []
            total_cents = 0
            for item in payload.items:
                unit_amount = item.reducedPriceCents or item.basePriceCents or 5000
                total_cents += unit_amount
                line_items.append({
                    "price_data": {
                        "currency": "eur",
                        "unit_amount": unit_amount,
                        "product_data": {
                            "name": item.boardName or f"Board #{item.boardId}",
                            "description": f"LED colors: {item.ledColors}" if item.ledColors else None,
                        },
                    },
                    "quantity": 1,
                })

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
                    "address":       shipping.addressLine1,
                    "city":          shipping.city,
                    "postal_code":   shipping.postalCode,
                    "country":       shipping.country,
                },
                success_url=SUCCESS_URL,
                cancel_url=CANCEL_URL,
            )

            # Shipping address
            shipping_details = _make_order_details(current_user.id, shipping)
            db.add(shipping_details)
            db.flush()

            # Billing address — separate row only when different from shipping
            if payload.billing:
                billing_details = _make_order_details(current_user.id, payload.billing)
                db.add(billing_details)
                db.flush()
            else:
                billing_details = shipping_details

            # One Order row per cart item
            for item in payload.items:
                order = Order(
                    stripe_session_id   = session.id,
                    status              = "pending",
                    board_id            = item.boardId,
                    user_id             = current_user.id,
                    shipping_details_id = shipping_details.id,
                    billing_details_id  = billing_details.id,
                    svg_content         = item.svg,
                    amount_cents        = item.reducedPriceCents or item.basePriceCents or 5000,
                    currency            = "eur",
                    price_version_id    = current_version.id if current_version else None,
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
            user_id=current_user.id
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

        return {"status": "ok"}

    @staticmethod
    def _confirm_order(session: dict, db: Session):
        for order in db.query(Order).filter_by(stripe_session_id=session["id"]).all():
            order.status  = "paid"
            order.paid_at = datetime.utcnow()
        db.commit()
