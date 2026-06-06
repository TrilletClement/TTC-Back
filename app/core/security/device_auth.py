"""Device authentication via mTLS client certificates.

In production, nginx terminates TLS and forwards these headers after
verifying the client cert against the device CA chain:

    X-Client-Cert-Fingerprint: <SHA-1 hex>
    X-Client-Cert-Subject:     CN=aa:bb:cc:dd:ee:ff,O=Trillet
    X-Client-Cert-Verified:    SUCCESS

Since uvicorn binds to the Docker-internal network only (127.0.0.1 or the
Docker bridge), only nginx can inject those headers — they cannot be spoofed
by an external caller.

In local development (ENV=local), the dependency falls back to an optional
X-Dev-Mac header so you can test device endpoints without running nginx.
"""

from datetime import datetime
from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.orm_models.db import get_db
from app.orm_models.device import ESP32Device
from app.orm_models.device_certificate import DeviceCertificate


def get_device_from_cert(
    x_client_cert_fingerprint: Optional[str] = Header(default=None),
    x_client_cert_verified: Optional[str] = Header(default=None),
    x_dev_mac: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> ESP32Device:
    """FastAPI dependency — resolves the calling device from its client cert.

    Returns the ESP32Device ORM object so endpoint handlers get the full
    device context (owner, board, firmware, …) in one dependency.
    """
    # ── Local development bypass ──────────────────────────────────────────────
    if settings.ENV == "local":
        if x_dev_mac:
            device = db.query(ESP32Device).filter_by(mac_address=x_dev_mac).first()
            if device:
                return device
            raise HTTPException(
                status_code=403,
                detail=f"Dev bypass: no device with MAC {x_dev_mac}",
            )
        # If neither cert headers nor dev mac provided in local, fall through
        # to the prod path so that local nginx setups are also tested correctly.

    # ── Production path ───────────────────────────────────────────────────────
    if x_client_cert_verified != "SUCCESS" or not x_client_cert_fingerprint:
        raise HTTPException(
            status_code=403,
            detail="Client certificate required",
        )

    # nginx provides SHA-1 in lowercase hex; normalise to uppercase for the DB
    fingerprint = x_client_cert_fingerprint.upper()

    cert = (
        db.query(DeviceCertificate)
        .filter(
            DeviceCertificate.cert_fingerprint_sha256 == fingerprint,
            DeviceCertificate.revoked_at.is_(None),
        )
        .first()
    )

    if not cert:
        raise HTTPException(status_code=403, detail="Device not authorized")

    if cert.expires_at < datetime.utcnow():
        raise HTTPException(status_code=403, detail="Device certificate expired")

    # Opportunistically update last_seen (best-effort, ignore write failures)
    try:
        cert.last_seen_at = datetime.utcnow()
        db.commit()
    except Exception:
        db.rollback()

    return cert.device
