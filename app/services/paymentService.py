import logging
import secrets
from datetime import datetime, timedelta
from app.core.config import settings
from app.core.mail import send_gift_email

log = logging.getLogger(__name__)

import stripe
from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.orm_models.auth import User
from app.orm_models.order import Order, OrderDetails, OrderGift, OrderItem
from app.repositories.order_repo import OrderRepository
from app.services.svg_validation import validate_board_svg

stripe.api_key = settings.STRIPE_SECRET_KEY
WEBHOOK_SECRET = settings.STRIPE_WEBHOOK_SECRET

_base = settings.FRONTEND_URL.rstrip("/")
SUCCESS_URL = f"{_base}/orders?success=true&session_id={{CHECKOUT_SESSION_ID}}"
CANCEL_URL  = f"{_base}/cart?cancelled=true&session_id={{CHECKOUT_SESSION_ID}}"


def _generate_cart_ref() -> str:
    return "C-" + datetime.utcnow().strftime("%Y%m%d") + "-" + secrets.token_hex(2).upper()


def _compute_price(board, version, repo: OrderRepository) -> int:
    if not board.board_type_id:
        raise HTTPException(
            status_code=400,
            detail=f"Board '{board.name}' has no board type assigned — cannot compute price",
        )
    entry = repo.get_price_entry(version.id, board.board_type_id)
    if not entry:
        raise HTTPException(
            status_code=400,
            detail=f"No price configured for the board type of '{board.name}' in the current price version",
        )
    return entry.reduced_price_cents or entry.base_price_cents


_KG_PER_ITEM = 0.5


def _resolve_shipping(
    country: str,
    postal_code: str,
    option_code: str,
    item_count: int,
    db: Session,
) -> tuple[int, str, list[str]]:
    from app.services import sendcloudService, adminShippingService

    code = country.upper().strip()

    # The public preview endpoint (routers/shipping.py) already restricts
    # results to admin-approved countries/options — this is the same check
    # applied where it actually matters: a client can call this endpoint
    # directly without ever hitting the preview one, so without it a
    # customer could check out to a country or via a carrier/service level
    # the store operator never enabled, which admin fulfillment then honors
    # unquestioningly (shipping_option_code is stored as-is on the order and
    # passed straight to SendCloud at ship time).
    if code not in adminShippingService.get_allowed_country_codes(db):
        raise HTTPException(status_code=400, detail="We do not ship to this country.")

    allowed_options = set(adminShippingService.get_enabled_codes(db))
    if not option_code or option_code not in allowed_options:
        raise HTTPException(status_code=400, detail="Invalid shipping option.")

    if sendcloudService._enabled():
        weight_kg = max(item_count, 1) * _KG_PER_ITEM
        price = sendcloudService.get_option_price_cents(option_code, code, "", weight_kg)
        if price is not None:
            label = option_code.split(":")[0].upper() + " — " + option_code.split(":")[-1].split("/")[0]
            return price, label, [code]

    raise HTTPException(
        status_code=400,
        detail="Could not determine shipping cost. Please select a valid shipping option.",
    )


def _build_stripe_shipping_option(cost_cents: int, display_name: str) -> dict:
    return {
        "shipping_rate_data": {
            "type": "fixed_amount",
            "fixed_amount": {"amount": cost_cents, "currency": "eur"},
            "display_name": display_name,
        }
    }


class PaymentService:

    @staticmethod
    def create_checkout_session(payload, current_user: User, db: Session):
        if not payload.items:
            raise HTTPException(status_code=400, detail="Cart is empty")
        if not payload.shipping_country:
            raise HTTPException(status_code=400, detail="Shipping country is required")
        if payload.is_gift and not (payload.gift_recipient_name.strip() and payload.gift_recipient_email.strip()):
            raise HTTPException(status_code=400, detail="Recipient name and email are required for a gift")

        repo = OrderRepository(db)
        current_version = repo.get_current_price_version()
        if not current_version:
            raise HTTPException(status_code=400, detail="No price version configured")

        item_boards: list[tuple] = []
        for item in payload.items:
            board = repo.get_board_for_user(item.boardId, current_user.id)
            if not board:
                raise HTTPException(
                    status_code=404,
                    detail=f"Board #{item.boardId} not found or not owned by you",
                )
            validate_board_svg(item.svg)
            unit_amount = _compute_price(board, current_version, repo)
            item_boards.append((item, board, unit_amount))

        cart_ref = _generate_cart_ref()
        cost_cents, ship_label, allowed_countries = _resolve_shipping(
            payload.shipping_country,
            getattr(payload, "shipping_postal_code", ""),
            getattr(payload, "shipping_option_code", ""),
            len(payload.items),
            db,
        )
        shipping_options = [_build_stripe_shipping_option(cost_cents, ship_label)]

        try:
            line_items = [
                {
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
                }
                for _, board, unit_amount in item_boards
            ]

            session_params: dict = {
                "payment_method_types": ["card"],
                "line_items": line_items,
                "mode": "payment",
                "customer_email": current_user.email,
                "phone_number_collection": {"enabled": True},
                "invoice_creation": {"enabled": True},
                "shipping_address_collection": {"allowed_countries": allowed_countries},
                "metadata": {
                    "user_id":   str(current_user.id),
                    "board_ids": ",".join(str(i.boardId) for i in payload.items),
                    "cart_ref":  cart_ref,
                },
                "success_url": SUCCESS_URL,
                "cancel_url":  CANCEL_URL,
                "shipping_options": shipping_options,
            }

            session = stripe.checkout.Session.create(**session_params)

            opt_code     = getattr(payload, "shipping_option_code", "") or None
            total_amount = sum(unit_amount for _, _, unit_amount in item_boards)

            order = repo.create_order(Order(
                stripe_session_id    = session.id,
                cart_ref             = cart_ref,
                status               = "pending",
                user_id              = current_user.id,
                amount_cents         = total_amount,
                currency             = "eur",
                price_version_id     = current_version.id,
                shipping_option_code = opt_code,
            ))

            for item, _, unit_amount in item_boards:
                repo.create_order_item(OrderItem(
                    order_id    = order.id,
                    board_id    = item.boardId,
                    svg_content = item.svg,
                    amount_cents = unit_amount,
                ))

            if payload.is_gift:
                repo.create_order_gift(OrderGift(
                    order_id        = order.id,
                    recipient_name  = payload.gift_recipient_name.strip(),
                    recipient_email = payload.gift_recipient_email.strip(),
                    message         = payload.gift_message.strip() or None,
                ))

                if (
                    payload.gift_ship_address_line1.strip()
                    and payload.gift_ship_city.strip()
                    and payload.gift_ship_postal_code.strip()
                ):
                    known_address = repo.create_order_details(OrderDetails(
                        user_id       = current_user.id,
                        first_name    = payload.gift_ship_first_name.strip() or payload.gift_recipient_name.strip(),
                        last_name     = payload.gift_ship_last_name.strip(),
                        phone         = payload.gift_ship_phone.strip() or None,
                        address_line1 = payload.gift_ship_address_line1.strip(),
                        city          = payload.gift_ship_city.strip(),
                        postal_code   = payload.gift_ship_postal_code.strip(),
                        country       = payload.shipping_country.strip(),
                    ))
                    order.shipping_details_id = known_address.id

            db.commit()
            return {"url": session.url}

        except stripe.StripeError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @staticmethod
    def get_payment_status(session_id: str, current_user: User, db: Session):
        repo = OrderRepository(db)
        order = repo.get_order_by_session_and_user(session_id, current_user.id)
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
            await PaymentService._confirm_order(event["data"]["object"], db)
        elif event["type"] in ("checkout.session.expired", "payment_intent.payment_failed"):
            PaymentService._cancel_pending_orders(event["data"]["object"], db)
        elif event["type"] == "charge.refunded":
            PaymentService._refund_orders(event["data"]["object"], db)

        return {"status": "ok"}

    @staticmethod
    async def _confirm_order(session_event, db: Session):
        session_id = session_event["id"]
        try:
            session = stripe.checkout.Session.retrieve(session_id)
        except stripe.StripeError:
            session = session_event

        repo   = OrderRepository(db)
        orders = repo.get_orders_by_session(session_id)
        if not orders:
            return

        stripe_total   = getattr(session, "amount_total", None) or 0
        expected_total = sum(o.amount_cents for o in orders)
        if stripe_total != expected_total:
            log.warning(
                "Amount mismatch for session %s: expected %d¢, Stripe reports %d¢",
                session_id, expected_total, stripe_total,
            )

        collected_info      = getattr(session, "collected_information", None)
        shipping_detail_obj = (
            getattr(collected_info, "shipping_details", None) if collected_info else None
        ) or getattr(session, "shipping_details", None)
        customer_details  = getattr(session, "customer_details", None)
        shipping_cost_obj = getattr(session, "shipping_cost", None)
        payment_intent_id = getattr(session, "payment_intent", None)

        shipping_details_id = None
        if shipping_detail_obj:
            addr = getattr(shipping_detail_obj, "address", None)
            name = getattr(shipping_detail_obj, "name", "") or ""
            name_parts = name.split(" ", 1)
            first_name = name_parts[0] if name_parts else ""
            last_name  = name_parts[1] if len(name_parts) > 1 else ""
            phone      = getattr(customer_details, "phone", None) if customer_details else None

            od = repo.create_order_details(OrderDetails(
                user_id       = orders[0].user_id,
                first_name    = first_name,
                last_name     = last_name,
                phone         = phone,
                address_line1 = getattr(addr, "line1", "") or "",
                city          = getattr(addr, "city", "") or "",
                postal_code   = getattr(addr, "postal_code", "") or "",
                country       = getattr(addr, "country", "") or "",
            ))
            shipping_details_id = od.id

        shipping_cost_cents = getattr(shipping_cost_obj, "amount_total", None) if shipping_cost_obj else None

        for order in orders:
            if order.status == "pending":
                order.status              = "paid"
                order.paid_at             = datetime.utcnow()
                order.payment_intent_id   = payment_intent_id
                order.shipping_cost_cents = shipping_cost_cents
                if shipping_details_id:
                    # A known gift shipping address (set at checkout) takes priority —
                    # whatever Stripe collected then becomes the billing address instead.
                    if not order.shipping_details_id:
                        order.shipping_details_id = shipping_details_id
                    if not order.billing_details_id:
                        order.billing_details_id = shipping_details_id

        gifts_to_email = []
        for order in orders:
            if order.gift and not order.gift.claim_token:
                order.gift.claim_token        = secrets.token_urlsafe(32)
                order.gift.claim_token_expiry = datetime.utcnow() + timedelta(days=30)
                gifts_to_email.append((order, order.gift))

        db.commit()

        for order, gift in gifts_to_email:
            claim_url = f"{_base}/gift/claim?token={gift.claim_token}"
            try:
                await send_gift_email(
                    gift.recipient_email, gift.recipient_name,
                    order.user.email if order.user else "", gift.message, claim_url,
                )
            except Exception:
                log.exception("Failed to send gift email for order %s", order.id)

    @staticmethod
    def cancel_session(session_id: str, current_user: User, db: Session):
        repo   = OrderRepository(db)
        orders = repo.get_pending_orders_by_session(session_id, current_user.id)
        for order in orders:
            order.status = "cancelled"
        db.commit()
        return {"cancelled": len(orders)}

    @staticmethod
    def _refund_orders(charge, db: Session):
        payment_intent_id = getattr(charge, "payment_intent", None)
        if not payment_intent_id:
            return
        repo = OrderRepository(db)
        for order in repo.get_orders_by_payment_intent(payment_intent_id):
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
        repo = OrderRepository(db)
        for order in repo.get_pending_orders_by_session(session_id):
            order.status = "cancelled"
        db.commit()
