"""
SendCloud REST API v3 client.

Docs: https://sendcloud.dev/api/v3/

Authentication: HTTP Basic — API key as username, API secret as password.
Sandbox:        Set SENDCLOUD_SANDBOX=True to use the free "Unstamped letter" option,
                which creates real parcels that are never charged (no label produced by
                a real carrier). Safe for local dev and testing.
"""
import hashlib
import hmac
import time
import requests
from typing import Optional
from dataclasses import dataclass

from app.core.config import settings

_BASE = "https://panel.sendcloud.sc/api/v3"

# Shipping option codes (v3)
_OPTION_SANDBOX = "sendcloud:letter"          # Free test option, no carrier charge
_OPTION_DEFAULT = "bpost:athome-bpack24hpro"  # bpost @home domestic


def _auth() -> tuple[str, str]:
    return settings.SENDCLOUD_API_KEY, settings.SENDCLOUD_API_SECRET


def _enabled() -> bool:
    return bool(settings.SENDCLOUD_API_KEY and settings.SENDCLOUD_API_SECRET)


def _shipping_option_code() -> str:
    if settings.SENDCLOUD_SANDBOX:
        return _OPTION_SANDBOX
    code = getattr(settings, "SENDCLOUD_SHIPPING_OPTION_CODE", "").strip()
    return code if code else _OPTION_DEFAULT


@dataclass
class ParcelResult:
    parcel_id:       str
    tracking_number: Optional[str]
    label_url:       Optional[str]
    sandbox:         bool = False


def create_parcel(
    *,
    name:        str,
    address:     str,
    city:        str,
    postal_code: str,
    country_iso: str,   # ISO-2 e.g. "BE"
    email:       str,
    telephone:   Optional[str] = None,
    weight_kg:   float = 1.0,
    order_ref:   Optional[str] = None,
) -> ParcelResult:
    """
    Create a parcel via SendCloud API v3 and return the parcel ID + label URL.
    When SENDCLOUD_SANDBOX=True the 'Unstamped letter' option is used —
    a real parcel record is created but no carrier is charged and no delivery happens.
    Raises RuntimeError on configuration or API errors.
    """
    if not _enabled():
        raise RuntimeError(
            "SendCloud is not configured (SENDCLOUD_API_KEY / SENDCLOUD_API_SECRET missing)."
        )

    option_code = _shipping_option_code()

    body: dict = {
        "ship_with": {
            "type": "shipping_option_code",
            "properties": {"shipping_option_code": option_code},
        },
        "to_address": {
            "name":          name,
            "address_line_1": address,
            "city":          city,
            "postal_code":   postal_code,
            "country_code":  country_iso.upper(),
            "email":         email,
        },
        "from_address": {
            "sender_address_id": settings.SENDCLOUD_FROM_ADDRESS_ID,
        },
        "parcels": [
            {"weight": {"value": f"{weight_kg:.3f}", "unit": "kg"}}
        ],
    }
    if telephone:
        body["to_address"]["phone_number"] = telephone
    if order_ref:
        body["external_reference_id"] = order_ref

    resp = requests.post(
        f"{_BASE}/shipments",
        json=body,
        auth=_auth(),
        timeout=15,
    )

    if resp.status_code not in (200, 201):
        try:
            errors = resp.json().get("errors", [])
            detail = "; ".join(e.get("detail", "") for e in errors) if errors else resp.text
        except Exception:
            detail = resp.text
        raise RuntimeError(f"SendCloud API error {resp.status_code}: {detail}")

    data        = resp.json()["data"]
    shipment_id = data.get("id")   # UUID — used only for polling
    parcels     = data.get("parcels", [])
    if not parcels:
        raise RuntimeError("SendCloud API returned a shipment with no parcels.")

    parcel          = parcels[0]
    parcel_id_int   = parcel["id"]            # integer — stored in DB, matched by webhook
    tracking_number = parcel.get("tracking_number") or None

    # Poll up to ~6 s for the carrier to announce the shipment and attach a label.
    label_url, tracking_number = _poll_shipment(
        shipment_id,
        tracking_number,
        max_attempts=4,
        delay=1.5,
    )

    return ParcelResult(
        parcel_id=str(parcel_id_int),
        tracking_number=tracking_number or None,
        label_url=label_url,
        sandbox=settings.SENDCLOUD_SANDBOX,
    )


def _poll_shipment(
    shipment_id: str,
    tracking_number: Optional[str],
    max_attempts: int = 4,
    delay: float = 1.5,
) -> tuple[Optional[str], Optional[str]]:
    """
    Poll the v3 shipment until the first parcel has a label document.
    Returns (label_url, tracking_number) — either may be None if still announcing.
    """
    for attempt in range(max_attempts):
        if attempt > 0:
            time.sleep(delay)
        try:
            r = requests.get(
                f"{_BASE}/shipments/{shipment_id}",
                auth=_auth(),
                timeout=10,
            )
            if r.status_code != 200:
                continue
            data    = r.json().get("data", {})
            parcels = data.get("parcels", [])
            if not parcels:
                continue
            parcel = parcels[0]
            trk    = parcel.get("tracking_number") or tracking_number
            for doc in parcel.get("documents", []):
                if doc.get("type") == "label":
                    return doc.get("link"), trk or None
        except Exception:
            continue
    return None, tracking_number


# ── Webhook signature verification ────────────────────────────────────────────

def verify_webhook(body: bytes, signature_header: str) -> bool:
    """
    Verify an incoming SendCloud webhook signature (HMAC-SHA256).
    If SENDCLOUD_WEBHOOK_SECRET is empty (free plan), verification is skipped.
    """
    if not settings.SENDCLOUD_WEBHOOK_SECRET:
        return True
    expected = hmac.new(
        settings.SENDCLOUD_WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


# ── Webhook status mapping ─────────────────────────────────────────────────────

_STATUS_MAP: dict[int, Optional[str]] = {
    1000: None,         # Ready to send
    1002: "shipped",    # Being sorted / in transit
    3:    "shipped",    # En route to sorting centre
    11:   "delivered",  # Delivered
    12:   "delivered",  # Awaiting customer pickup
    2000: "delivered",  # Shipment delivered
    1998: None,         # No label
    13:   None,         # Return parcel — don't auto-change status
}


def map_sendcloud_status(status_id: int) -> Optional[str]:
    """Return our order status string, or None if no transition should happen."""
    return _STATUS_MAP.get(status_id)
