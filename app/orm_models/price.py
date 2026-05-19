from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.orm_models.db import Base


class PriceVersion(Base):
    __tablename__ = "price_version"

    id         = Column(Integer, primary_key=True)
    label      = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    prices         = relationship("BoardTypePrice", back_populates="version", cascade="all, delete-orphan")
    shipping_rates = relationship("ShippingRate",   back_populates="version", cascade="all, delete-orphan",
                                  order_by="ShippingRate.country_name")


class ShippingRate(Base):
    __tablename__ = "shipping_rate"
    __table_args__ = (
        UniqueConstraint("price_version_id", "country_code", name="uq_shipping_version_country"),
    )

    id                = Column(Integer, primary_key=True)
    price_version_id  = Column(Integer, ForeignKey("price_version.id", ondelete="CASCADE"), nullable=False)
    country_code      = Column(String(3),   nullable=False)
    country_name      = Column(String(100), nullable=False)
    cost_cents        = Column(Integer, nullable=False)
    delivery_days_min = Column(Integer, nullable=False)
    delivery_days_max = Column(Integer, nullable=False)
    version = relationship("PriceVersion", back_populates="shipping_rates")


class BoardTypePrice(Base):
    __tablename__ = "board_type_price"
    __table_args__ = (
        UniqueConstraint("price_version_id", "board_type_id", name="uq_price_version_board_type"),
    )

    id                  = Column(Integer, primary_key=True)
    price_version_id    = Column(Integer, ForeignKey("price_version.id"), nullable=False)
    board_type_id       = Column(Integer, ForeignKey("board_type.id"), nullable=False)
    base_price_cents    = Column(Integer, nullable=False)
    reduced_price_cents = Column(Integer, nullable=False)

    version    = relationship("PriceVersion", back_populates="prices")
    board_type = relationship("BoardType", backref="price_entries")
