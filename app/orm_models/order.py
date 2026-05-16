from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from app.orm_models.db import Base


class OrderDetails(Base):
    __tablename__ = "order_details"

    id            = Column(Integer, primary_key=True)
    user_id       = Column(Integer, ForeignKey("user.id"), nullable=False)
    user          = relationship("User", backref="order_details")

    first_name    = Column(String(100), nullable=False)
    last_name     = Column(String(100), nullable=False)
    email         = Column(String(200), nullable=False)
    address_line1 = Column(String(255), nullable=False)
    city          = Column(String(100), nullable=False)
    postal_code   = Column(String(20),  nullable=False)
    country       = Column(String(10),  nullable=False)

    created_at    = Column(DateTime, default=datetime.utcnow)

    orders        = relationship("Order", back_populates="order_details")


class Order(Base):
    __tablename__ = "orders"

    id                = Column(Integer, primary_key=True)
    stripe_session_id = Column(String(255), unique=True, nullable=True)
    status            = Column(String(50), default="pending", nullable=False)
    # pending | paid | cancelled

    board_id          = Column(Integer, ForeignKey("board.id"), nullable=True)
    board             = relationship("Board", backref="orders")

    user_id           = Column(Integer, ForeignKey("user.id"), nullable=False)
    user              = relationship("User", backref="orders")

    order_details_id  = Column(Integer, ForeignKey("order_details.id"), nullable=True)
    order_details     = relationship("OrderDetails", back_populates="orders")

    led_colors        = Column(String(255))
    svg_path          = Column(String(255))

    amount_cents      = Column(Integer, nullable=False, default=0)
    currency          = Column(String(10), default="eur")

    price_version_id  = Column(Integer, ForeignKey("price_version.id"), nullable=True)

    created_at        = Column(DateTime, default=datetime.utcnow)
    paid_at           = Column(DateTime, nullable=True)