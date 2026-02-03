from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table
from sqlalchemy.orm import backref, relationship

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
    led_color = Column(String(50), nullable=False, default="red")
    line = relationship(
        "Line",
        backref="led_strips",
        primaryjoin="and_(LedStrip.line_id == Line.id, LedStrip.line_agency_name == Line.agency_name)",
    )

    led1 = Column(Integer, ForeignKey("led.id"))
    led2 = Column(Integer, ForeignKey("led.id"))
    led3 = Column(Integer, ForeignKey("led.id"))
    led4 = Column(Integer, ForeignKey("led.id"))
    led5 = Column(Integer, ForeignKey("led.id"))
    led6 = Column(Integer, ForeignKey("led.id"))
    led7 = Column(Integer, ForeignKey("led.id"))
    led8 = Column(Integer, ForeignKey("led.id"))
    led9 = Column(Integer, ForeignKey("led.id"))
    led10 = Column(Integer, ForeignKey("led.id"))
    led11 = Column(Integer, ForeignKey("led.id"))
    led12 = Column(Integer, ForeignKey("led.id"))

    led1_obj = relationship("Led", foreign_keys=[led1], backref=backref("ledstrip1", uselist=False))
    led2_obj = relationship("Led", foreign_keys=[led2], backref=backref("ledstrip2", uselist=False))
    led3_obj = relationship("Led", foreign_keys=[led3], backref=backref("ledstrip3", uselist=False))
    led4_obj = relationship("Led", foreign_keys=[led4], backref=backref("ledstrip4", uselist=False))
    led5_obj = relationship("Led", foreign_keys=[led5], backref=backref("ledstrip5", uselist=False))
    led6_obj = relationship("Led", foreign_keys=[led6], backref=backref("ledstrip6", uselist=False))
    led7_obj = relationship("Led", foreign_keys=[led7], backref=backref("ledstrip7", uselist=False))
    led8_obj = relationship("Led", foreign_keys=[led8], backref=backref("ledstrip8", uselist=False))
    led9_obj = relationship("Led", foreign_keys=[led9], backref=backref("ledstrip9", uselist=False))
    led10_obj = relationship("Led", foreign_keys=[led10], backref=backref("ledstrip10", uselist=False))
    led11_obj = relationship("Led", foreign_keys=[led11], backref=backref("ledstrip11", uselist=False))
    led12_obj = relationship("Led", foreign_keys=[led12], backref=backref("ledstrip12", uselist=False))


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
    id = Column(Integer, primary_key=True)
    custom_name = Column(String(100))
    type = Column(String(10), nullable=False)  # left/right/central
    trip_stops = relationship(
        "TripStop",
        secondary="trip_stop_led_link",
        back_populates="leds",
    )
