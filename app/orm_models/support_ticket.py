from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.orm_models.db import Base


class SupportTicket(Base):
    __tablename__ = "support_ticket"

    id          = Column(Integer, primary_key=True)

    user_id     = Column(Integer, ForeignKey("user.id"), nullable=False)
    user        = relationship("User")

    order_id    = Column(Integer, ForeignKey("orders.id"), nullable=True)
    order       = relationship("Order")

    subject     = Column(String(200), nullable=False)
    message     = Column(Text, nullable=False)
    status      = Column(String(20), nullable=False, default="open")

    admin_reply = Column(Text, nullable=True)
    replied_at  = Column(DateTime, nullable=True)
    archived    = Column(Boolean, nullable=False, default=False)

    created_at  = Column(DateTime, default=datetime.utcnow)
