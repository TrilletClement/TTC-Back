from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.user_access import require_admin
from app.orm_models.db import get_db
from app.services import sendcloudService, adminShippingService

router = APIRouter(prefix="/api/admin/shipping", tags=["admin-shipping"])


# ── Option endpoints ───────────────────────────────────────────────────────────

@router.get("/available")
@require_admin
def get_available_options(
    country_code: str = Query(...),
    db: Session = Depends(get_db),
):
    """
    Fetch all home-delivery options from SendCloud for a given country.
    Returns each option with a flag indicating whether it is currently enabled.
    """
    enabled = set(adminShippingService.get_enabled_codes(db))
    options = sendcloudService.get_shipping_options(country_code)
    for opt in options:
        opt["enabled"] = opt["code"] in enabled
    return options


@router.get("/configs")
@require_admin
def get_configs(db: Session = Depends(get_db)) -> list[str]:
    return adminShippingService.get_enabled_codes(db)


@router.put("/configs")
@require_admin
def save_configs(codes: list[str], db: Session = Depends(get_db)) -> list[str]:
    return adminShippingService.save_enabled_codes(db, codes)


# ── Country endpoints ──────────────────────────────────────────────────────────

class CountryOut(BaseModel):
    country_code: str
    sort_order:   int

    class Config:
        from_attributes = True


@router.get("/countries", response_model=list[CountryOut])
@require_admin
def get_countries(db: Session = Depends(get_db)):
    return adminShippingService.list_countries(db)


@router.put("/countries", response_model=list[CountryOut])
@require_admin
def save_countries(codes: list[str], db: Session = Depends(get_db)):
    return adminShippingService.save_countries(db, codes)
