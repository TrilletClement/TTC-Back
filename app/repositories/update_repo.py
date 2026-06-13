from typing import Optional

from sqlalchemy.orm import Session

from app.orm_models.device import ESP32Device, FirmwarePackage, Hardware


class UpdateRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_device_by_mac(self, mac: str) -> Optional[ESP32Device]:
        return self.db.query(ESP32Device).filter(ESP32Device.mac_address == mac).first()

    def get_hardware_by_type(self, hardware_type: str) -> Optional[Hardware]:
        return self.db.query(Hardware).filter(Hardware.hardware_type == hardware_type).first()

    def get_firmware_by_filename(self, filename: str) -> Optional[FirmwarePackage]:
        return self.db.query(FirmwarePackage).filter(FirmwarePackage.filename == filename).first()

    def get_active_firmware_by_id(self, firmware_id: int) -> Optional[FirmwarePackage]:
        return (
            self.db.query(FirmwarePackage)
            .filter(FirmwarePackage.id == firmware_id, FirmwarePackage.archived == False)
            .first()
        )

    def firmware_exists(self, filename: str) -> bool:
        return (
            self.db.query(FirmwarePackage.id)
            .filter(FirmwarePackage.filename == filename)
            .first()
        ) is not None

    def commit(self) -> None:
        self.db.commit()
