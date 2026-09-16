from sqlalchemy.orm import Session

from app.orm_models.newsletter import NewsletterSubscriber


class NewsletterRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_email(self, email: str) -> NewsletterSubscriber | None:
        return self.db.query(NewsletterSubscriber).filter(NewsletterSubscriber.email == email).first()

    def get_by_token(self, token: str) -> NewsletterSubscriber | None:
        return self.db.query(NewsletterSubscriber).filter(NewsletterSubscriber.unsubscribe_token == token).first()

    def get_by_id(self, subscriber_id: int) -> NewsletterSubscriber | None:
        return self.db.query(NewsletterSubscriber).filter(NewsletterSubscriber.id == subscriber_id).first()

    def list_active(self) -> list[NewsletterSubscriber]:
        return (
            self.db.query(NewsletterSubscriber)
            .filter(NewsletterSubscriber.unsubscribed_at.is_(None))
            .order_by(NewsletterSubscriber.subscribed_at.desc())
            .all()
        )

    def save(self, subscriber: NewsletterSubscriber) -> NewsletterSubscriber:
        self.db.add(subscriber)
        self.db.commit()
        self.db.refresh(subscriber)
        return subscriber

    def delete(self, subscriber: NewsletterSubscriber) -> None:
        self.db.delete(subscriber)
        self.db.commit()

    def commit(self) -> None:
        self.db.commit()
