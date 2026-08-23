from typing import Optional

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.orm_models.board import Board, Led, LedStrip
from app.orm_models.gtfs import Line, Stop, Trip, TripStop


class LedStripRepository:
    # Same threshold the frontend's cosmetic trunk preview uses
    # (led-visualization.ts MIN_TRUNK_LEN) — below this a shared stop is
    # more likely an incidental interchange than a real shared corridor.
    MIN_TRUNK_LEN = 3

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

    def get_cross_line_sibling_trip_stops(
        self, trip_stop_ids: list[int], other_line_id: int,
    ) -> dict[int, list[TripStop]]:
        """For each given trip_stop id, the TripStops of a DIFFERENT line's
        trips serving the same physical stop.

        Used when a human confirms two strips on a board share a physical
        corridor (see LedStripService.link_cross_line_trunk) — every LED on
        the shared stretch then gets linked to both lines' TripStops, so a
        vehicle on either line lights it. Unlike get_sibling_trip_stops
        (same line, same direction), direction isn't filtered here: a
        different line's direction_id isn't guaranteed comparable to this
        one's, and the caller already knows which concrete strip/line it's
        pairing against. line_id alone identifies a Line (global PK, see
        get_sibling_trip_stops), no agency filter needed.
        """
        if not trip_stop_ids:
            return {}
        primary = sa.orm.aliased(TripStop)
        sibling_trip = sa.orm.aliased(Trip)
        rows = (
            self.db.query(primary.id, TripStop)
            .join(
                TripStop,
                (TripStop.stop_stop_id == primary.stop_stop_id)
                & (TripStop.stop_agency_name == primary.stop_agency_name)
                & (TripStop.trip_id != primary.trip_id),
            )
            .join(
                sibling_trip,
                (sibling_trip.id == TripStop.trip_id)
                & (sibling_trip.line_id == other_line_id),
            )
            .filter(primary.id.in_(trip_stop_ids))
            .all()
        )
        siblings: dict[int, list[TripStop]] = {}
        for primary_id, sibling_ts in rows:
            siblings.setdefault(primary_id, []).append(sibling_ts)
        return siblings

    @staticmethod
    def _longest_common_run(a_keys: list[tuple[str, str]], b_keys: list[tuple[str, str]]) -> int:
        """Longest run of consecutive matching physical stops between two
        ordered stop-key sequences, tried both forward and with `b`
        reversed (two lines can run through a shared corridor in opposite
        order) — same idea as the frontend's findTrunk, simplified to just
        the length since callers here only need a yes/no candidate signal.
        """
        best = 0
        for seq in (b_keys, list(reversed(b_keys))):
            prev_row = [0] * (len(seq) + 1)
            for i in range(1, len(a_keys) + 1):
                cur_row = [0] * (len(seq) + 1)
                for j in range(1, len(seq) + 1):
                    if a_keys[i - 1] == seq[j - 1]:
                        cur_row[j] = prev_row[j - 1] + 1
                        best = max(best, cur_row[j])
                prev_row = cur_row
        return best

    def find_trunk_candidate_strips(self, strip_id: int) -> list[dict]:
        """Other strips on the same board, on a different line, whose stop
        sequence overlaps this strip's by >= MIN_TRUNK_LEN consecutive
        physical stops — candidates offered to a human for an explicit
        cross-line trunk link (get_cross_line_sibling_trip_stops does the
        actual linking once one is picked).
        """
        strip = self.db.query(LedStrip).filter_by(id=strip_id).first()
        if not strip:
            return []

        def ordered_stop_keys(s: LedStrip) -> list[tuple[str, str]]:
            keys: list[tuple[str, str]] = []
            for led in s.leds:
                for ts in led.trip_stops:
                    key = (ts.stop_stop_id, ts.stop_agency_name)
                    if not keys or keys[-1] != key:
                        keys.append(key)
            return keys

        a_keys = ordered_stop_keys(strip)
        if not a_keys:
            return []

        other_strips = (
            self.db.query(LedStrip)
            .filter(
                LedStrip.board_id == strip.board_id,
                LedStrip.id != strip.id,
                LedStrip.line_id != strip.line_id,
            )
            .all()
        )

        candidates = []
        for other in other_strips:
            overlap = self._longest_common_run(a_keys, ordered_stop_keys(other))
            if overlap >= self.MIN_TRUNK_LEN:
                candidates.append({
                    "stripId": other.id,
                    "lineId": other.line_id,
                    "lineAgencyName": other.line_agency_name,
                    "routeLabel": other.line.short_name if other.line else str(other.line_id),
                    "overlapLength": overlap,
                })
        return candidates

    # ── Persistence ───────────────────────────────────────────────────────────

    def flush(self) -> None:
        self.db.flush()

    def commit(self) -> None:
        self.db.commit()
