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
    cart_ref            = Column(String(20),  nullable=True)
    payment_intent_id   = Column(String(255), nullable=True)
    status              = Column(String(50), default="pending", nullable=False)

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

    tracking_number     = Column(String(100), nullable=True)

    amount_cents        = Column(Integer, nullable=False, default=0)
    currency            = Column(String(10), default="eur")
    shipping_cost_cents = Column(Integer, nullable=True)

    sendcloud_parcel_id  = Column(String(50),  nullable=True)
    label_url            = Column(String(500), nullable=True)
    tracking_url         = Column(String(500), nullable=True)
    shipping_option_code = Column(String(100), nullable=True)

    created_at          = Column(DateTime, default=datetime.utcnow)
    paid_at             = Column(DateTime, nullable=True)

    items               = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_item"

    id            = Column(Integer, primary_key=True)
    order_id      = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    board_id      = Column(Integer, ForeignKey("board.id"), nullable=True)
    svg_content   = Column(Text, nullable=True)
    amount_cents  = Column(Integer, nullable=False, default=0)
    esp_device_id = Column(Integer, ForeignKey("esp32_device.id"), nullable=True)

    order      = relationship("Order", back_populates="items")
    board      = relationship("Board")
    esp_device = relationship("ESP32Device", foreign_keys=[esp_device_id])
