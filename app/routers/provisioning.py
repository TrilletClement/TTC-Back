"""Device certificate provisioning.

Endpoint
--------
POST /api/provisioning/sign-csr

Called by the home server (home.trillet.uk) acting as enrollment proxy
for ESP32 devices booting for the first time on the home network.

Authentication
--------------
The caller must present the HOME_SERVER_SECRET in the Authorization header:
    Authorization: Bearer <HOME_SERVER_SECRET>
"""

from typing import Optional

from cryptography import x509
from cryptography.x509.oid import NameOID
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.orm_models.db import get_db
from app.services.provisioningService import ProvisioningService

router = APIRouter(prefix="/api/provisioning", tags=["provisioning"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class CSRSigningRequest(BaseModel):
    mac_address:   str
    hardware_type: str
    csr_pem:       str


class SigningResponse(BaseModel):
    cert_pem:         str
    expires_at:       str
    device_id:        int
    already_enrolled: bool


# ── Auth helper ───────────────────────────────────────────────────────────────

def _verify_home_server(authorization: Optional[str] = Header(default=None)) -> None:
    expected = f"Bearer {settings.HOME_SERVER_SECRET}"
    if not settings.HOME_SERVER_SECRET or authorization != expected:
        raise HTTPException(status_code=401, detail="Unauthorized enrollment proxy")


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/sign-csr", response_model=SigningResponse)
def sign_device_csr(
    payload: CSRSigningRequest,
    db: Session = Depends(get_db),
    _auth: None = Depends(_verify_home_server),
):
    mac = payload.mac_address.lower().strip()

    parts = mac.split(":")
    if len(parts) != 6 or not all(len(p) == 2 for p in parts):
        raise HTTPException(status_code=400, detail=f"Invalid MAC address format: {mac}")

    try:
        csr = x509.load_pem_x509_csr(payload.csr_pem.encode())
        cn_attrs = csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        csr_cn = cn_attrs[0].value.lower() if cn_attrs else ""
    except Exception:
        raise HTTPException(status_code=400, detail="Cannot parse CSR")

    if csr_cn != mac:
        raise HTTPException(
            status_code=400,
            detail=f"CSR CN '{csr_cn}' does not match declared MAC '{mac}'",
        )

    result = ProvisioningService.sign_device_csr(mac, payload.hardware_type, payload.csr_pem, db)
    return SigningResponse(**result)
