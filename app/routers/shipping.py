import logging
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.orm_models.db import get_db
from app.orm_models.order import Order
from app.orm_models.price import PriceVersion

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/shipping", tags=["shipping"])


@router.get("/rates")
def get_shipping_rates(db: Session = Depends(get_db)):
    """Public endpoint: returns shipping rates from the latest price version."""
    latest = db.query(PriceVersion).order_by(PriceVersion.created_at.desc()).first()
    if not latest or not latest.shipping_rates:
        return []
    return [
        {
            "countryCode":     r.country_code,
            "countryName":     r.country_name,
            "costCents":       r.cost_cents,
            "deliveryDaysMin": r.delivery_days_min,
            "deliveryDaysMax": r.delivery_days_max,
        }
        for r in latest.shipping_rates
    ]


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

    parcel      = data.get("parcel", {})
    parcel_id   = str(parcel.get("id", ""))
    status_id   = (parcel.get("status") or {}).get("id")
    tracking_nr = parcel.get("tracking_number")

    if not parcel_id or status_id is None:
        return {"accepted": True}

    order = db.query(Order).filter(Order.sendcloud_parcel_id == parcel_id).first()
    if not order:
        logger.warning("SendCloud webhook: unknown parcel_id %s", parcel_id)
        return {"accepted": True}

    new_status = sendcloudService.map_sendcloud_status(status_id)
    if new_status:
        order.status = new_status
    if tracking_nr and not order.tracking_number:
        order.tracking_number = tracking_nr

    db.commit()
    logger.info("SendCloud webhook: parcel %s → status %s (order #%s)", parcel_id, status_id, order.id)
    return {"accepted": True}
