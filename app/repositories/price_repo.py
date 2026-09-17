from sqlalchemy.orm import Session, joinedload
from app.orm_models.board import BoardType
from app.orm_models.price import PriceVersion, BoardTypePrice


class PriceRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_versions(self) -> list[PriceVersion]:
        # AdminPricesService.list_versions sorts v.prices per version.
        return (
            self.db.query(PriceVersion)
            .options(joinedload(PriceVersion.prices))
            .order_by(PriceVersion.created_at.desc())
            .all()
        )

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

    def commit_and_refresh(self, obj) -> None:
        self.db.commit()
        self.db.refresh(obj)
