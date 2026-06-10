from sqlalchemy.orm import Session
from app.orm_models.board import BoardType
from app.orm_models.price import PriceVersion, BoardTypePrice, ShippingRate


class PriceRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_versions(self) -> list[PriceVersion]:
        return self.db.query(PriceVersion).order_by(PriceVersion.created_at.desc()).all()

    def get_board_types(self) -> dict[int, str]:
        return {bt.id: bt.name for bt in self.db.query(BoardType).all()}

    def create_version(self, label: str | None) -> PriceVersion:
        version = PriceVersion(label=label)
        self.db.add(version)
        self.db.flush()
        return version

    def add_price_entry(self, version_id: int, board_type_id: int, base: int, reduced: int) -> None:
        self.db.add(BoardTypePrice(
            price_version_id=version_id,
            board_type_id=board_type_id,
            base_price_cents=base,
            reduced_price_cents=reduced,
        ))

    def add_shipping_rate(self, version_id: int, country_code: str, country_name: str, cost: int, days_min: int, days_max: int) -> None:
        self.db.add(ShippingRate(
            price_version_id=version_id,
            country_code=country_code.upper().strip(),
            country_name=country_name.strip(),
            cost_cents=cost,
            delivery_days_min=days_min,
            delivery_days_max=days_max,
        ))

    def commit_and_refresh(self, obj) -> None:
        self.db.commit()
        self.db.refresh(obj)