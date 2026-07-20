from sqlalchemy.orm import Session, joinedload

from app.orm_models.order import Order
from app.orm_models.support_ticket import SupportTicket


class SupportRepository:
    def __init__(self, db: Session):
        self.db = db

    def _base_query(self):
        return self.db.query(SupportTicket).options(
            joinedload(SupportTicket.user),
            joinedload(SupportTicket.order),
        )

    def create(self, ticket: SupportTicket) -> SupportTicket:
        self.db.add(ticket)
        self.db.commit()
        self.db.refresh(ticket)
        return ticket

    def list_for_user(self, user_id: int) -> list[SupportTicket]:
        return (
            self._base_query()
            .filter(SupportTicket.user_id == user_id)
            .order_by(SupportTicket.created_at.desc())
            .all()
        )

    def list_all(self, status: str | None = None, archived: bool = False) -> list[SupportTicket]:
        q = self._base_query().filter(SupportTicket.archived.is_(archived))
        if status:
            q = q.filter(SupportTicket.status == status)
        return q.order_by(SupportTicket.created_at.desc()).all()

    def count_open_for_user(self, user_id: int) -> int:
        return (
            self.db.query(SupportTicket)
            .filter(SupportTicket.user_id == user_id, SupportTicket.status == "open")
            .count()
        )

    def get_latest_for_user(self, user_id: int) -> SupportTicket | None:
        return (
            self.db.query(SupportTicket)
            .filter(SupportTicket.user_id == user_id)
            .order_by(SupportTicket.created_at.desc())
            .first()
        )

    def get_by_id(self, ticket_id: int) -> SupportTicket | None:
        return self._base_query().filter(SupportTicket.id == ticket_id).first()

    def get_for_user(self, ticket_id: int, user_id: int) -> SupportTicket | None:
        return (
            self._base_query()
            .filter(SupportTicket.id == ticket_id, SupportTicket.user_id == user_id)
            .first()
        )

    def order_belongs_to_user(self, order_id: int, user_id: int) -> bool:
        return (
            self.db.query(Order)
            .filter(Order.id == order_id, Order.user_id == user_id)
            .first()
            is not None
        )

    def save(self, ticket: SupportTicket) -> None:
        self.db.commit()
        self.db.refresh(ticket)
