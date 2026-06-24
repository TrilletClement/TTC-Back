from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import backref, relationship

from app.orm_models.db import Base
from app.orm_models.board import trip_stop_led_link
# GTFSTrip was removed — raw_gtfs_trip (in raw_gtfs.py) stores the same mapping
# with richer fields and serves both STIB and TEC.


class Agency(Base):
    __tablename__ = "agency"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    country = Column(String(100), nullable=False)


class Stop(Base):
    __tablename__ = "stop"
    stop_id = Column(String(100), nullable=False)
    name = Column(String(100), nullable=False)
    agency_name = Column(String(100), ForeignKey("agency.name"), nullable=False)
    agency = relationship("Agency", backref="stops")

    __table_args__ = (
        PrimaryKeyConstraint("stop_id", "agency_name", name="pk_stopid_agency"),
    )


class Line(Base):
    __tablename__ = "line"

    id = Column(Integer, primary_key=True)
    route_id = Column(String(50), nullable=False)
    short_name = Column(String(10), nullable=False)
    long_name = Column(String(100), nullable=False)
    best_trip_0_id = Column(Integer, ForeignKey("trip.id"), nullable=True)
    best_trip_1_id = Column(Integer, ForeignKey("trip.id"), nullable=True)
    route_type = Column(String(10))
    color = Column(String(7))
    text_color = Column(String(7))

    agency_name = Column(String(100), ForeignKey("agency.name"), nullable=False)
    agency = relationship("Agency", backref="lines")

    best_trip_b = relationship(
        "Trip",
        foreign_keys=[best_trip_0_id],
        backref=backref("line_best_trip_0", uselist=False),
    )
    best_trip_f = relationship(
        "Trip",
        foreign_keys=[best_trip_1_id],
        backref=backref("line_best_trip_1", uselist=False),
    )
    __table_args__ = (
        UniqueConstraint("short_name", "long_name", "agency_name", name="uq_short_long_agency"),
    )


class Trip(Base):
    __tablename__ = "trip"

    id = Column(Integer, primary_key=True)
    signature = Column(String(64), nullable=True)

    terminus_stop_id = Column(String, nullable=False)
    terminus_agency_name = Column(String, nullable=False)

    start_stop_id = Column(String, nullable=False)
    start_agency_name = Column(String, nullable=False)

    line_id = Column(Integer, ForeignKey("line.id"), nullable=False)
    line_agency_name = Column(String, nullable=False)

    trip_count = Column(Integer, nullable=False, default=1)
    blacklisted = Column(Boolean, default=False)

    direction = Column(Integer, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["terminus_stop_id", "terminus_agency_name"],
            ["stop.stop_id", "stop.agency_name"],
        ),
        ForeignKeyConstraint(
            ["start_stop_id", "start_agency_name"],
            ["stop.stop_id", "stop.agency_name"],
        ),
    )

    terminus = relationship(
        "Stop",
        foreign_keys=[terminus_stop_id, terminus_agency_name],
        backref="trips_terminus",
    )
    start = relationship(
        "Stop",
        foreign_keys=[start_stop_id, start_agency_name],
        backref="trips_start",
    )
    line = relationship(
        "Line",
        foreign_keys=[line_id],
        backref="trips",
    )


class TripStop(Base):
    __tablename__ = "trip_stop"

    id = Column(Integer, primary_key=True)
    trip_id = Column(Integer, ForeignKey("trip.id"), nullable=False)
    stop_stop_id = Column(String, nullable=False)
    stop_agency_name = Column(String, nullable=False)
    vehicle_incoming = Column(Boolean, nullable=False, default=False)
    sequence = Column(Integer, nullable=False)

    leds = relationship(
        "Led",
        secondary=trip_stop_led_link,
        back_populates="trip_stops",
    )

    __table_args__ = (
        UniqueConstraint("trip_id", "sequence", name="uq_trip_stop_sequence"),
        ForeignKeyConstraint(
            ["stop_stop_id", "stop_agency_name"],
            ["stop.stop_id", "stop.agency_name"],
        ),
    )

    trip = relationship("Trip", backref="trip_stops")
    stop = relationship(
        "Stop",
        foreign_keys=[stop_stop_id, stop_agency_name],
        backref="trip_stops",
    )




class GtfsImportLog(Base):
    __tablename__ = "gtfs_import_log"

    agency_name      = Column(String(50), primary_key=True)
    status           = Column(String(10), nullable=False, default="never")
    started_at       = Column(DateTime, nullable=True)
    completed_at     = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    error_message    = Column(Text, nullable=True)
    rt_error_message = Column(Text, nullable=True)
    rt_error_at      = Column(DateTime, nullable=True)
