from sqlalchemy.orm import Session
from app.orm_models.device import ESP32Device, FirmwarePackage, Hardware


class FirmwareRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, id: int) -> FirmwarePackage | None:
        return self.db.query(FirmwarePackage).filter(FirmwarePackage.id == id).first()

    def get_by_filename(self, filename: str) -> FirmwarePackage | None:
        return self.db.query(FirmwarePackage).filter(FirmwarePackage.filename == filename).first()

    def list_all(self) -> list[FirmwarePackage]:
        return self.db.query(FirmwarePackage).order_by(FirmwarePackage.created_at.desc()).all()

    def get_hardware_by_package(self, package_id: int) -> list[Hardware]:
        return self.db.query(Hardware).filter(Hardware.firmware_package_id == package_id).all()

    def get_devices_by_target(self, package_id: int) -> list[ESP32Device]:
        return self.db.query(ESP32Device).filter(ESP32Device.target_firmware_id == package_id).all()

    def get_devices_by_hardware(self, hardware_id: int) -> list[ESP32Device]:
        return self.db.query(ESP32Device).filter(ESP32Device.hardware_id == hardware_id).all()

    def get_devices_with_overrides(self) -> list[ESP32Device]:
        return (
            self.db.query(ESP32Device)
            .filter(ESP32Device.target_firmware_id.isnot(None))
            .order_by(ESP32Device.mac_address)
            .all()
        )

    def get_hardware_by_id(self, id: int) -> Hardware | None:
        return self.db.query(Hardware).filter(Hardware.id == id).first()

    def get_hardware_by_type(self, hardware_type: str) -> Hardware | None:
        return self.db.query(Hardware).filter(Hardware.hardware_type == hardware_type).first()

    def list_hardware(self) -> list[Hardware]:
        return self.db.query(Hardware).order_by(Hardware.hardware_type).all()

    def get_device_by_mac(self, mac: str) -> ESP32Device | None:
        return self.db.query(ESP32Device).filter(ESP32Device.mac_address == mac).first()

    def save(self, obj) -> None:
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)

    def delete(self, obj) -> None:
        self.db.delete(obj)
        self.db.commit()

    def detach_package_from_hardware(self, package_id: int) -> None:
        self.db.query(Hardware).filter(
            Hardware.firmware_package_id == package_id
        ).update({"firmware_package_id": None}, synchronize_session=False)

    def detach_package_from_devices(self, package_id: int) -> None:
        self.db.query(ESP32Device).filter(
            ESP32Device.target_firmware_id == package_id
        ).update({"target_firmware_id": None}, synchronize_session=False)

    def flush(self) -> None:
        self.db.flush()

    def commit(self) -> None:
        self.db.commit()