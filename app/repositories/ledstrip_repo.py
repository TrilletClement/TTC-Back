from typing import Optional

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.orm_models.board import Board, Led, LedStrip
from app.orm_models.gtfs import Line, Stop, Trip, TripStop


class LedStripRepository:
    def __init__(self, db: Session):
        self.db = db

    # ── Board ─────────────────────────────────────────────────────────────────

    def get_board(self, board_id: int) -> Optional[Board]:
        return self.db.query(Board).filter_by(id=board_id).first()

    # ── LedStrip ──────────────────────────────────────────────────────────────

    def get_strip(self, strip_id: int, board_id: int) -> Optional[LedStrip]:
        return self.db.query(LedStrip).filter_by(id=strip_id, board_id=board_id).first()

    def get_strip_at_slot(self, board_id: int, order_index: int, exclude_id: int) -> Optional[LedStrip]:
        return self.db.query(LedStrip).filter(
            LedStrip.board_id == board_id,
            LedStrip.order_index == order_index,
            LedStrip.id != exclude_id,
        ).first()

    def count_strips(self, board_id: int) -> int:
        return (
            self.db.query(sa.func.count(LedStrip.id))
            .filter(LedStrip.board_id == board_id)
            .scalar()
        )

    def max_order_index(self, board_id: int) -> int:
        return (
            self.db.query(sa.func.max(LedStrip.order_index))
            .filter(LedStrip.board_id == board_id)
            .scalar()
        ) or 0

    def add_strip(self, strip: LedStrip) -> LedStrip:
        self.db.add(strip)
        self.db.flush()
        return strip

    def delete_strip(self, strip: LedStrip) -> None:
        for led in list(strip.leds):
            led.trip_stops.clear()
            self.db.delete(led)
        self.db.delete(strip)

    def get_strip_by_id_for_reorder(self, strip_id: int, board_id: int) -> Optional[LedStrip]:
        return self.db.query(LedStrip).filter_by(id=strip_id, board_id=board_id).first()

    # ── Led ───────────────────────────────────────────────────────────────────

    def add_led(self, led: Led) -> Led:
        self.db.add(led)
        self.db.flush()
        return led

    def get_led(self, led_id: int, ledstrip_id: int) -> Optional[Led]:
        return self.db.query(Led).filter_by(id=led_id, ledstrip_id=ledstrip_id).first()

    # ── GTFS ─────────────────────────────────────────────────────────────────

    def get_line(self, line_id: int, agency_name: str) -> Optional[Line]:
        return self.db.query(Line).filter_by(id=line_id, agency_name=agency_name).first()

    def get_trip(self, trip_id) -> Optional[Trip]:
        return self.db.query(Trip).filter_by(id=trip_id).first()

    def get_trip_stops(self, trip_id) -> list[TripStop]:
        return (
            self.db.query(TripStop)
            .filter_by(trip_id=trip_id)
            .order_by(TripStop.sequence)
            .all()
        )

    def get_stop(self, stop_id, agency_name: str) -> Optional[Stop]:
        return self.db.query(Stop).filter_by(stop_id=stop_id, agency_name=agency_name).first()

    def get_sibling_trip_stops(self, line_id: int, trip_stop_ids: list[int]) -> dict[int, list[TripStop]]:
        """For each given trip_stop id, the TripStops of OTHER canonical trips
        of the same line + direction that serve the same physical stop.

        Used at LED-creation time so a LED on a branching line's shared trunk
        gets linked to every trip variant passing its stop — a vehicle on
        either branch then lights it, while post-divergence stops (absent
        from the other branch's trips) stay branch-specific automatically.
        """
        if not trip_stop_ids:
            return {}
        primary = sa.orm.aliased(TripStop)
        primary_trip = sa.orm.aliased(Trip)
        sibling_trip = sa.orm.aliased(Trip)
        rows = (
            self.db.query(primary.id, TripStop)
            .join(primary_trip, primary_trip.id == primary.trip_id)
            .join(
                TripStop,
                (TripStop.stop_stop_id == primary.stop_stop_id)
                & (TripStop.stop_agency_name == primary.stop_agency_name)
                & (TripStop.trip_id != primary.trip_id),
            )
            .join(
                sibling_trip,
                (sibling_trip.id == TripStop.trip_id)
                & (sibling_trip.line_id == line_id)
                & (sibling_trip.direction == primary_trip.direction),
            )
            .filter(primary.id.in_(trip_stop_ids))
            .all()
        )
        siblings: dict[int, list[TripStop]] = {}
        for primary_id, sibling_ts in rows:
            siblings.setdefault(primary_id, []).append(sibling_ts)
        return siblings

    # ── Persistence ───────────────────────────────────────────────────────────

    def flush(self) -> None:
        self.db.flush()

    def commit(self) -> None:
        self.db.commit()
