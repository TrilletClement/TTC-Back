"""Business logic for device CSR signing and enrollment."""

import datetime
import logging

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.orm_models.device import ESP32Device
from app.orm_models.device_certificate import DeviceCertificate
from app.repositories.provisioning_repo import ProvisioningRepository

logger = logging.getLogger(__name__)

CERT_VALIDITY_DAYS = 5 * 365


# ── CA helpers (pure crypto, no DB) ──────────────────────────────────────────

def _load_ca():
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

    now        = datetime.datetime.utcnow()
    expires_at = now + datetime.timedelta(days=CERT_VALIDITY_DAYS)
    serial     = x509.random_serial_number()

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
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=False,
                crl_sign=False, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
        .sign(ca_key, hashes.SHA256())
    )

    cert_pem    = cert.public_bytes(serialization.Encoding.PEM).decode()
    fingerprint = cert.fingerprint(hashes.SHA256()).hex().upper()
    subject     = cert.subject.rfc4514_string()

    return cert_pem, serial, fingerprint, subject, expires_at


# ── Service ───────────────────────────────────────────────────────────────────

class ProvisioningService:

    @staticmethod
    def sign_device_csr(mac: str, hardware_type: str, csr_pem: str, db: Session) -> dict:
        repo = ProvisioningRepository(db)

        # Idempotency check
        existing = repo.get_active_cert_by_mac(mac)
        if existing:
            try:
                existing_x509 = x509.load_pem_x509_certificate(existing.cert_pem.encode())
                csr = x509.load_pem_x509_csr(csr_pem.encode())
                same_key = (
                    existing_x509.public_key().public_bytes(
                        serialization.Encoding.PEM,
                        serialization.PublicFormat.SubjectPublicKeyInfo,
                    )
                    == csr.public_key().public_bytes(
                        serialization.Encoding.PEM,
                        serialization.PublicFormat.SubjectPublicKeyInfo,
                    )
                )
            except Exception:
                same_key = False

            if same_key:
                logger.info("MAC %s already enrolled with same key — returning existing cert", mac)
                return {
                    "cert_pem":        existing.cert_pem,
                    "expires_at":      existing.expires_at.isoformat(),
                    "device_id":       existing.esp32_device_id,
                    "already_enrolled": True,
                }

            logger.info(
                "MAC %s submitted new public key — revoking old cert serial=%s",
                mac, existing.cert_serial,
            )
            repo.revoke_cert(existing, "key_replacement")

        # Validate hardware type
        hardware = repo.get_hardware_by_type(hardware_type)
        if hardware is None:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown hardware type '{hardware_type}' — add it to the Hardware table first",
            )

        # Look up or create the device
        device = repo.get_device_by_mac(mac)
        if device is None:
            device = repo.create_device(ESP32Device(
                mac_address=mac,
                owner_id=None,
                hardware_id=hardware.id,
                registered_at=datetime.datetime.utcnow(),
            ))
            logger.info("Created new ESP32Device id=%s for MAC %s hardware=%s", device.id, mac, hardware_type)
        elif device.hardware_id is None:
            device.hardware_id = hardware.id

        # Sign
        cert_pem, serial, fingerprint, subject, expires_at = _sign_csr(csr_pem, mac)

        # Persist
        device.last_connected = datetime.datetime.utcnow()
        repo.create_cert(DeviceCertificate(
            esp32_device_id       = device.id,
            mac_address           = mac,
            cert_serial           = serial,
            cert_subject          = subject,
            cert_fingerprint_sha256 = fingerprint,
            cert_pem              = cert_pem,
            issued_at             = datetime.datetime.utcnow(),
            expires_at            = expires_at,
        ))
        repo.commit()

        logger.info(
            "Issued cert serial=%s fingerprint=%s for device id=%s MAC=%s",
            serial, fingerprint, device.id, mac,
        )

        return {
            "cert_pem":        cert_pem,
            "expires_at":      expires_at.isoformat(),
            "device_id":       device.id,
            "already_enrolled": False,
        }
