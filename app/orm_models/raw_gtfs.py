"""
Raw GTFS + realtime override models.

These tables form the operational layer beneath the stable canonical
Trip / TripStop abstraction.  LEDs remain linked to canonical TripStops only.

Architecture:
  raw_gtfs_service_date            (service_id, agency_name, date)
  raw_gtfs_trip      ──FK──►  trip (canonical)
  raw_gtfs_stop_time ──FK──►  raw_gtfs_trip
  raw_gtfs_stop_time ──FK──►  trip_stop (canonical, nullable)
  realtime_stop_time_override  (keyed by gtfs_trip_id + start_date + stop_seq)

Active-trip filtering uses arrival_seconds (indexed) AND a join to
raw_gtfs_service_date to restrict to trips actually running today.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
)

from app.orm_models.db import Base


class RawGtfsTrip(Base):
    """
    One row per GTFS trips.txt entry.

    canonical_trip_id links back to the stable Trip pattern that was derived
    from this GTFS trip during the import signature-grouping step.  It may be
    NULL for trips whose route was not imported (unknown line, etc.).

    Surrogate integer PK keeps raw_gtfs_stop_time rows slim (4 bytes vs ~43
    bytes for the (gtfs_trip_id, agency_name) composite key).
    (gtfs_trip_id, agency_name) is a UNIQUE constraint so cross-PTO uniqueness
    is still enforced without bloating child rows.
    """

    __tablename__ = "raw_gtfs_trip"

    id = Column(Integer, primary_key=True, autoincrement=True)
    gtfs_trip_id = Column(String(100), nullable=False)
    agency_name = Column(String(100), ForeignKey("agency.name"), nullable=False)

    route_id = Column(String(50), nullable=False)
    service_id = Column(String(50), nullable=False)
    direction_id = Column(Integer, nullable=False, default=0)
    shape_id = Column(String(50), nullable=True)
    trip_headsign = Column(String(200), nullable=True)

    # Link to the canonical pattern (may be NULL if route unknown)
    canonical_trip_id = Column(Integer, ForeignKey("trip.id"), nullable=True)

    __table_args__ = (
        UniqueConstraint("gtfs_trip_id", "agency_name", name="uq_raw_gtfs_trip"),
        Index("ix_raw_gtfs_trip_canonical", "canonical_trip_id"),
        Index("ix_raw_gtfs_trip_service", "service_id", "agency_name"),
        Index("ix_raw_gtfs_trip_route", "route_id", "agency_name"),
    )


class RawGtfsStopTime(Base):
    """
    One row per stop_times.txt entry.

    arrival_seconds / departure_seconds store seconds-from-midnight so that
    interval arithmetic can be done in SQL without string parsing.  Values may
    exceed 86 400 for trips that run past midnight (GTFS allows this).

    raw_trip_id is a FK to raw_gtfs_trip.id (surrogate integer) rather than
    the (gtfs_trip_id, agency_name) composite — saves ~43 bytes per row on a
    table that can hold millions of rows.

    canonical_trip_stop_id is populated during import by matching stop_id
    against the TripStops of the canonical Trip linked from RawGtfsTrip.
    It is NULL when no canonical TripStop was found (unmapped stop).
    """

    __tablename__ = "raw_gtfs_stop_time"

    id = Column(Integer, primary_key=True, autoincrement=True)
    raw_trip_id = Column(Integer, ForeignKey("raw_gtfs_trip.id"), nullable=False)
    stop_sequence = Column(Integer, nullable=False)
    stop_id = Column(String(100), nullable=False)

    # Integer seconds from midnight — used in all interval queries
    arrival_seconds = Column(Integer, nullable=True)
    departure_seconds = Column(Integer, nullable=True)

    # The stable canonical stop this raw row maps to (NULL = unmapped)
    canonical_trip_stop_id = Column(Integer, ForeignKey("trip_stop.id"), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "raw_trip_id", "stop_sequence",
            name="uq_raw_gtfs_st_trip_seq",
        ),
        Index("ix_raw_gtfs_st_canonical", "canonical_trip_stop_id"),
        Index("ix_raw_gtfs_st_trip", "raw_trip_id"),
        Index("ix_raw_gtfs_st_arr_sec", "arrival_seconds"),
    )



class RealtimeStopTimeOverride(Base):
    """
    GTFS-RT TripUpdates overrides.

    One row per (trip, start_date, stop_sequence).  The poller does a pure
    upsert — it never computes LED states.  The interval query reads these
    rows to replace static schedule times with predicted times.

    schedule_relationship values (GTFS-RT spec):
      0 = SCHEDULED (default, times updated)
      1 = SKIPPED    (stop will not be served — interval query must skip it)
      2 = NO_DATA
    """

    __tablename__ = "realtime_stop_time_override"

    id = Column(Integer, primary_key=True, autoincrement=True)
    gtfs_trip_id = Column(String(100), nullable=False)
    agency_name = Column(String(100), nullable=False)
    start_date = Column(String(8), nullable=False)    # YYYYMMDD

    stop_sequence = Column(Integer, nullable=False)
    stop_id = Column(String(100), nullable=True)

    # Unix timestamps (seconds); NULL = not provided by feed
    predicted_arrival_ts = Column(BigInteger, nullable=True)
    predicted_departure_ts = Column(BigInteger, nullable=True)

    delay_seconds = Column(Integer, nullable=True)
    schedule_relationship = Column(Integer, nullable=True, default=0)

    feed_timestamp = Column(BigInteger, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "gtfs_trip_id", "agency_name", "start_date", "stop_sequence",
            name="uq_rt_override_trip_date_seq",
        ),
        # Hot-path: look up overrides for a specific trip + date
        Index("ix_rt_override_trip_date", "gtfs_trip_id", "agency_name", "start_date"),
        # Cleanup: find old override rows by date
        Index("ix_rt_override_date", "start_date", "agency_name"),
    )


class RawGtfsServiceDate(Base):
    """
    Precomputed flat table of (service_id, agency_name, date) rows.

    Built from calendar.txt (weekly recurrence expanded over start_date..end_date)
    + calendar_dates.txt (exception_type 1=add, 2=remove).  Replaces on every
    static GTFS import.

    The active_incoming_intervals view joins here to restrict trips to those
    actually running today, fixing the seconds-from-midnight ambiguity.
    """

    __tablename__ = "raw_gtfs_service_date"

    service_id = Column(String(100), nullable=False)
    agency_name = Column(String(100), ForeignKey("agency.name"), nullable=False)
    date = Column(String(8), nullable=False)   # YYYYMMDD

    __table_args__ = (
        PrimaryKeyConstraint("service_id", "agency_name", "date",
                             name="pk_raw_gtfs_service_date"),
        Index("ix_raw_gtfs_service_date_today", "agency_name", "date"),
    )
