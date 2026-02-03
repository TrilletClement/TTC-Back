from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.orm_models.db import Base


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
    version_hard = Column(String(50))
    version_soft = Column(String(50))
    version_firmware = Column(String(50))
    version_updater = Column(String(50))
    last_connected = Column(DateTime)

    registered_at = Column(DateTime, default=datetime.now())

    def to_dict(self):
        return {
            "id": self.id,
            "mac_address": self.mac_address,
            "name": self.name,
            "owner_id": self.owner_id,
            "board_id": self.board_id,
            "registered_at": self.registered_at.isoformat() if self.registered_at else None,
        }
