from typing import Optional

from sqlalchemy.orm import Session

from app.orm_models.order import Order
from app.orm_models.shipping_config import ShippingCountry, ShippingOptionConfig


class ShippingRepository:
    def __init__(self, db: Session):
        self.db = db

    # ── Options ───────────────────────────────────────────────────────────────

    def get_enabled_codes(self) -> list[str]:
        return [
            c.option_code
            for c in self.db.query(ShippingOptionConfig)
            .order_by(ShippingOptionConfig.option_code)
            .all()
        ]

    def save_enabled_codes(self, codes: list[str]) -> list[str]:
        unique = list({c.strip() for c in codes if c.strip()})
        self.db.query(ShippingOptionConfig).delete(synchronize_session=False)
        for code in unique:
            self.db.add(ShippingOptionConfig(option_code=code))
        self.db.commit()
        return self.get_enabled_codes()

    def get_first_enabled(self) -> Optional[str]:
        row = self.db.query(ShippingOptionConfig).first()
        return row.option_code if row else None

    # ── Countries ─────────────────────────────────────────────────────────────

    def list_countries(self) -> list[ShippingCountry]:
        return (
            self.db.query(ShippingCountry)
            .order_by(ShippingCountry.sort_order, ShippingCountry.country_code)
            .all()
        )

    def get_allowed_country_codes(self) -> set[str]:
        return {c.country_code for c in self.db.query(ShippingCountry).all()}

    def save_countries(self, codes: list[str]) -> list[ShippingCountry]:
        upper = [c.strip().upper() for c in codes if c.strip()]
        self.db.query(ShippingCountry).filter(
            ShippingCountry.country_code.notin_(upper)
        ).delete(synchronize_session=False)

        existing = {c.country_code for c in self.db.query(ShippingCountry).all()}
        for idx, code in enumerate(upper):
            if code not in existing:
                self.db.add(ShippingCountry(country_code=code, sort_order=idx))
            else:
                self.db.query(ShippingCountry).filter_by(country_code=code).update(
                    {"sort_order": idx}
                )

        self.db.commit()
        return self.list_countries()

    # ── Orders (for webhook) ──────────────────────────────────────────────────

    def get_order_by_parcel_id(self, parcel_id: str) -> Optional[Order]:
        return (
            self.db.query(Order)
            .filter(Order.sendcloud_parcel_id == parcel_id)
            .first()
        )

    def commit(self) -> None:
        self.db.commit()
