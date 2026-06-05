from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.orm_models.db import Base


class DeviceCertificate(Base):
    """One X.509 client certificate issued to an ESP32 device.

    The fingerprint (SHA-256 of the DER cert) is the lookup key on every
    device request — nginx forwards it as X-Client-Cert-Fingerprint.

    The MAC address is stored separately (extracted from the cert CN at
    signing time) so that cert rotation preserves the device identity link.
    """
    __tablename__ = "device_certificate"

    id                    = Column(Integer, primary_key=True)
    esp32_device_id       = Column(Integer, ForeignKey("esp32_device.id"), nullable=False, index=True)
    mac_address           = Column(String(17), nullable=False, index=True)
    cert_serial           = Column(Numeric(scale=0), nullable=False, unique=True)
    cert_subject          = Column(String(255), nullable=False)
    cert_fingerprint_sha256 = Column(String(64), nullable=False, unique=True, index=True)
    cert_pem              = Column(Text, nullable=False)
    issued_at             = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at            = Column(DateTime, nullable=False)
    revoked_at            = Column(DateTime, nullable=True)
    revocation_reason     = Column(String(255), nullable=True)
    last_seen_at          = Column(DateTime, nullable=True)

    device = relationship("ESP32Device", backref="certificates")
