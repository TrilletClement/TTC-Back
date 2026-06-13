import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.orm_models.device import ESP32Device, Hardware
from app.orm_models.device_certificate import DeviceCertificate


class ProvisioningRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_active_cert_by_mac(self, mac: str) -> Optional[DeviceCertificate]:
        return (
            self.db.query(DeviceCertificate)
            .filter(
                DeviceCertificate.mac_address == mac,
                DeviceCertificate.revoked_at.is_(None),
            )
            .first()
        )

    def get_hardware_by_type(self, hardware_type: str) -> Optional[Hardware]:
        return self.db.query(Hardware).filter_by(hardware_type=hardware_type).first()

    def get_device_by_mac(self, mac: str) -> Optional[ESP32Device]:
        return self.db.query(ESP32Device).filter_by(mac_address=mac).first()

    def create_device(self, device: ESP32Device) -> ESP32Device:
        self.db.add(device)
        self.db.flush()
        return device

    def revoke_cert(self, cert: DeviceCertificate, reason: str) -> None:
        cert.revoked_at = datetime.datetime.utcnow()
        cert.revocation_reason = reason
        self.db.flush()

    def create_cert(self, cert: DeviceCertificate) -> None:
        self.db.add(cert)

    def commit(self) -> None:
        self.db.commit()
