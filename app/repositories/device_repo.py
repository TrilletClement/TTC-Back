import datetime
import json

from sqlalchemy.orm import Session, joinedload

from app.orm_models.auth import User
from app.orm_models.board import Board
from app.orm_models.device import ESP32Device, FirmwarePackage, Hardware
from app.orm_models.order import Order, OrderItem


class DeviceRepository:
    def __init__(self, db: Session):
        self.db = db

    # ── admin ─────────────────────────────────────────────────────────────────

    def list_all(self) -> list[ESP32Device]:
        return self.db.query(ESP32Device).order_by(ESP32Device.registered_at.desc().nullslast()).all()

    def get_by_id(self, device_id: int) -> ESP32Device | None:
        return self.db.query(ESP32Device).filter(ESP32Device.id == device_id).first()

    def get_orders_for_board(self, board_id: int) -> list[Order]:
        return (
            self.db.query(Order)
            .join(OrderItem, OrderItem.order_id == Order.id)
            .filter(OrderItem.board_id == board_id)
            .order_by(Order.created_at.desc())
            .all()
        )

    def get_user_by_email(self, email: str) -> User | None:
        return self.db.query(User).filter(User.email == email).first()

    def list_user_emails(self) -> list[str]:
        return [u.email for u in self.db.query(User.email).order_by(User.email).all()]

    def list_boards(self, owner_id: int | None = None) -> list[Board]:
        query = self.db.query(Board).options(joinedload(Board.owner))
        if owner_id is not None:
            query = query.filter(Board.owner_id == owner_id)
        return query.order_by(Board.name).all()

    def get_firmware_by_id(self, id: int) -> FirmwarePackage | None:
        return self.db.query(FirmwarePackage).filter(FirmwarePackage.id == id).first()

    def get_hardware_by_id(self, id: int) -> Hardware | None:
        return self.db.query(Hardware).filter(Hardware.id == id).first()

    def get_board_by_id(self, id: int) -> Board | None:
        return self.db.query(Board).filter(Board.id == id).first()

    def save(self, device: ESP32Device) -> ESP32Device:
        self.db.commit()
        self.db.refresh(device)
        return device

    # ── user-facing ───────────────────────────────────────────────────────────

    def get_devices_for_owner(self, owner_id: int) -> list[ESP32Device]:
        return self.db.query(ESP32Device).filter_by(owner_id=owner_id).all()

    def get_device_by_id_and_owner(self, esp_id: int, owner_id: int) -> ESP32Device | None:
        return self.db.query(ESP32Device).filter_by(id=esp_id, owner_id=owner_id).first()

    def get_device_by_mac(self, mac: str) -> ESP32Device | None:
        return self.db.query(ESP32Device).filter(ESP32Device.mac_address == mac).first()

    def get_board_by_id_and_owner(self, board_id: int, owner_id: int) -> Board | None:
        return self.db.query(Board).filter_by(id=board_id, owner_id=owner_id).first()

    def update_luminosity(self, device: ESP32Device, value: float) -> float:
        overrides = json.loads(device.json_settings_override or "{}")
        overrides["light_intensity_percent"] = max(0.0, min(100.0, value))
        device.json_settings_override = json.dumps(overrides)
        device.last_settings_updated_at = datetime.datetime.utcnow()
        self.db.commit()
        return overrides["light_intensity_percent"]

    def touch_last_connected(self, device: ESP32Device) -> None:
        device.last_connected = datetime.datetime.utcnow()
        self.db.commit()

    def commit(self) -> None:
        self.db.commit()