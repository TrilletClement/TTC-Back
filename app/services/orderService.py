import os
import json
from datetime import datetime
from fastapi import HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.orm_models.board import Board, Order, OrderDetails

ORDER_SVG_DIR = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "static", "orders"
)
os.makedirs(ORDER_SVG_DIR, exist_ok=True)


class OrderService:

    @staticmethod
    def create_order(
        board_id: int,
        svg_content: str,
        details: str | dict | None,
        led_colors: str | None,
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

        order_details = None

        if details:
            try:
                payload = details if isinstance(details, dict) else json.loads(details)
                email = payload.get("email")

                if email:
                    order_details = db.query(OrderDetails).filter_by(email=email).first()

                if not order_details:
                    order_details = OrderDetails(
                        first_name=payload.get("firstName"),
                        last_name=payload.get("lastName"),
                        email=email,
                        address_line1=payload.get("addressLine1"),
                        city=payload.get("city"),
                        postal_code=payload.get("postalCode"),
                        country=payload.get("country"),
                        user_id=user_id
                    )
                    db.add(order_details)
                    db.flush()
                else:
                    order_details.first_name = payload.get("firstName") or order_details.first_name
                    order_details.last_name = payload.get("lastName") or order_details.last_name
                    order_details.address_line1 = payload.get("addressLine1") or order_details.address_line1
                    order_details.city = payload.get("city") or order_details.city
                    order_details.postal_code = payload.get("postalCode") or order_details.postal_code
                    order_details.country = payload.get("country") or order_details.country

                    if user_id and not order_details.user_id:
                        order_details.user_id = user_id

            except Exception:
                pass

        filename = f"order_{board_id}_{int(datetime.utcnow().timestamp())}.svg"
        filepath = os.path.join(ORDER_SVG_DIR, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(svg_content)

        order = Order(
            board_id=board_id,
            order_details_id=order_details.id if order_details else None,
            svg_path=f"/static/orders/{filename}",
            status="pending",
            led_colors=led_colors
        )

        db.add(order)
        db.commit()

        return {
            "message": "Order created",
            "order_id": order.id
        }

    @staticmethod
    def get_order_svg(order_id: int, user_id: int, db: Session):
        order = (
            db.query(Order)
            .join(Board, Order.board_id == Board.id)
            .filter(Order.id == order_id)
            .first()
        )

        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        if order.board.owner_id != user_id:
            raise HTTPException(status_code=403, detail="Forbidden")

        filename = os.path.basename(order.svg_path or "")
        file_path = os.path.join(ORDER_SVG_DIR, filename)

        if not filename or not os.path.isfile(file_path):
            raise HTTPException(status_code=404, detail="SVG not found")

        return FileResponse(
            path=file_path,
            media_type="image/svg+xml",
            filename=filename
        )
