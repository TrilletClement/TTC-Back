from sqlalchemy.orm import Session
from app.orm_models.device import ESP32Device, Hardware


class SettingsRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_hardware_by_id(self, hardware_id: int) -> Hardware | None:
        return self.db.query(Hardware).filter(Hardware.id == hardware_id).first()

    def get_device_by_id(self, device_id: int) -> ESP32Device | None:
        return self.db.query(ESP32Device).filter(ESP32Device.id == device_id).first()

    def get_devices_by_hardware(self, hardware_id: int) -> list[ESP32Device]:
        return self.db.query(ESP32Device).filter(ESP32Device.hardware_id == hardware_id).all()

    def commit(self) -> None:
        self.db.commit()

    def refresh(self, obj) -> None:
        self.db.refresh(obj)