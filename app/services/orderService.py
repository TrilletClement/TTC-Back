import json

from fastapi import HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.domain.exceptions import BusinessError, ValidationError
from app.orm_models.order import Order, OrderDetails, OrderItem
from app.repositories.order_repo import OrderRepository
from app.services.giftService import GiftService


class OrderService:

    @staticmethod
    def create_order(
        board_id: int,
        svg_content: str,
        details: str | dict | None,
        user_id: int | None,
        db: Session,
    ):
        if not board_id or not svg_content:
            raise HTTPException(
                status_code=400,
                detail="board_id and svg_content are required",
            )

        repo = OrderRepository(db)
        board = repo.get_board_by_id(board_id)
        if not board:
            raise HTTPException(status_code=404, detail="Board not found")

        shipping_details = None
        if details:
            try:
                payload = details if isinstance(details, dict) else json.loads(details)
                od = OrderDetails(
                    first_name    = payload.get("firstName") or "",
                    last_name     = payload.get("lastName") or "",
                    address_line1 = payload.get("addressLine1") or "",
                    city          = payload.get("city") or "",
                    postal_code   = payload.get("postalCode") or "",
                    country       = payload.get("country") or "",
                    phone         = payload.get("phone"),
                    user_id       = user_id,
                )
                shipping_details = repo.create_order_details(od)
            except Exception:
                pass

        current_version = repo.get_current_price_version()

        order = repo.create_order(Order(
            shipping_details_id = shipping_details.id if shipping_details else None,
            billing_details_id  = shipping_details.id if shipping_details else None,
            status              = "pending",
            price_version_id    = current_version.id if current_version else None,
            user_id             = user_id,
            amount_cents        = 0,
        ))

        repo.create_order_item(OrderItem(
            order_id     = order.id,
            board_id     = board_id,
            svg_content  = svg_content,
            amount_cents = 0,
        ))
        db.commit()

        return {"message": "Order created", "order_id": order.id}

    @staticmethod
    async def update_gift(order_id: int, payload, user_id: int, db: Session):
        repo = OrderRepository(db)
        order = repo.get_for_user_with_items(order_id, user_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        try:
            return await GiftService(repo).update_gift_fields(order, payload)
        except (BusinessError, ValidationError) as e:
            raise HTTPException(status_code=400, detail=str(e))

    @staticmethod
    def get_order_svg(order_id: int, user_id: int, db: Session):
        repo = OrderRepository(db)
        order = repo.get_for_user_with_items(order_id, user_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        svg = next((i.svg_content for i in order.items if i.svg_content), None)
        if not svg:
            raise HTTPException(status_code=404, detail="No SVG stored for this order")

        return Response(content=svg, media_type="image/svg+xml")

    @staticmethod
    def list_orders(user_id: int, db: Session):
        repo = OrderRepository(db)
        orders = repo.list_for_user(user_id)
        return [
            {
                "id":                  o.id,
                "cart_ref":            o.cart_ref,
                "status":              o.status,
                "amount_cents":        o.amount_cents,
                "shipping_cost_cents": o.shipping_cost_cents,
                "currency":            o.currency,
                "created_at":          o.created_at.isoformat() if o.created_at else None,
                "tracking_number":     o.tracking_number,
                "tracking_url":        o.tracking_url,
                "shipping_details": {
                    "firstName":    o.shipping_details.first_name,
                    "lastName":     o.shipping_details.last_name,
                    "phone":        o.shipping_details.phone,
                    "addressLine1": o.shipping_details.address_line1,
                    "city":         o.shipping_details.city,
                    "postalCode":   o.shipping_details.postal_code,
                    "country":      o.shipping_details.country,
                } if o.shipping_details else None,
                "gift": {
                    "recipient_name":  o.gift.recipient_name,
                    "recipient_email": o.gift.recipient_email,
                    "message":         o.gift.message,
                    "claimed":         o.gift.claimed_at is not None,
                    "claimed_at":      o.gift.claimed_at.isoformat() if o.gift.claimed_at else None,
                } if o.gift else None,
                "items": [
                    {
                        "id":            i.id,
                        "board_id":      i.board_id,
                        "board_name":    i.board.name if i.board else None,
                        "svg_content":   i.svg_content,
                        "amount_cents":  i.amount_cents,
                        "esp_device_id": i.esp_device_id,
                    }
                    for i in o.items
                ],
            }
            for o in orders
        ]
