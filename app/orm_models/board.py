from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table, UniqueConstraint
from sqlalchemy.orm import relationship

from app.orm_models.db import Base


trip_stop_led_link = Table(
    "trip_stop_led_link",
    Base.metadata,
    Column("trip_stop_id", Integer, ForeignKey("trip_stop.id"), primary_key=True),
    Column("led_id", Integer, ForeignKey("led.id"), primary_key=True),
)


class Board(Base):
    __tablename__ = "board"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    owner_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    owner = relationship("User", backref="boards")
    svg_path = Column(String(255))
    led_strips = relationship("LedStrip", backref="board")


class LedStrip(Base):
    __tablename__ = "led_strip"

    id = Column(Integer, primary_key=True)
    board_id = Column(Integer, ForeignKey("board.id"), nullable=False)
    line_id = Column(Integer, ForeignKey("line.id"), nullable=False)
    line_agency_name = Column(String(100), nullable=False)
    order_index = Column(Integer, nullable=False, default=1)
    line = relationship(
        "Line",
        backref="led_strips",
        primaryjoin="and_(LedStrip.line_id == Line.id, LedStrip.line_agency_name == Line.agency_name)",
    )
    leds = relationship(
        "Led",
        back_populates="led_strip",
        cascade="all, delete-orphan",
        order_by="Led.ledstrip_index",
    )


class Order(Base):
    __tablename__ = "order"

    id = Column(Integer, primary_key=True)
    board_id = Column(Integer, ForeignKey("board.id"), nullable=False)
    order_details_id = Column(Integer, ForeignKey("order_details.id"), nullable=True)
    svg_path = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False, default="pending")
    led_colors = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)

    board = relationship("Board")
    order_details = relationship("OrderDetails", backref="orders")


class OrderDetails(Base):
    __tablename__ = "order_details"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    email = Column(String(255), nullable=True, unique=True)
    address_line1 = Column(String(255), nullable=True)
    city = Column(String(100), nullable=True)
    postal_code = Column(String(20), nullable=True)
    country = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", backref="order_details")


class Led(Base):
    __tablename__ = "led"
    __table_args__ = (
        UniqueConstraint("ledstrip_id", "ledstrip_index", name="uq_led_ledstrip_id_index"),
    )

    id = Column(Integer, primary_key=True)
    ledstrip_id = Column(Integer, ForeignKey("led_strip.id"), nullable=False)
    ledstrip_index = Column(Integer, nullable=False, index=True)
    custom_name = Column(String(100))
    type = Column(String(10), nullable=False)  # left/right/central
    led_color = Column(String(50), nullable=False, default="#00FF00")
    pre_travel_minutes = Column(Integer, nullable=True) 

    led_strip = relationship("LedStrip", back_populates="leds")
    trip_stops = relationship(
        "TripStop",
        secondary="trip_stop_led_link",
        back_populates="leds",
    )
