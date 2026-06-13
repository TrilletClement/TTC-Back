import json
from fastapi import HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload
from app.orm_models.board import Board
from app.orm_models.order import Order, OrderDetails, OrderItem
from app.orm_models.price import PriceVersion


class OrderService:

    @staticmethod
    def create_order(
        board_id: int,
        svg_content: str,
        details: str | dict | None,
        user_id: int | None,
        db: Session
    ):
        if not board_id or not svg_content:
            raise HTTPException(
                status_code=400,
                detail="board_id and svg_content are required"
            )

        board = db.query(Board).filter_by(id=board_id).first()
        if not board:
            raise HTTPException(status_code=404, detail="Board not found")

        shipping_details = None

        if details:
            try:
                payload = details if isinstance(details, dict) else json.loads(details)
                shipping_details = OrderDetails(
                    first_name    = payload.get("firstName") or "",
                    last_name     = payload.get("lastName") or "",
                    address_line1 = payload.get("addressLine1") or "",
                    city          = payload.get("city") or "",
                    postal_code   = payload.get("postalCode") or "",
                    country       = payload.get("country") or "",
                    phone         = payload.get("phone"),
                    user_id       = user_id,
                )
                db.add(shipping_details)
                db.flush()
            except Exception:
                pass

        current_price_version = (
            db.query(PriceVersion)
            .order_by(PriceVersion.created_at.desc())
            .first()
        )

        order = Order(
            shipping_details_id = shipping_details.id if shipping_details else None,
            billing_details_id  = shipping_details.id if shipping_details else None,
            status              = "pending",
            price_version_id    = current_price_version.id if current_price_version else None,
            user_id             = user_id,
            amount_cents        = 0,
        )
        db.add(order)
        db.flush()

        item = OrderItem(
            order_id    = order.id,
            board_id    = board_id,
            svg_content = svg_content,
            amount_cents = 0,
        )
        db.add(item)
        db.commit()

        return {
            "message": "Order created",
            "order_id": order.id
        }

    @staticmethod
    def get_order_svg(order_id: int, user_id: int, db: Session):
        order = (
            db.query(Order)
            .options(joinedload(Order.items))
            .filter(Order.id == order_id, Order.user_id == user_id)
            .first()
        )
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        svg = next((i.svg_content for i in order.items if i.svg_content), None)
        if not svg:
            raise HTTPException(status_code=404, detail="No SVG stored for this order")

        return Response(content=svg, media_type="image/svg+xml")

    @staticmethod
    def list_orders(user_id: int, db: Session):
        orders = (
            db.query(Order)
            .options(
                joinedload(Order.shipping_details),
                joinedload(Order.items).joinedload(OrderItem.board),
                joinedload(Order.items).joinedload(OrderItem.esp_device),
            )
            .filter(Order.user_id == user_id)
            .order_by(Order.created_at.desc())
            .all()
        )
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
                "items": [
                    {
                        "id":           i.id,
                        "board_id":     i.board_id,
                        "board_name":   i.board.name if i.board else None,
                        "svg_content":  i.svg_content,
                        "amount_cents": i.amount_cents,
                        "esp_device_id": i.esp_device_id,
                    }
                    for i in o.items
                ],
            }
            for o in orders
        ]
