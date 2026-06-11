"""
SendCloud REST API v3 client.
Docs: https://sendcloud.dev/api/v3/
Authentication: HTTP Basic — API key as username, API secret as password.
"""
import hashlib
import hmac
import time
import requests
from typing import Optional
from dataclasses import dataclass

from app.core.config import settings

_BASE = "https://panel.sendcloud.sc/api/v3"

_FROM_COUNTRY = "BE"
_FROM_POSTAL  = "4020"


def _auth() -> tuple[str, str]:
    return settings.SENDCLOUD_API_KEY, settings.SENDCLOUD_API_SECRET


def _enabled() -> bool:
    return bool(settings.SENDCLOUD_API_KEY and settings.SENDCLOUD_API_SECRET)


def get_shipping_options(
    to_country_code: str,
    to_postal_code: str = "",
    weight_kg: float = 1.0,
) -> list[dict]:
    """
    Return all home-delivery shipping options with live prices from SendCloud.
    Does NOT apply the admin allowlist — callers are responsible for filtering.
    Filters out service-point-required and pure-B2B options as a baseline.
    """
    if not _enabled():
        return []

    body: dict = {
        "from_country_code": _FROM_COUNTRY,
        "from_postal_code":  _FROM_POSTAL,
        "to_country_code":   to_country_code.upper(),
        "parcels": [{"weight": {"value": f"{weight_kg:.3f}", "unit": "kg"}}],
        "calculate_quotes":  True,
    }
    if to_postal_code:
        body["to_postal_code"] = to_postal_code

    try:
        resp = requests.post(
            f"{_BASE}/shipping-options",
            json=body,
            auth=_auth(),
            timeout=10,
        )
        if resp.status_code != 200:
            return []

        result = []
        for opt in resp.json().get("data", []):
            code  = opt.get("code", "")
            req   = opt.get("requirements", {})
            funcs = opt.get("functionalities", {})
            if req.get("is_service_point_required"):
                continue
            if funcs.get("b2b") and not funcs.get("b2c"):
                continue

            quotes = opt.get("quotes", [])
            price_cents: Optional[int] = None
            currency = "EUR"
            if quotes:
                total = quotes[0].get("price", {}).get("total", {})
                price_str = total.get("value")
                currency  = total.get("currency", "EUR")
                if price_str is not None:
                    try:
                        price_cents = round(float(price_str) * 100)
                    except (ValueError, TypeError):
                        pass

            result.append({
                "code":         code,
                "name":         opt.get("name", code),
                "carrier_code": opt.get("carrier", {}).get("code", ""),
                "carrier_name": opt.get("carrier", {}).get("name", ""),
                "price_cents":  price_cents,
                "currency":     currency,
            })

        return sorted(result, key=lambda x: x["price_cents"] or 99_999)
    except Exception:
        return []


def get_option_price_cents(
    option_code: str,
    to_country_code: str,
    to_postal_code: str = "",
    weight_kg: float = 1.0,
) -> Optional[int]:
    """Return price in cents for a specific option code, or None if not found."""
    for opt in get_shipping_options(to_country_code, to_postal_code, weight_kg):
        if opt["code"] == option_code:
            return opt["price_cents"]
    return None


@dataclass
class ParcelResult:
    parcel_id:       str
    tracking_number: Optional[str]
    label_url:       Optional[str]
    tracking_url:    Optional[str] = None


def create_parcel(
    *,
    name:                 str,
    address:              str,
    city:                 str,
    postal_code:          str,
    country_iso:          str,
    email:                str,
    telephone:            Optional[str] = None,
    weight_kg:            float = 1.0,
    order_ref:            Optional[str] = None,
    shipping_option_code: str,
) -> ParcelResult:
    """
    Create a parcel via SendCloud API v3 and return the parcel ID + label URL.
    shipping_option_code is required — use the admin-configured code for the order.
    """
    if not _enabled():
        raise RuntimeError(
            "SendCloud is not configured (SENDCLOUD_API_KEY / SENDCLOUD_API_SECRET missing)."
        )
    if not shipping_option_code:
        raise RuntimeError(
            "No shipping option code provided. Configure one in the admin shipping panel."
        )

    body: dict = {
        "ship_with": {
            "type": "shipping_option_code",
            "properties": {"shipping_option_code": shipping_option_code},
        },
        "to_address": {
            "name":           name,
            "address_line_1": address,
            "city":           city,
            "postal_code":    postal_code,
            "country_code":   country_iso.upper(),
            "email":          email,
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
    shipment_id = data.get("id")
    parcels     = data.get("parcels", [])
    if not parcels:
        raise RuntimeError("SendCloud API returned a shipment with no parcels.")

    parcel          = parcels[0]
    parcel_id_int   = parcel["id"]
    tracking_number = parcel.get("tracking_number") or None

    label_url, tracking_number, tracking_url = _poll_shipment(
        shipment_id,
        tracking_number,
        max_attempts=4,
        delay=1.5,
    )

    return ParcelResult(
        parcel_id=str(parcel_id_int),
        tracking_number=tracking_number or None,
        label_url=label_url,
        tracking_url=tracking_url,
    )


def _poll_shipment(
    shipment_id: str,
    tracking_number: Optional[str],
    max_attempts: int = 4,
    delay: float = 1.5,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Poll for label attachment. Returns (label_url, tracking_number, tracking_url)."""
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
            parcel       = parcels[0]
            trk          = parcel.get("tracking_number") or tracking_number
            tracking_url = parcel.get("tracking_url") or None
            for doc in parcel.get("documents", []):
                if doc.get("type") == "label":
                    return doc.get("link"), trk or None, tracking_url
        except Exception:
            continue
    return None, tracking_number, None


# ── Webhook signature verification ────────────────────────────────────────────

def verify_webhook(body: bytes, signature_header: str) -> bool:
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
    1000: None,
    1002: "shipped",
    3:    "shipped",
    11:   "delivered",
    12:   "delivered",
    2000: "delivered",
    1998: None,
    13:   None,
}


def map_sendcloud_status(status_id: int) -> Optional[str]:
    return _STATUS_MAP.get(status_id)
