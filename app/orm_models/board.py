from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Table, UniqueConstraint
from sqlalchemy.orm import relationship

from app.orm_models.db import Base


trip_stop_led_link = Table(
    "trip_stop_led_link",
    Base.metadata,
    Column("trip_stop_id", Integer, ForeignKey("trip_stop.id"), primary_key=True),
    Column("led_id", Integer, ForeignKey("led.id"), primary_key=True),
)


class BoardType(Base):
    __tablename__ = "board_type"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    max_led = Column(Integer, nullable=False)
    max_ledstrip = Column(Integer, nullable=False)

    # Physical dimensions (mm) — used for SVG export and frame preview
    max_width_mm       = Column(Float, nullable=True)
    max_height_mm      = Column(Float, nullable=True)
    delta_x_mm         = Column(Float, nullable=True)
    delta_y_mm         = Column(Float, nullable=True)
    frame_inner_x_mm   = Column(Float, nullable=True)
    frame_inner_y_mm   = Column(Float, nullable=True)
    frame_outer_x_mm   = Column(Float, nullable=True)
    frame_outer_y_mm   = Column(Float, nullable=True)
    frame_overlap_x_mm = Column(Float, nullable=True)
    frame_overlap_y_mm = Column(Float, nullable=True)


class Board(Base):
    __tablename__ = "board"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    owner_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    owner = relationship("User", backref="boards")
    svg_path = Column(String(255))
    archived = Column(Boolean, nullable=False, default=False)
    board_type_id = Column(Integer, ForeignKey("board_type.id"), nullable=False)
    board_type = relationship("BoardType")
    led_strips = relationship("LedStrip", backref="board")


class LedStrip(Base):
    __tablename__ = "led_strip"

    id = Column(Integer, primary_key=True)
    board_id = Column(Integer, ForeignKey("board.id"), nullable=False)
    line_id = Column(Integer, ForeignKey("line.id"), nullable=False)
    line_agency_name = Column(String(100), nullable=False)
    order_index = Column(Integer, nullable=False, default=1)
    integrated_terminus = Column(Boolean, default=False, nullable=False)
    custom_terminus_left_name  = Column(String(50), nullable=True)
    custom_terminus_right_name = Column(String(50), nullable=True)
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


class Led(Base):
    __tablename__ = "led"
    __table_args__ = (
        UniqueConstraint("ledstrip_id", "ledstrip_index", name="uq_led_ledstrip_id_index"),
    )

    id = Column(Integer, primary_key=True)
    ledstrip_id = Column(Integer, ForeignKey("led_strip.id"), nullable=False)
    ledstrip_index = Column(Integer, nullable=False, index=True)
    custom_name = Column(String(100))
    custom_subname = Column(String(100))
    type = Column(String(10), nullable=False)  # left/right/central
    led_color = Column(String(50), nullable=False, default="#00FF00")
    pre_travel_minutes = Column(Integer, nullable=True) 

    led_strip = relationship("LedStrip", back_populates="leds")
    trip_stops = relationship(
        "TripStop",
        secondary="trip_stop_led_link",
        back_populates="leds",
    )
