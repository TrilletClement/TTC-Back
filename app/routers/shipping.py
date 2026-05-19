from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.orm_models.db import get_db
from app.orm_models.price import PriceVersion

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
