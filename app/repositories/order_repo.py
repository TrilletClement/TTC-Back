from sqlalchemy.orm import Session, joinedload

from app.orm_models.board import Board
from app.orm_models.device import ESP32Device
from app.orm_models.order import Order, OrderDetails, OrderGift, OrderItem
from app.orm_models.price import BoardTypePrice, PriceVersion


class OrderRepository:
    def __init__(self, db: Session):
        self.db = db

    # ── Price helpers ─────────────────────────────────────────────────────────

    def get_current_price_version(self) -> PriceVersion | None:
        return (
            self.db.query(PriceVersion)
            .order_by(PriceVersion.created_at.desc())
            .first()
        )

    def get_price_entry(self, version_id: int, board_type_id: int) -> BoardTypePrice | None:
        return self.db.query(BoardTypePrice).filter_by(
            price_version_id=version_id,
            board_type_id=board_type_id,
        ).first()

    def get_board_for_user(self, board_id: int, user_id: int) -> Board | None:
        return self.db.query(Board).filter_by(id=board_id, owner_id=user_id).first()

    def get_board_by_id(self, board_id: int) -> Board | None:
        return self.db.query(Board).filter_by(id=board_id).first()

    def get_board_names_for_owner(self, owner_id: int, exclude_board_id: int) -> set[str]:
        return {
            b.name for b in self.db.query(Board).filter(
                Board.owner_id == owner_id,
                Board.archived.is_(False),
                Board.id != exclude_board_id,
            ).all()
            if b.name
        }

    # ── Order writes ──────────────────────────────────────────────────────────

    def create_order_details(self, details: OrderDetails) -> OrderDetails:
        self.db.add(details)
        self.db.flush()
        return details

    def create_order_gift(self, gift: OrderGift) -> OrderGift:
        self.db.add(gift)
        self.db.flush()
        return gift

    def create_order(self, order: Order) -> Order:
        self.db.add(order)
        self.db.flush()
        return order

    def create_order_item(self, item: OrderItem) -> None:
        self.db.add(item)

    # ── Order reads ───────────────────────────────────────────────────────────

    def get_order_by_session_and_user(self, session_id: str, user_id: int) -> Order | None:
        return self.db.query(Order).filter_by(
            stripe_session_id=session_id,
            user_id=user_id,
        ).first()

    def get_orders_by_session(self, session_id: str) -> list[Order]:
        return self.db.query(Order).filter_by(stripe_session_id=session_id).all()

    def get_orders_by_payment_intent(self, payment_intent_id: str) -> list[Order]:
        return self.db.query(Order).filter_by(payment_intent_id=payment_intent_id).all()

    def get_pending_orders_by_session(self, session_id: str, user_id: int | None = None) -> list[Order]:
        q = self.db.query(Order).filter_by(stripe_session_id=session_id, status="pending")
        if user_id is not None:
            q = q.filter_by(user_id=user_id)
        return q.all()

    def list_for_user(self, user_id: int) -> list[Order]:
        return (
            self.db.query(Order)
            .options(
                joinedload(Order.shipping_details),
                joinedload(Order.gift),
                joinedload(Order.items).joinedload(OrderItem.board),
                joinedload(Order.items).joinedload(OrderItem.esp_device),
            )
            .filter(Order.user_id == user_id)
            .order_by(Order.created_at.desc())
            .all()
        )

    def get_for_user_with_items(self, order_id: int, user_id: int) -> Order | None:
        return (
            self.db.query(Order)
            .options(joinedload(Order.items), joinedload(Order.gift))
            .filter(Order.id == order_id, Order.user_id == user_id)
            .first()
        )

    def _base_query(self):
        return (
            self.db.query(Order)
            .options(
                joinedload(Order.shipping_details),
                joinedload(Order.billing_details),
                joinedload(Order.gift),
                joinedload(Order.user),
                joinedload(Order.items).joinedload(OrderItem.board),
                joinedload(Order.items).joinedload(OrderItem.esp_device),
            )
        )

    def list_all(self, status: str | None = None) -> list[Order]:
        q = self._base_query()
        if status:
            q = q.filter(Order.status == status)
        return q.all()

    def get_by_id(self, order_id: int) -> Order | None:
        return self._base_query().filter(Order.id == order_id).first()

    def get_item_by_id(self, item_id: int) -> OrderItem | None:
        return (
            self.db.query(OrderItem)
            .options(
                joinedload(OrderItem.board),
                joinedload(OrderItem.esp_device),
                joinedload(OrderItem.order).joinedload(Order.user),
                joinedload(OrderItem.order).joinedload(Order.shipping_details),
                joinedload(OrderItem.order).joinedload(Order.billing_details),
                joinedload(OrderItem.order).joinedload(Order.gift),
                joinedload(OrderItem.order).joinedload(Order.items).joinedload(OrderItem.board),
                joinedload(OrderItem.order).joinedload(Order.items).joinedload(OrderItem.esp_device),
            )
            .filter(OrderItem.id == item_id)
            .first()
        )

    def get_gift_by_token(self, token: str) -> OrderGift | None:
        return (
            self.db.query(OrderGift)
            .options(
                joinedload(OrderGift.order).joinedload(Order.user),
                joinedload(OrderGift.order).joinedload(Order.items).joinedload(OrderItem.board),
                joinedload(OrderGift.order).joinedload(Order.items).joinedload(OrderItem.esp_device),
            )
            .filter(OrderGift.claim_token == token)
            .first()
        )

    def get_device_by_id(self, device_id: int) -> ESP32Device | None:
        return self.db.query(ESP32Device).filter(ESP32Device.id == device_id).first()

    def list_unowned_devices(self) -> list[ESP32Device]:
        return self.db.query(ESP32Device).filter(ESP32Device.owner_id.is_(None)).all()

    def list_all_devices(self) -> list[ESP32Device]:
        # AdminOrdersService.list_all_devices reads d.owner.email per row for
        # the device-select dropdown — eager-load avoids 1+N lazy loads.
        return (
            self.db.query(ESP32Device)
            .options(joinedload(ESP32Device.owner))
            .order_by(ESP32Device.registered_at.desc().nullslast())
            .all()
        )

    def get_device_names_for_owner(self, owner_id: int, exclude_device_id: int) -> set[str]:
        return {
            d.name for d in self.db.query(ESP32Device).filter(
                ESP32Device.owner_id == owner_id,
                ESP32Device.id != exclude_device_id,
            ).all()
            if d.name
        }

    def save(self, obj) -> None:
        self.db.commit()
        self.db.refresh(obj)
