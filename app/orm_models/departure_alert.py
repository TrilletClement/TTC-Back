from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import relationship

from app.orm_models.db import Base


class PushDevice(Base):
    """A phone of the user that receives push notifications (FCM registration token)."""
    __tablename__ = "push_device"

    id           = Column(Integer, primary_key=True)
    user_id      = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    token        = Column(String(512), nullable=False, unique=True)
    platform     = Column(String(20), nullable=False, default="android")
    # Language of the notifications sent to this phone ("fr" / "en").
    lang         = Column(String(5), nullable=False, default="fr")
    created_at   = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    user = relationship("User")


class DepartureAlert(Base):
    """"Time to leave" notification for one stop of one of the user's strips.

    Anchored on the strip + the station's GTFS stops (+ direction), never on a
    Led row: editing a strip deletes and recreates its LEDs. A station is all
    the stop ids one LED stands for (operators like STIB have one per
    platform/direction). If the station is no longer on the strip, the alert
    simply never fires (the API reports it).
    """
    __tablename__ = "departure_alert"

    id               = Column(Integer, primary_key=True)
    user_id          = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    led_strip_id     = Column(Integer, ForeignKey("led_strip.id", ondelete="CASCADE"), nullable=False, index=True)
    # [[stop_id, agency_name], ...] — the station's GTFS stops.
    stop_keys        = Column(JSON, nullable=False)
    # Station name as shown on the strip when the alert was saved (notification text).
    stop_name        = Column(String(100), nullable=False)
    # Trip.direction (0/1); NULL = both directions.
    direction        = Column(Integer, nullable=True)
    # "minutes": the vehicle reaches the stop within minutes_before;
    # "led": the stop's LED turns on (vehicle left the previous stop).
    trigger          = Column(String(10), nullable=False, default="minutes")
    minutes_before   = Column(Integer, nullable=False, default=5)
    # [{"days": [0..6] (Monday = 0), "start": "HH:MM", "end": "HH:MM"}], Brussels
    # time; end < start spans midnight; [] = always.
    windows          = Column(JSON, nullable=False, default=list)
    enabled          = Column(Boolean, nullable=False, default=True)
    created_at       = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    user = relationship("User")
    led_strip = relationship("LedStrip")


class DepartureAlertSent(Base):
    """One notification per alert and vehicle (trip of a service day)."""
    __tablename__ = "departure_alert_sent"
    __table_args__ = (
        UniqueConstraint("alert_id", "raw_trip_id", "service_date", name="uq_departure_alert_sent_trip"),
    )

    id           = Column(Integer, primary_key=True)
    alert_id     = Column(Integer, ForeignKey("departure_alert.id", ondelete="CASCADE"), nullable=False)
    raw_trip_id  = Column(Integer, nullable=False)
    service_date = Column(String(8), nullable=False)
    sent_at      = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
