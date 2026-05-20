import logging
import secrets
from datetime import datetime
from app.core.config import settings

log = logging.getLogger(__name__)

import stripe
from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.orm_models.auth import User
from app.orm_models.board import Board
from app.orm_models.order import Order, OrderDetails
from app.orm_models.price import BoardTypePrice, PriceVersion, ShippingRate

stripe.api_key = settings.STRIPE_SECRET_KEY
WEBHOOK_SECRET = settings.STRIPE_WEBHOOK_SECRET

_base = settings.FRONTEND_URL.rstrip("/")
SUCCESS_URL = f"{_base}/orders?success=true&session_id={{CHECKOUT_SESSION_ID}}"
CANCEL_URL  = f"{_base}/cart?cancelled=true&session_id={{CHECKOUT_SESSION_ID}}"


def _generate_cart_ref() -> str:
    return "C-" + datetime.utcnow().strftime("%Y%m%d") + "-" + secrets.token_hex(2).upper()


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


def _get_shipping_for_country(country: str, db: Session) -> tuple[ShippingRate, list[str]]:
    """Return (ShippingRate row, allowed_countries) from the DB.

    Restricts allowed_countries to the single selected country so the Stripe
    address form cannot be changed to a different country after selection.
    """
    code     = country.upper().strip()
    latest   = db.query(PriceVersion).order_by(PriceVersion.created_at.desc()).first()
    rate_row = (
        db.query(ShippingRate)
        .filter_by(price_version_id=latest.id, country_code=code)
        .first()
        if latest else None
    )
    if not rate_row:
        raise HTTPException(
            status_code=400,
            detail=f"Shipping to {code} is not configured. Please select an available country.",
        )
    return rate_row, [code]


def _build_stripe_shipping_option(rate_row: ShippingRate) -> dict:
    return {
        "shipping_rate_data": {
            "type": "fixed_amount",
            "fixed_amount": {"amount": rate_row.cost_cents, "currency": "eur"},
            "display_name": f"Shipping to {rate_row.country_name}",
            "delivery_estimate": {
                "minimum": {"unit": "business_day", "value": rate_row.delivery_days_min},
                "maximum": {"unit": "business_day", "value": rate_row.delivery_days_max},
            },
        }
    }


class PaymentService:

    @staticmethod
    def create_checkout_session(payload, current_user: User, db: Session):
        if not payload.items:
            raise HTTPException(status_code=400, detail="Cart is empty")
        if not payload.shipping_country:
            raise HTTPException(status_code=400, detail="Shipping country is required")

        current_version = (
            db.query(PriceVersion)
            .order_by(PriceVersion.created_at.desc())
            .first()
        )
        if not current_version:
            raise HTTPException(status_code=400, detail="No price version configured")

        item_boards: list[tuple] = []
        for item in payload.items:
            board = db.query(Board).filter_by(id=item.boardId, owner_id=current_user.id).first()
            if not board:
                raise HTTPException(
                    status_code=404,
                    detail=f"Board #{item.boardId} not found or not owned by you",
                )
            unit_amount = _compute_price(board, current_version, db)
            item_boards.append((item, board, unit_amount))

        cart_ref = _generate_cart_ref()
        rate_row, allowed_countries = _get_shipping_for_country(payload.shipping_country, db)
        shipping_options = [_build_stripe_shipping_option(rate_row)]

        try:
            line_items = []
            for item, board, unit_amount in item_boards:
                line_items.append({
                    "price_data": {
                        "currency": "eur",
                        "unit_amount": unit_amount,
                        "product_data": {
                            "name": (
                                board.board_type.name if board.board_type
                                else board.name or f"Board #{board.id}"
                            ),
                        },
                    },
                    "quantity": 1,
                })

            session_params: dict = {
                "payment_method_types": ["card"],
                "line_items": line_items,
                "mode": "payment",
                "customer_email": current_user.email,
                "phone_number_collection": {"enabled": True},
                "invoice_creation": {"enabled": True},
                "shipping_address_collection": {
                    "allowed_countries": allowed_countries,
                },
                "metadata": {
                    "user_id":   str(current_user.id),
                    "board_ids": ",".join(str(i.boardId) for i in payload.items),
                    "cart_ref":  cart_ref,
                },
                "success_url": SUCCESS_URL,
                "cancel_url":  CANCEL_URL,
            }

            session_params["shipping_options"] = shipping_options

            session = stripe.checkout.Session.create(**session_params)

            for item, board, unit_amount in item_boards:
                order = Order(
                    stripe_session_id = session.id,
                    cart_ref          = cart_ref,
                    status            = "pending",
                    board_id          = item.boardId,
                    user_id           = current_user.id,
                    svg_content       = item.svg,
                    amount_cents      = unit_amount,
                    currency          = "eur",
                    price_version_id  = current_version.id,
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
        elif event["type"] == "charge.refunded":
            PaymentService._refund_orders(event["data"]["object"], db)

        return {"status": "ok"}

    @staticmethod
    def _confirm_order(session_event, db: Session):
        session_id = session_event["id"]
        # Retrieve fresh session so all fields (shipping_details, customer_details,
        # shipping_cost, payment_intent) are guaranteed to be present.
        try:
            session = stripe.checkout.Session.retrieve(session_id)
        except stripe.StripeError:
            session = session_event

        orders = db.query(Order).filter_by(stripe_session_id=session_id).all()
        if not orders:
            return

        stripe_total   = getattr(session, "amount_total", None) or 0
        expected_total = sum(o.amount_cents for o in orders)
        if stripe_total != expected_total:
            log.warning(
                "Amount mismatch for session %s: expected %d¢, Stripe reports %d¢",
                session["id"], expected_total, stripe_total,
            )

        # Extract shipping details collected by Stripe
        # In newer Stripe API versions, shipping is under collected_information.shipping_details
        shipping_details_id  = None
        collected_info       = getattr(session, "collected_information", None)
        shipping_detail_obj  = (
            getattr(collected_info, "shipping_details", None)
            if collected_info else None
        ) or getattr(session, "shipping_details", None)
        customer_details    = getattr(session, "customer_details", None)
        shipping_cost_obj   = getattr(session, "shipping_cost", None)
        payment_intent_id   = getattr(session, "payment_intent", None)

        if shipping_detail_obj:
            addr = getattr(shipping_detail_obj, "address", None)
            name = getattr(shipping_detail_obj, "name", "") or ""
            name_parts = name.split(" ", 1)
            first_name = name_parts[0] if name_parts else ""
            last_name  = name_parts[1] if len(name_parts) > 1 else ""
            phone      = getattr(customer_details, "phone", None) if customer_details else None

            user_id = orders[0].user_id
            od = OrderDetails(
                user_id       = user_id,
                first_name    = first_name,
                last_name     = last_name,
                phone         = phone,
                address_line1 = getattr(addr, "line1", "") or "",
                city          = getattr(addr, "city", "") or "",
                postal_code   = getattr(addr, "postal_code", "") or "",
                country       = getattr(addr, "country", "") or "",
            )
            db.add(od)
            db.flush()
            shipping_details_id = od.id

        shipping_cost_cents = None
        if shipping_cost_obj:
            shipping_cost_cents = getattr(shipping_cost_obj, "amount_total", None)

        for order in orders:
            if order.status == "pending":
                order.status              = "paid"
                order.paid_at             = datetime.utcnow()
                order.payment_intent_id   = payment_intent_id
                order.shipping_cost_cents = shipping_cost_cents
                if shipping_details_id:
                    order.shipping_details_id = shipping_details_id
                    order.billing_details_id  = shipping_details_id

        db.commit()

    @staticmethod
    def cancel_session(session_id: str, current_user: User, db: Session):
        """Immediately cancel pending orders when the user abandons the checkout."""
        orders = db.query(Order).filter_by(
            stripe_session_id=session_id,
            user_id=current_user.id,
            status="pending",
        ).all()
        for order in orders:
            order.status = "cancelled"
        db.commit()
        return {"cancelled": len(orders)}

    @staticmethod
    def _refund_orders(charge, db: Session):
        """Mark orders as refunded when Stripe fires charge.refunded."""
        payment_intent_id = getattr(charge, "payment_intent", None)
        if not payment_intent_id:
            return
        for order in db.query(Order).filter_by(payment_intent_id=payment_intent_id).all():
            if order.status not in ("cancelled", "refunded"):
                order.status = "refunded"
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
