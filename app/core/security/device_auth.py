"""Device authentication for mTLS-protected device endpoints.

Architecture
------------
Apache acts as the TLS terminator and cert gatekeeper:

  SSLVerifyClient optional_no_ca
  Require expr "%{SSL:SSL_CLIENT_VERIFY} =~ /^(GENEROUS|SUCCESS)$/"  # in device Locations

Requests without a client cert are rejected by Apache (403) before reaching
FastAPI. Requests that do reach FastAPI have SSL_CLIENT_VERIFY=GENEROUS
forwarded as X-Client-Cert-Verified.

Device identity is provided by the device in the X-Device-Mac request header.
Apache proxies it as-is. Security model: TLS proves key ownership; Apache ensures
only cert-bearing connections reach device endpoints; MAC identifies which device.

Local development
-----------------
Set ENV=local and send X-Dev-Mac: <mac> to bypass the cert gate.
"""

import logging
from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.orm_models.db import get_db
from app.orm_models.device import ESP32Device

logger = logging.getLogger(__name__)


def get_device_from_mac(
    x_device_mac: Optional[str] = Header(default=None),
    x_dev_mac: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> ESP32Device:
    """Resolve the calling device from the X-Device-Mac header.

    Apache has already gate-kept cert presence. FastAPI identifies which
    device it is by MAC and returns the full device ORM object.
    """
    mac_raw = x_device_mac or (x_dev_mac if settings.ENV == "local" else None)
    if not mac_raw:
        raise HTTPException(status_code=403, detail="X-Device-Mac header required")

    mac = mac_raw.lower().strip()
    device = db.query(ESP32Device).filter_by(mac_address=mac).first()
    if not device:
        raise HTTPException(status_code=403, detail=f"Device not registered: {mac}")

    return device


def require_device_cert(
    x_client_cert_verified: Optional[str] = Header(default=None),
) -> None:
    """Verify that the request passed Apache's mTLS gate.

    Used for endpoints that need cert presence but not device identity
    (e.g. firmware binary download). Defense-in-depth — Apache's Require expr
    already blocks no-cert requests before they reach FastAPI.
    """
    if settings.ENV == "local":
        return
    if x_client_cert_verified not in ("SUCCESS", "GENEROUS"):
        raise HTTPException(status_code=403, detail="Client certificate required")
