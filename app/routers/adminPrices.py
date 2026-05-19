from typing import List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.user_access import require_admin
from app.orm_models.auth import User
from app.orm_models.db import get_db
from app.orm_models.board import BoardType
from app.orm_models.price import BoardTypePrice, PriceVersion, ShippingRate

router = APIRouter(prefix="/api/admin/price-versions", tags=["admin-prices"])


class PriceEntryIn(BaseModel):
    board_type_id: int
    base_price_cents: int
    reduced_price_cents: int


class ShippingRateIn(BaseModel):
    country_code:      str
    country_name:      str
    cost_cents:        int
    delivery_days_min: int
    delivery_days_max: int


class PriceVersionCreate(BaseModel):
    label:    Optional[str] = None
    prices:   List[PriceEntryIn]
    shipping: List[ShippingRateIn] = []


@router.get("")
@require_admin
def list_price_versions(current_user: User, db: Session = Depends(get_db)):
    versions = db.query(PriceVersion).order_by(PriceVersion.created_at.desc()).all()
    board_types = {bt.id: bt.name for bt in db.query(BoardType).all()}

    latest_id = versions[0].id if versions else None

    return [
        {
            "id": v.id,
            "label": v.label,
            "createdAt": v.created_at.isoformat(),
            "isCurrent": v.id == latest_id,
            "prices": [
                {
                    "boardTypeId": p.board_type_id,
                    "boardTypeName": board_types.get(p.board_type_id, f"Type {p.board_type_id}"),
                    "basePriceCents": p.base_price_cents,
                    "reducedPriceCents": p.reduced_price_cents,
                }
                for p in sorted(v.prices, key=lambda p: p.board_type_id)
            ],
            "shippingRates": [
                {
                    "countryCode":     r.country_code,
                    "countryName":     r.country_name,
                    "costCents":       r.cost_cents,
                    "deliveryDaysMin": r.delivery_days_min,
                    "deliveryDaysMax": r.delivery_days_max,
                }
                for r in v.shipping_rates
            ],
        }
        for v in versions
    ]


@router.post("", status_code=201)
@require_admin
def create_price_version(payload: PriceVersionCreate, current_user: User, db: Session = Depends(get_db)):
    version = PriceVersion(label=payload.label or None)
    db.add(version)
    db.flush()

    for entry in payload.prices:
        db.add(BoardTypePrice(
            price_version_id=version.id,
            board_type_id=entry.board_type_id,
            base_price_cents=entry.base_price_cents,
            reduced_price_cents=entry.reduced_price_cents,
        ))

    for rate in payload.shipping:
        db.add(ShippingRate(
            price_version_id=version.id,
            country_code=rate.country_code.upper().strip(),
            country_name=rate.country_name.strip(),
            cost_cents=rate.cost_cents,
            delivery_days_min=rate.delivery_days_min,
            delivery_days_max=rate.delivery_days_max,
        ))

    db.commit()
    db.refresh(version)
    return {"id": version.id, "label": version.label, "createdAt": version.created_at.isoformat()}
