import logging
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.mail import send_support_ticket_alert
from app.orm_models.support_ticket import SupportTicket
from app.repositories.support_repo import SupportRepository

log = logging.getLogger(__name__)

# Anti-harassment guard rails — keep a single support inbox from being flooded.
TICKET_COOLDOWN_SECONDS   = 60
MAX_OPEN_TICKETS_PER_USER = 5


def _ticket_out(t: SupportTicket) -> dict:
    return {
        "id":          t.id,
        "subject":     t.subject,
        "message":     t.message,
        "status":      t.status,
        "admin_reply": t.admin_reply,
        "replied_at":  t.replied_at,
        "created_at":  t.created_at,
        "order_id":    t.order_id,
        "order_ref":   t.order.cart_ref or f"#{t.order.id}" if t.order else None,
    }


class SupportService:

    @staticmethod
    async def create_ticket(payload, user_id: int, user_email: str, db: Session) -> dict:
        subject = payload.subject.strip()
        message = payload.message.strip()
        if not subject or not message:
            raise HTTPException(status_code=400, detail="Subject and message are required")

        repo = SupportRepository(db)

        latest = repo.get_latest_for_user(user_id)
        if latest and latest.created_at:
            elapsed = (datetime.utcnow() - latest.created_at).total_seconds()
            if elapsed < TICKET_COOLDOWN_SECONDS:
                raise HTTPException(
                    status_code=429,
                    detail="Please wait a moment before sending another message.",
                )

        if repo.count_open_for_user(user_id) >= MAX_OPEN_TICKETS_PER_USER:
            raise HTTPException(
                status_code=400,
                detail="You already have several open requests awaiting a reply — "
                       "please wait for those to be answered before sending more.",
            )

        if payload.order_id is not None and not repo.order_belongs_to_user(payload.order_id, user_id):
            raise HTTPException(status_code=404, detail="Order not found")

        ticket = repo.create(SupportTicket(
            user_id  = user_id,
            order_id = payload.order_id,
            subject  = subject,
            message  = message,
        ))

        try:
            await send_support_ticket_alert(
                ticket.id, subject, message, user_email,
                ticket.order.cart_ref or f"#{ticket.order.id}" if ticket.order else None,
            )
        except Exception:
            log.exception("Failed to send support ticket alert for ticket %s", ticket.id)

        return _ticket_out(ticket)

    @staticmethod
    def list_my_tickets(user_id: int, db: Session) -> list[dict]:
        repo = SupportRepository(db)
        return [_ticket_out(t) for t in repo.list_for_user(user_id)]
