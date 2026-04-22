from datetime import datetime
from app.core.config import settings

import stripe
from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.orm_models.auth import User
from app.orm_models.board import Board
from app.orm_models.order import Order, OrderDetails

stripe.api_key      = settings.STRIPE_SECRET_KEY
WEBHOOK_SECRET      = settings.STRIPE_WEBHOOK_SECRET

PRICE_PER_BOARD_CENTS = 5000  # 50€
SUCCESS_URL = "https://transport.trillet.be/orders?success=true&session_id={CHECKOUT_SESSION_ID}"
CANCEL_URL  = "https://transport.trillet.be/cart?cancelled=true"


class PaymentService:

    @staticmethod
    def create_checkout_session(payload, current_user: User, db: Session):
        if not payload.items:
            raise HTTPException(status_code=400, detail="Cart is empty")

        # Vérifier que les boards appartiennent bien à l'utilisateur
        for item in payload.items:
            board = db.query(Board).filter_by(id=item.boardId, owner_id=current_user.id).first()
            if not board:
                raise HTTPException(
                    status_code=404,
                    detail=f"Board #{item.boardId} not found or not owned by you"
                )

        try:
            line_items = [
                {
                    "price_data": {
                        "currency": "eur",
                        "unit_amount": PRICE_PER_BOARD_CENTS,
                        "product_data": {
                            "name": item.boardName or f"Board #{item.boardId}",
                            "description": f"LED colors: {item.ledColors}" if item.ledColors else None,
                        },
                    },
                    "quantity": 1,
                }
                for item in payload.items
            ]

            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=line_items,
                mode="payment",
                customer_email=payload.customer.email,
                shipping_address_collection={
                    "allowed_countries": ["BE", "FR", "LU", "NL", "DE"],
                },
                metadata={
                    "user_id":       str(current_user.id),
                    "board_id":      str(payload.items[0].boardId),
                    "customer_name": f"{payload.customer.firstName} {payload.customer.lastName}",
                    "address":       payload.customer.addressLine1,
                    "city":          payload.customer.city,
                    "postal_code":   payload.customer.postalCode,
                    "country":       payload.customer.country,
                },
                success_url=SUCCESS_URL,
                cancel_url=CANCEL_URL,
            )

            order_details = OrderDetails(
                user_id       = current_user.id,
                first_name    = payload.customer.firstName,
                last_name     = payload.customer.lastName,
                email         = payload.customer.email,
                address_line1 = payload.customer.addressLine1,
                city          = payload.customer.city,
                postal_code   = payload.customer.postalCode,
                country       = payload.customer.country,
            )
            db.add(order_details)
            db.flush()
            
            # Créer la commande en base avec status pending
            order = Order(
                stripe_session_id = session.id,
                status            = "pending",
                board_id          = payload.items[0].boardId,
                user_id           = current_user.id,
                order_details_id  = order_details.id,
                led_colors        = payload.items[0].ledColors or "",
                svg_path          = "",
                amount_cents      = PRICE_PER_BOARD_CENTS * len(payload.items),
                currency          = "eur",
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
        order = db.query(Order).filter_by(stripe_session_id=session["id"]).first()
        if not order:
            return

        order.status  = "paid"
        order.paid_at = datetime.utcnow()
        db.commit()