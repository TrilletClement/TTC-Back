from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.orm_models.db import Base


class FirmwarePackage(Base):
    __tablename__ = "firmware_package"

    id = Column(Integer, primary_key=True)
    app_name = Column(String(100), nullable=False)
    app_version = Column(String(50), nullable=False)
    package_file = Column(String(255), nullable=False, unique=True)
    uploaded_by_user_id = Column(Integer, ForeignKey("user.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    uploaded_by = relationship("User")

    __table_args__ = (
        UniqueConstraint("app_name", "app_version", name="uq_firmware_package_identity"),
    )


class Hardware(Base):
    __tablename__ = "hardware"

    id = Column(Integer, primary_key=True)
    hardware_type = Column(String(100), nullable=False)
    hardware_version = Column(String(100), nullable=False, default="")
    default_firmware_package_id = Column(Integer, ForeignKey("firmware_package.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    default_firmware = relationship("FirmwarePackage", foreign_keys=[default_firmware_package_id])
    firmware_assignments = relationship(
        "HardwareFirmwareAssignment",
        back_populates="hardware",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("hardware_type", "hardware_version", name="uq_hardware_type_version"),
    )


class HardwareFirmwareAssignment(Base):
    __tablename__ = "hardware_firmware_assignment"

    id = Column(Integer, primary_key=True)
    hardware_id = Column(Integer, ForeignKey("hardware.id"), nullable=False)
    firmware_name = Column(String(100), nullable=False)
    firmware_package_id = Column(Integer, ForeignKey("firmware_package.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    hardware = relationship("Hardware", back_populates="firmware_assignments")
    firmware_package = relationship("FirmwarePackage", foreign_keys=[firmware_package_id])

    __table_args__ = (
        UniqueConstraint("hardware_id", "firmware_name", name="uq_hardware_firmware_assignment"),
    )


class ESP32Device(Base):
    __tablename__ = "esp32_device"

    id = Column(Integer, primary_key=True)
    mac_address = Column(String(17), unique=True, nullable=False)
    name = Column(String(100))
    owner_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    owner = relationship("User", backref="esp32_devices")
    board_id = Column(Integer, ForeignKey("board.id"))
    board = relationship("Board", backref="esp32_devices")
    test = Column(Boolean, default=False)
    hardware_id = Column(Integer, ForeignKey("hardware.id"), nullable=True)
    hardware = relationship("Hardware", foreign_keys=[hardware_id])
    version_updater = Column(String(50))
    current_firmware_id = Column(Integer, ForeignKey("firmware_package.id"), nullable=True)
    target_firmware_id = Column(Integer, ForeignKey("firmware_package.id"), nullable=True)
    current_firmware = relationship("FirmwarePackage", foreign_keys=[current_firmware_id])
    target_firmware = relationship("FirmwarePackage", foreign_keys=[target_firmware_id])
    last_connected = Column(DateTime)
    last_ota_check = Column(DateTime)

    registered_at = Column(DateTime, default=datetime.now())

    def to_dict(self):
        return {
            "id": self.id,
            "mac_address": self.mac_address,
            "name": self.name,
            "owner_id": self.owner_id,
            "board_id": self.board_id,
            "hardware_id": self.hardware_id,
            "current_firmware_id": self.current_firmware_id,
            "target_firmware_id": self.target_firmware_id,
            "last_connected": self.last_connected.isoformat() if self.last_connected else None,
            "last_ota_check": self.last_ota_check.isoformat() if self.last_ota_check else None,
            "registered_at": self.registered_at.isoformat() if self.registered_at else None,
        }
