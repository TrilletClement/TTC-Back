from sqlalchemy.orm import Session, joinedload
from app.orm_models.order import Order, OrderDetails
from app.orm_models.device import ESP32Device


class OrderRepository:
    def __init__(self, db: Session):
        self.db = db

    def _base_query(self):
        return (
            self.db.query(Order)
            .options(
                joinedload(Order.shipping_details),
                joinedload(Order.billing_details),
                joinedload(Order.board),
                joinedload(Order.user),
                joinedload(Order.esp_device),
            )
        )

    def list_all(self, status: str | None = None) -> list[Order]:
        q = self._base_query()
        if status:
            q = q.filter(Order.status == status)
        return q.all()

    def get_by_id(self, order_id: int) -> Order | None:
        return self._base_query().filter(Order.id == order_id).first()

    def get_device_by_id(self, device_id: int) -> ESP32Device | None:
        return self.db.query(ESP32Device).filter(ESP32Device.id == device_id).first()

    def list_unowned_devices(self) -> list[ESP32Device]:
        return self.db.query(ESP32Device).filter(ESP32Device.owner_id.is_(None)).all()

    def list_all_devices(self) -> list[ESP32Device]:
        return self.db.query(ESP32Device).order_by(ESP32Device.registered_at.desc().nullslast()).all()

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