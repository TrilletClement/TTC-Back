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

This secret is shared between the home server and this production server.
It is NOT a device credential — it authenticates the enrollment proxy.

What happens
------------
1. Validate HOME_SERVER_SECRET.
2. Parse the CSR and validate the MAC address in the CN matches the
   mac_address field in the request body.
3. If the MAC already has an active (non-revoked) certificate → return it
   idempotently without signing a new one.
4. Look up or create the ESP32Device row (owner_id=None until a customer
   links the device to their account).
5. Sign the CSR with the Intermediate CA using the `cryptography` library.
6. Insert a DeviceCertificate row.
7. Return the signed certificate PEM.
"""

import datetime
import logging
from typing import Optional

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.orm_models.db import get_db
from app.orm_models.device import ESP32Device, Hardware
from app.orm_models.device_certificate import DeviceCertificate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/provisioning", tags=["provisioning"])

CERT_VALIDITY_DAYS = 5 * 365   # 5-year device certificates


# ── Request / Response schemas ────────────────────────────────────────────────

class CSRSigningRequest(BaseModel):
    mac_address: str          # e.g. "aa:bb:cc:dd:ee:ff"
    hardware_type: str        # e.g. "ESP32_WROOM" — matched against Hardware table
    csr_pem: str              # PEM-encoded PKCS#10 CSR generated on the device


class SigningResponse(BaseModel):
    cert_pem: str
    expires_at: str
    device_id: int
    already_enrolled: bool    # True if returning an existing cert


# ── Auth helper ───────────────────────────────────────────────────────────────

def _verify_home_server(authorization: Optional[str] = Header(default=None)) -> None:
    expected = f"Bearer {settings.HOME_SERVER_SECRET}"
    if not settings.HOME_SERVER_SECRET or authorization != expected:
        raise HTTPException(status_code=401, detail="Unauthorized enrollment proxy")


# ── CA signing ────────────────────────────────────────────────────────────────

def _load_ca():
    """Load the Intermediate CA key and certificate from the mounted volume."""
    try:
        with open(settings.DEVICE_CA_KEY_PATH, "rb") as f:
            ca_key = serialization.load_pem_private_key(f.read(), password=None)
        with open(settings.DEVICE_CA_CERT_PATH, "rb") as f:
            ca_cert = x509.load_pem_x509_certificate(f.read())
        return ca_key, ca_cert
    except FileNotFoundError as exc:
        logger.error("Device CA files not found: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="CA not initialised on server — run ca/setup-ca.sh first",
        )


def _sign_csr(csr_pem: str, mac_address: str) -> tuple[str, int, str, str, datetime.datetime]:
    """Sign a device CSR. Returns (cert_pem, serial_int, fingerprint_hex, subject_str, expires_at)."""
    ca_key, ca_cert = _load_ca()

    try:
        csr = x509.load_pem_x509_csr(csr_pem.encode())
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid CSR PEM")

    if not csr.is_signature_valid:
        raise HTTPException(status_code=400, detail="CSR signature is invalid")

    now = datetime.datetime.utcnow()
    expires_at = now + datetime.timedelta(days=CERT_VALIDITY_DAYS)
    serial = x509.random_serial_number()

    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, mac_address),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Trillet"),
        ]))
        .issuer_name(ca_cert.subject)
        .public_key(csr.public_key())
        .serial_number(serial)
        .not_valid_before(now)
        .not_valid_after(expires_at)
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None), critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    fingerprint = cert.fingerprint(hashes.SHA256()).hex().upper()
    subject = cert.subject.rfc4514_string()

    return cert_pem, serial, fingerprint, subject, expires_at


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/sign-csr", response_model=SigningResponse)
def sign_device_csr(
    payload: CSRSigningRequest,
    db: Session = Depends(get_db),
    _auth: None = Depends(_verify_home_server),
):
    mac = payload.mac_address.lower().strip()

    # Validate MAC format (basic check)
    parts = mac.split(":")
    if len(parts) != 6 or not all(len(p) == 2 for p in parts):
        raise HTTPException(status_code=400, detail=f"Invalid MAC address format: {mac}")

    # Validate CSR CN matches the declared MAC
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

    # Idempotency: if an active cert already exists for this MAC, return it
    existing_cert = (
        db.query(DeviceCertificate)
        .filter(
            DeviceCertificate.mac_address == mac,
            DeviceCertificate.revoked_at.is_(None),
        )
        .first()
    )
    if existing_cert:
        logger.info("MAC %s already enrolled — returning existing cert", mac)
        return SigningResponse(
            cert_pem=existing_cert.cert_pem,
            expires_at=existing_cert.expires_at.isoformat(),
            device_id=existing_cert.esp32_device_id,
            already_enrolled=True,
        )

    # Validate hardware type is registered
    hardware = db.query(Hardware).filter_by(hardware_type=payload.hardware_type).first()
    if hardware is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown hardware type '{payload.hardware_type}' — add it to the Hardware table first",
        )

    # Look up or create the ESP32Device (no owner until customer links it)
    device = db.query(ESP32Device).filter_by(mac_address=mac).first()
    if device is None:
        device = ESP32Device(
            mac_address=mac,
            owner_id=None,
            hardware_id=hardware.id,
            registered_at=datetime.datetime.utcnow(),
        )
        db.add(device)
        db.flush()   # get the auto-generated id
        logger.info("Created new ESP32Device id=%s for MAC %s hardware=%s",
                    device.id, mac, payload.hardware_type)
    elif device.hardware_id is None:
        device.hardware_id = hardware.id

    # Sign the CSR
    cert_pem, serial, fingerprint, subject, expires_at = _sign_csr(
        payload.csr_pem, mac
    )

    # Persist the certificate
    device_cert = DeviceCertificate(
        esp32_device_id=device.id,
        mac_address=mac,
        cert_serial=serial,
        cert_subject=subject,
        cert_fingerprint_sha256=fingerprint,
        cert_pem=cert_pem,
        issued_at=datetime.datetime.utcnow(),
        expires_at=expires_at,
    )
    device.last_connected = datetime.datetime.utcnow()
    db.add(device_cert)
    db.commit()

    logger.info(
        "Issued cert serial=%s fingerprint=%s for device id=%s MAC=%s",
        serial, fingerprint, device.id, mac,
    )

    return SigningResponse(
        cert_pem=cert_pem,
        expires_at=expires_at.isoformat(),
        device_id=device.id,
        already_enrolled=False,
    )
