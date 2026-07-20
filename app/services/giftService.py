import logging
from datetime import datetime

from app.core.config import settings
from app.core.mail import send_gift_email
from app.domain.exceptions import BusinessError, ValidationError
from app.orm_models.auth import User
from app.orm_models.order import Order
from app.repositories.order_repo import OrderRepository
from app.services.naming import unique_name

log = logging.getLogger(__name__)


class GiftService:
    def __init__(self, repo: OrderRepository):
        self.repo = repo

    def _status(self, gift) -> str:
        if gift.claimed_at:
            return "claimed"
        if gift.claim_token_expiry and gift.claim_token_expiry < datetime.utcnow():
            return "expired"
        return "pending"

    def get_claim_info(self, token: str) -> dict:
        gift = self.repo.get_gift_by_token(token)
        if not gift:
            raise ValidationError("invalid-token")

        order = gift.order
        first_board_name = next((i.board.name for i in order.items if i.board), None)

        return {
            "recipient_name":   gift.recipient_name,
            "buyer_email":      order.user.email if order.user else None,
            "message":          gift.message,
            "item_count":       len(order.items),
            "first_board_name": first_board_name,
            "status":           self._status(gift),
        }

    def claim_gift(self, token: str, current_user: User) -> dict:
        gift = self.repo.get_gift_by_token(token)
        if not gift:
            raise ValidationError("invalid-token")

        status = self._status(gift)
        if status != "pending":
            raise ValidationError(status)

        gift.claimed_at         = datetime.utcnow()
        gift.claimed_by_user_id = current_user.id

        order = gift.order
        for item in order.items:
            if item.board:
                existing = self.repo.get_board_names_for_owner(current_user.id, item.board.id)
                item.board.name      = unique_name(item.board.name, existing)
                item.board.owner_id  = current_user.id
            if item.esp_device:
                existing = self.repo.get_device_names_for_owner(current_user.id, item.esp_device.id)
                item.esp_device.name     = unique_name(item.esp_device.name or "Display", existing)
                item.esp_device.owner_id = current_user.id

        self.repo.save(order)
        return {"status": "claimed"}

    async def update_gift_fields(self, order: Order, payload) -> dict:
        if not order.gift:
            raise BusinessError("This order is not a gift")
        if order.gift.claimed_at:
            raise BusinessError("This gift has already been accepted and can no longer be edited")

        gift = order.gift
        if payload.recipient_name is not None:
            gift.recipient_name = payload.recipient_name.strip()
        if payload.recipient_email is not None:
            gift.recipient_email = payload.recipient_email.strip()
        if payload.message is not None:
            gift.message = payload.message.strip() or None

        if not gift.recipient_name or not gift.recipient_email:
            raise ValidationError("Recipient name and email are required")

        self.repo.save(order)

        resent = False
        if gift.claim_token:
            claim_url = f"{settings.FRONTEND_URL.rstrip('/')}/gift/claim?token={gift.claim_token}"
            try:
                await send_gift_email(
                    gift.recipient_email, gift.recipient_name,
                    order.user.email if order.user else "", gift.message, claim_url,
                )
                resent = True
            except Exception:
                log.exception("Failed to resend gift email for order %s", order.id)

        return {
            "recipient_name":  gift.recipient_name,
            "recipient_email": gift.recipient_email,
            "message":         gift.message,
            "claimed":         False,
            "resent":          resent,
        }
