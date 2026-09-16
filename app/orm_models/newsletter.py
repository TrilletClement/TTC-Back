from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from app.orm_models.db import Base


class NewsletterSubscriber(Base):
    __tablename__ = "newsletter_subscriber"

    id                = Column(Integer, primary_key=True)
    email             = Column(String(120), unique=True, nullable=False, index=True)
    user_id           = Column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    source            = Column(String(30), nullable=False)
    unsubscribe_token = Column(String(100), unique=True, nullable=False)
    subscribed_at     = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    unsubscribed_at   = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User")
