from typing import Optional

import sqlalchemy as sa
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.orm_models.gtfs import Agency, Line, Stop, Trip, TripStop


class LineRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all_agencies(self) -> list[Agency]:
        return self.db.query(Agency).all()

    def search_lines(self, agency_name: str, search: Optional[str] = None) -> list[Line]:
        query = self.db.query(Line).filter_by(agency_name=agency_name)
        if search:
            pattern = f"%{search}%"
            query = query.filter(
                or_(Line.short_name.ilike(pattern), Line.long_name.ilike(pattern))
            )
        return query.all()

    def get_all_stops(self) -> list[Stop]:
        return self.db.query(Stop).all()

    def get_line_by_id(self, line_id: int) -> Optional[Line]:
        return self.db.query(Line).filter_by(id=line_id).first()

    def get_trip_by_id(self, trip_id) -> Optional[Trip]:
        return self.db.query(Trip).filter_by(id=trip_id).first()

    def get_trip_stops_with_stops(self, trip_id) -> list[tuple]:
        return (
            self.db.query(Stop, TripStop.sequence)
            .join(
                TripStop,
                (TripStop.stop_stop_id == Stop.stop_id)
                & (TripStop.stop_agency_name == Stop.agency_name),
            )
            .filter(TripStop.trip_id == trip_id)
            .order_by(TripStop.sequence)
            .all()
        )

    def get_nearest_stop(self, lat: float, lon: float) -> Optional[tuple[Stop, float]]:
        """Closest Stop (any agency) with known coordinates, via haversine distance.

        Uses the asin/sqrt form (not acos) to avoid acos(>1.0) returning NaN
        when float rounding pushes the argument just past 1.0 for a point at
        (near-)zero distance from a stop.
        """
        row = self.db.execute(sa.text("""
            SELECT stop_id, agency_name,
                   2 * 6371000 * asin(sqrt(
                       power(sin(radians(:lat - lat) / 2), 2) +
                       cos(radians(:lat)) * cos(radians(lat)) *
                       power(sin(radians(:lon - lon) / 2), 2)
                   )) AS distance_m
            FROM stop
            WHERE lat IS NOT NULL AND lon IS NOT NULL
            ORDER BY distance_m ASC
            LIMIT 1
        """), {"lat": lat, "lon": lon}).first()
        if not row:
            return None
        stop = self.db.query(Stop).filter_by(stop_id=row.stop_id, agency_name=row.agency_name).first()
        return (stop, row.distance_m) if stop else None

    def get_nearby_stops(self, lat: float, lon: float, radius_m: float) -> list[tuple[Stop, float]]:
        """Every Stop (any agency) with known coordinates within radius_m,
        closest first. Same haversine form as get_nearest_stop."""
        rows = self.db.execute(sa.text("""
            SELECT stop_id, agency_name, distance_m FROM (
                SELECT stop_id, agency_name,
                       2 * 6371000 * asin(sqrt(
                           power(sin(radians(:lat - lat) / 2), 2) +
                           cos(radians(:lat)) * cos(radians(lat)) *
                           power(sin(radians(:lon - lon) / 2), 2)
                       )) AS distance_m
                FROM stop
                WHERE lat IS NOT NULL AND lon IS NOT NULL
            ) AS with_distance
            WHERE distance_m <= :radius_m
            ORDER BY distance_m ASC
        """), {"lat": lat, "lon": lon, "radius_m": radius_m}).all()

        stops_by_key = {
            (s.stop_id, s.agency_name): s
            for s in self.db.query(Stop).filter(
                sa.tuple_(Stop.stop_id, Stop.agency_name).in_(
                    [(r.stop_id, r.agency_name) for r in rows]
                )
            )
        } if rows else {}

        result = []
        for r in rows:
            stop = stops_by_key.get((r.stop_id, r.agency_name))
            if stop:
                result.append((stop, r.distance_m))
        return result

    def get_lines_serving_stop(self, stop_id: str, agency_name: str) -> list[tuple[Line, int]]:
        """(Line, direction) pairs for every line whose canonical trip
        (best_trip_0_id or best_trip_1_id) passes through this stop."""
        return (
            self.db.query(Line, Trip.direction)
            .join(Trip, or_(Trip.id == Line.best_trip_0_id, Trip.id == Line.best_trip_1_id))
            .join(
                TripStop,
                (TripStop.trip_id == Trip.id)
                & (TripStop.stop_stop_id == stop_id)
                & (TripStop.stop_agency_name == agency_name),
            )
            .filter(Line.agency_name == agency_name)
            .all()
        )
