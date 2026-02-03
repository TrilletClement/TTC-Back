from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import backref, relationship

from app.orm_models.db import Base
from app.orm_models.board import trip_stop_led_link


class Agency(Base):
    __tablename__ = "agency"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    country = Column(String(100), nullable=False)


class SubAgency(Base):
    __tablename__ = "subagency"
    id = Column(String(10), nullable=False)
    name = Column(String(100), unique=True, nullable=False)
    agency_name = Column(String(100), ForeignKey("agency.name"), nullable=False)
    agency = relationship("Agency", backref="subagencies")

    __table_args__ = (
        PrimaryKeyConstraint("id", "agency_name", name="pk_subagency_id_agency"),
    )


class Stop(Base):
    __tablename__ = "stop"
    stop_id = Column(String(10), nullable=False)
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
    subagency_id = Column(String(10), nullable=True)
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
    subagency = relationship(
        "SubAgency",
        backref="lines",
        foreign_keys=[subagency_id, agency_name],
        overlaps="agency,lines",
    )

    __table_args__ = (
        UniqueConstraint("short_name", "long_name", "agency_name", name="uq_short_long_agency"),
        ForeignKeyConstraint(
            ["subagency_id", "agency_name"],
            ["subagency.id", "subagency.agency_name"],
            name="fk_line_subagency",
        ),
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


class GTFSTrip(Base):
    __tablename__ = "gtfs_trip"

    id = Column(String(100), nullable=False)
    trip_id = Column(Integer, ForeignKey("trip.id"), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("id", "trip_id", name="pk_gtfs_trip_composite"),
    )
    pattern = relationship("Trip", backref="gtfs_mappings")
