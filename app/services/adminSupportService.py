import logging
from datetime import datetime
from typing import Optional

from app.core.mail import send_support_reply
from app.domain.exceptions import NotFoundError, BusinessError, ValidationError
from app.orm_models.support_ticket import SupportTicket
from app.repositories.support_repo import SupportRepository
from app.schemas.support import AdminTicketOut, TicketReply

log = logging.getLogger(__name__)

TICKET_STATUSES = {"open", "resolved"}


def _ticket_out(t: SupportTicket) -> AdminTicketOut:
    return AdminTicketOut(
        id=t.id,
        subject=t.subject,
        message=t.message,
        status=t.status,
        admin_reply=t.admin_reply,
        replied_at=t.replied_at,
        created_at=t.created_at,
        order_id=t.order_id,
        order_ref=(t.order.cart_ref or f"#{t.order.id}") if t.order else None,
        user_email=t.user.email if t.user else None,
        archived=t.archived,
    )


class AdminSupportService:
    def __init__(self, repo: SupportRepository):
        self.repo = repo

    def list_tickets(
        self, status: Optional[str], search: Optional[str], archived: bool = False,
    ) -> list[AdminTicketOut]:
        if status and status not in TICKET_STATUSES:
            raise ValidationError(f"Invalid status. Allowed: {TICKET_STATUSES}")
        tickets = self.repo.list_all(status, archived)

        if search:
            s = search.strip().lower()
            tickets = [
                t for t in tickets
                if s in (t.user.email or "").lower()
                or s in t.subject.lower()
                or s in str(t.id)
            ]

        return [_ticket_out(t) for t in tickets]

    def get_ticket(self, ticket_id: int) -> AdminTicketOut:
        t = self.repo.get_by_id(ticket_id)
        if not t:
            raise NotFoundError("SupportTicket", ticket_id)
        return _ticket_out(t)

    def archive(self, ticket_id: int) -> AdminTicketOut:
        t = self.repo.get_by_id(ticket_id)
        if not t:
            raise NotFoundError("SupportTicket", ticket_id)
        if t.status != "resolved":
            raise BusinessError("Only resolved tickets can be archived.")

        t.archived = True
        self.repo.save(t)
        return _ticket_out(t)

    async def reply(self, ticket_id: int, payload: TicketReply) -> AdminTicketOut:
        t = self.repo.get_by_id(ticket_id)
        if not t:
            raise NotFoundError("SupportTicket", ticket_id)

        reply_text = payload.message.strip()
        if not reply_text:
            raise ValidationError("Reply message is required")

        t.admin_reply = reply_text
        t.replied_at  = datetime.utcnow()
        t.status      = "resolved" if payload.resolve else "open"
        self.repo.save(t)

        if t.user:
            try:
                await send_support_reply(t.user.email, t.subject, reply_text)
            except Exception:
                log.exception("Failed to send support reply email for ticket %s", t.id)

        return _ticket_out(t)
