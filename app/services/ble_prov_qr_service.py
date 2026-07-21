"""
BLE WiFi provisioning QR code generation.

Reproduces the exact same service name + Proof-of-Possession (POP) derivation
the ESP firmware computes itself at boot (derive_prov_identity() in esp-base's
wifi_manager.cpp), and that scripts/gen_prov_qr.py in stib-display-private
already mirrors for manufacturing-time QR stickers.

KEEP THIS FORMULA IN SYNC WITH BOTH OF THOSE — three independent
implementations of the same algorithm with no automated check that they
agree. Any change here without mirroring it there produces labels whose QR
codes silently don't work.

This module only derives the identity and renders the QR image — it knows
nothing about PDFs, legal text, or label layout (see device_label_service.py
for that).
"""

import hashlib
import json
from io import BytesIO

import qrcode

POP_BYTES = 8


def derive_identity(mac_bytes: bytes, prefix: str, salt: str, pop_bytes: int = POP_BYTES) -> tuple[str, str]:
    """Returns (service_name, pop). Exact port of derive() in gen_prov_qr.py."""
    # Last 2 raw bytes, uppercase hex, no separator — must match
    # derive_prov_identity()'s "%02X%02X" formatting exactly.
    suffix = mac_bytes[-2:].hex().upper()
    service_name = f"{prefix}-{suffix}"

    digest = hashlib.sha256(mac_bytes + salt.encode("ascii")).digest()
    pop = digest[:pop_bytes].hex()  # lowercase hex, matches "%02x" formatting

    return service_name, pop


def build_provisioning_qr(mac_address: str, prefix: str, salt: str) -> tuple[bytes, str, str]:
    """Returns (qr_png_bytes, service_name, pop) for the given MAC (colon-separated,
    e.g. "aa:bb:cc:dd:ee:ff") and this hardware type's BLE provisioning identity."""
    mac_bytes = bytes.fromhex(mac_address.replace(":", ""))
    service_name, pop = derive_identity(mac_bytes, prefix, salt)

    # Key order matches gen_prov_qr.py exactly (ver, name, pop, transport).
    payload = json.dumps({
        "ver": "v1",
        "name": service_name,
        "pop": pop,
        "transport": "ble",
    })

    buf = BytesIO()
    qrcode.make(payload).save(buf, format="PNG")
    return buf.getvalue(), service_name, pop
