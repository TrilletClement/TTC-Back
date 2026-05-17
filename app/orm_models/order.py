from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from app.orm_models.db import Base


class OrderDetails(Base):
    __tablename__ = "order_details"

    id            = Column(Integer, primary_key=True)

    user_id       = Column(Integer, ForeignKey("user.id"), nullable=False)
    user          = relationship("User", backref="order_details")

    first_name    = Column(String(100), nullable=False)
    last_name     = Column(String(100), nullable=False)
    phone         = Column(String(30),  nullable=True)
    address_line1 = Column(String(255), nullable=False)
    city          = Column(String(100), nullable=False)
    postal_code   = Column(String(20),  nullable=False)
    country       = Column(String(100), nullable=False)

    created_at    = Column(DateTime, default=datetime.utcnow)

    shipped_orders = relationship(
        "Order",
        foreign_keys="[Order.shipping_details_id]",
        back_populates="shipping_details",
    )


class Order(Base):
    __tablename__ = "orders"

    id                  = Column(Integer, primary_key=True)
    stripe_session_id   = Column(String(255), nullable=True)
    status              = Column(String(50), default="pending", nullable=False)
    # pending | paid | cancelled

    board_id            = Column(Integer, ForeignKey("board.id"), nullable=True)
    board               = relationship("Board", backref="orders")

    user_id             = Column(Integer, ForeignKey("user.id"), nullable=False)
    user                = relationship("User", backref="orders")

    shipping_details_id = Column(Integer, ForeignKey("order_details.id"), nullable=True)
    shipping_details    = relationship(
        "OrderDetails",
        foreign_keys=[shipping_details_id],
        back_populates="shipped_orders",
    )

    billing_details_id  = Column(Integer, ForeignKey("order_details.id"), nullable=True)
    billing_details     = relationship(
        "OrderDetails",
        foreign_keys=[billing_details_id],
    )

    price_version_id    = Column(Integer, ForeignKey("price_version.id"), nullable=True)

    svg_content         = Column(Text, nullable=True)
    tracking_number     = Column(String(100), nullable=True)

    amount_cents        = Column(Integer, nullable=False, default=0)
    currency            = Column(String(10), default="eur")

    created_at          = Column(DateTime, default=datetime.utcnow)
    paid_at             = Column(DateTime, nullable=True)
