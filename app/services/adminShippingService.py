from typing import Optional
from sqlalchemy.orm import Session

from app.orm_models.shipping_config import ShippingCountry, ShippingOptionConfig


# ── Enabled shipping option codes ─────────────────────────────────────────────

def get_enabled_codes(db: Session) -> list[str]:
    return [c.option_code for c in db.query(ShippingOptionConfig).order_by(ShippingOptionConfig.option_code).all()]


def save_enabled_codes(db: Session, codes: list[str]) -> list[str]:
    """Replace the enabled set with exactly these codes."""
    unique = list({c.strip() for c in codes if c.strip()})
    db.query(ShippingOptionConfig).delete(synchronize_session=False)
    for code in unique:
        db.add(ShippingOptionConfig(option_code=code))
    db.commit()
    return get_enabled_codes(db)


def get_first_enabled(db: Session) -> Optional[str]:
    row = db.query(ShippingOptionConfig).first()
    return row.option_code if row else None


# ── Allowed shipping countries ─────────────────────────────────────────────────

def list_countries(db: Session) -> list[ShippingCountry]:
    return (
        db.query(ShippingCountry)
        .order_by(ShippingCountry.sort_order, ShippingCountry.country_code)
        .all()
    )


def get_allowed_country_codes(db: Session) -> set[str]:
    return {c.country_code for c in db.query(ShippingCountry).all()}


def save_countries(db: Session, codes: list[str]) -> list[ShippingCountry]:
    upper = [c.strip().upper() for c in codes if c.strip()]
    db.query(ShippingCountry).filter(
        ShippingCountry.country_code.notin_(upper)
    ).delete(synchronize_session=False)

    existing = {c.country_code for c in db.query(ShippingCountry).all()}
    for idx, code in enumerate(upper):
        if code not in existing:
            db.add(ShippingCountry(country_code=code, sort_order=idx))
        else:
            db.query(ShippingCountry).filter_by(country_code=code).update({"sort_order": idx})

    db.commit()
    return list_countries(db)
