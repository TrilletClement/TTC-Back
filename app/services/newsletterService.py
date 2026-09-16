import logging
import secrets
from datetime import datetime

from app.core.config import settings
from app.core.mail import send_newsletter_email
from app.domain.exceptions import NotFoundError, ValidationError
from app.orm_models.newsletter import NewsletterSubscriber
from app.repositories.newsletter_repo import NewsletterRepository

logger = logging.getLogger(__name__)


class NewsletterService:
    def __init__(self, repo: NewsletterRepository):
        self.repo = repo

    def subscribe(self, email: str, user_id: int | None, source: str) -> NewsletterSubscriber:
        email = email.strip().lower()
        existing = self.repo.get_by_email(email)
        if existing:
            if existing.unsubscribed_at is not None:
                existing.unsubscribed_at = None
                if user_id and not existing.user_id:
                    existing.user_id = user_id
                self.repo.commit()
            return existing

        subscriber = NewsletterSubscriber(
            email=email,
            user_id=user_id,
            source=source,
            unsubscribe_token=secrets.token_urlsafe(32),
        )
        return self.repo.save(subscriber)

    def unsubscribe(self, token: str) -> dict:
        subscriber = self.repo.get_by_token(token)
        if not subscriber:
            raise ValidationError("invalid-token")
        subscriber.unsubscribed_at = datetime.utcnow()
        self.repo.commit()
        return {"status": "unsubscribed"}

    def list_subscribers(self) -> list[NewsletterSubscriber]:
        return self.repo.list_active()

    def remove_subscriber(self, subscriber_id: int) -> None:
        subscriber = self.repo.get_by_id(subscriber_id)
        if not subscriber:
            raise NotFoundError("Subscriber", subscriber_id)
        self.repo.delete(subscriber)

    async def send_campaign(self, subject: str, body_html: str) -> dict:
        subscribers = self.repo.list_active()
        sent = 0
        for sub in subscribers:
            unsubscribe_url = f"{settings.FRONTEND_URL}/newsletter/unsubscribe?token={sub.unsubscribe_token}"
            try:
                await send_newsletter_email(sub.email, subject, body_html, unsubscribe_url)
                sent += 1
            except Exception as mail_err:
                logger.warning(f"Newsletter send failed for {sub.email}: {mail_err}")
        logger.info(f"Newsletter campaign sent: {sent}/{len(subscribers)}")
        return {"sent": sent, "total": len(subscribers)}
