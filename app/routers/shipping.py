import logging
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.orm_models.db import get_db
from app.repositories.shipping_repo import ShippingRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/shipping", tags=["shipping"])

_KG_PER_ITEM = 0.5


@router.get("/countries")
def get_shipping_countries(db: Session = Depends(get_db)):
    """Public endpoint: ISO-2 country codes the store ships to."""
    from app.services.adminShippingService import list_countries
    return [c.country_code for c in list_countries(db)]


@router.get("/options")
def get_shipping_options(
    country_code: str = Query(...),
    item_count:   int = Query(default=1, ge=1),
    db: Session = Depends(get_db),
):
    """
    Public endpoint: admin-allowed SendCloud options for a given country.
    Returns [] when the country is not in the allowed list or SendCloud is not configured.
    """
    from app.services import sendcloudService, adminShippingService

    cc = country_code.upper()

    if cc not in adminShippingService.get_allowed_country_codes(db):
        return []

    if not sendcloudService._enabled():
        return []

    allowed = set(adminShippingService.get_enabled_codes(db))
    if not allowed:
        return []

    weight_kg   = item_count * _KG_PER_ITEM
    all_options = sendcloudService.get_shipping_options(cc, weight_kg=weight_kg)
    filtered    = [o for o in all_options if o["code"] in allowed]
    filtered.sort(key=lambda x: x["price_cents"] or 99_999)
    return filtered


# ── SendCloud webhook ──────────────────────────────────────────────────────────

@router.post("/webhook/sendcloud")
async def sendcloud_webhook(
    request: Request,
    db: Session = Depends(get_db),
    sendcloud_signature: str = Header(default=""),
):
    """
    Receives parcel status updates from SendCloud.
    Configure the URL in SendCloud panel → Settings → Integrations → Webhooks:
      https://transport.trillet.be/api/shipping/webhook/sendcloud
    """
    from app.services import sendcloudService

    body = await request.body()

    if not sendcloudService.verify_webhook(body, sendcloud_signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    action = data.get("action")
    if action != "parcel_status_changed":
        return {"accepted": True, "action": action}

    parcel       = data.get("parcel", {})
    parcel_id    = str(parcel.get("id", ""))
    status_id    = (parcel.get("status") or {}).get("id")
    tracking_nr  = parcel.get("tracking_number")
    tracking_url = parcel.get("tracking_url")

    label_obj = parcel.get("label") or {}
    label_url = (
        label_obj.get("label_printer")
        or (label_obj.get("normal_printer") or [None])[0]
    )

    logger.info(
        "SendCloud webhook: parcel=%s status=%s tracking=%s tracking_url=%s label=%s",
        parcel_id, status_id, tracking_nr, tracking_url, label_url,
    )

    if not parcel_id or status_id is None:
        return {"accepted": True}

    repo = ShippingRepository(db)
    order = repo.get_order_by_parcel_id(parcel_id)
    if not order:
        logger.warning("SendCloud webhook: unknown parcel_id %s", parcel_id)
        return {"accepted": True}

    new_status = sendcloudService.map_sendcloud_status(status_id)
    if new_status:
        order.status = new_status
    if tracking_nr and not order.tracking_number:
        order.tracking_number = tracking_nr
    if tracking_url:
        order.tracking_url = tracking_url
    if label_url and not order.label_url:
        order.label_url = label_url

    repo.commit()
    logger.info("SendCloud webhook: parcel %s → status %s (order #%s)", parcel_id, status_id, order.id)
    return {"accepted": True}
