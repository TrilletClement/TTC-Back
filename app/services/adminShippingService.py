from typing import Optional

from sqlalchemy.orm import Session

from app.orm_models.shipping_config import ShippingCountry
from app.repositories.shipping_repo import ShippingRepository


# ── Module-level helpers (keep existing call-sites working) ───────────────────

def get_enabled_codes(db: Session) -> list[str]:
    return ShippingRepository(db).get_enabled_codes()


def save_enabled_codes(db: Session, codes: list[str]) -> list[str]:
    return ShippingRepository(db).save_enabled_codes(codes)


def get_first_enabled(db: Session) -> Optional[str]:
    return ShippingRepository(db).get_first_enabled()


def list_countries(db: Session) -> list[ShippingCountry]:
    return ShippingRepository(db).list_countries()


def get_allowed_country_codes(db: Session) -> set[str]:
    return ShippingRepository(db).get_allowed_country_codes()


def save_countries(db: Session, codes: list[str]) -> list[ShippingCountry]:
    return ShippingRepository(db).save_countries(codes)
