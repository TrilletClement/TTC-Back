import re
from math import asin, cos, radians, sin, sqrt
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.repositories.line_repo import LineRepository


class LineService:

    @staticmethod
    def get_agencies(db: Session):
        repo = LineRepository(db)
        return [{"id": a.id, "name": a.name} for a in repo.get_all_agencies()]

    @staticmethod
    def get_lines(agency_name: str, search: Optional[str], db: Session):
        repo = LineRepository(db)
        lines = repo.search_lines(agency_name, search)
        lines = sorted(lines, key=LineService._line_sort_key)
        return [
            {
                "id": str(line.id),
                "longName": line.long_name,
                "name": line.short_name,
                "color": line.color,
                "textColor": line.text_color,
                "text_color": line.text_color,
            }
            for line in lines
        ]

    @staticmethod
    def get_stops(db: Session):
        repo = LineRepository(db)
        return [
            {"id": s.stop_id, "name": s.name, "agency_name": s.agency_name}
            for s in repo.get_all_stops()
        ]

    @staticmethod
    def get_line_stops(line_id: int, db: Session):
        try:
            repo = LineRepository(db)
            line = repo.get_line_by_id(line_id)
            if not line:
                raise HTTPException(status_code=404, detail="Line not found")

            trips = [
                t
                for t in [
                    repo.get_trip_by_id(line.best_trip_0_id),
                    repo.get_trip_by_id(line.best_trip_1_id),
                ]
                if t
            ]
            if not trips:
                raise HTTPException(status_code=404, detail="No trips found")

            stops_by_direction, _ = LineService._build_stops_by_direction(repo, trips)

            return {
                "line": {
                    "id": line.id,
                    "route_id": line.route_id,
                    "agency_name": line.agency_name,
                    "short_name": line.short_name,
                    "long_name": line.long_name,
                    "color": line.color,
                    "text_color": line.text_color,
                    "textColor": line.text_color,
                },
                "stops_by_direction": stops_by_direction,
            }

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Stops within this radius of the user's position are all considered —
    # multimodal hubs (e.g. a tram platform and a bus platform a few tens of
    # meters apart) genuinely serve different lines, so picking only the
    # single closest stop_id would silently guess wrong.
    NEARBY_RADIUS_METERS = 200

    @staticmethod
    def find_nearest_stop_with_lines(lat: float, lon: float, db: Session):
        repo = LineRepository(db)

        nearby = repo.get_nearby_stops(lat, lon, LineService.NEARBY_RADIUS_METERS)
        if not nearby:
            # Sparse area: no stop within radius — fall back to whichever
            # stop is closest regardless of distance, same as before.
            nearest = repo.get_nearest_stop(lat, lon)
            if not nearest:
                raise HTTPException(status_code=404, detail="No stop with known coordinates found")
            nearby = [nearest]

        candidates = []
        seen_line_ids: set[int] = set()
        for stop, distance_m in nearby:
            for line, direction in repo.get_lines_serving_stop(stop.stop_id, stop.agency_name):
                if line.id in seen_line_ids:
                    continue
                seen_line_ids.add(line.id)

                trips = [
                    t for t in [
                        repo.get_trip_by_id(line.best_trip_0_id),
                        repo.get_trip_by_id(line.best_trip_1_id),
                    ] if t
                ]
                stops_by_direction, nearest_stop_by_direction = LineService._build_stops_by_direction(
                    repo, trips, lat, lon
                )

                candidates.append({
                    "agency_name": stop.agency_name,
                    "line_id": line.id,
                    "direction": str(direction),
                    "stop_id": f"{stop.stop_id}_{stop.agency_name}",
                    "stop_name": stop.name,
                    "distance_meters": round(distance_m, 1),
                    "line": {
                        "id": line.id,
                        "route_id": line.route_id,
                        "agency_name": line.agency_name,
                        "short_name": line.short_name,
                        "long_name": line.long_name,
                        "color": line.color,
                        "text_color": line.text_color,
                        "textColor": line.text_color,
                    },
                    "stops_by_direction": stops_by_direction,
                    # Nearest stop to the user's position within each
                    # direction's own stop list — lets the wizard pre-fill
                    # both directions instead of just the one that matched.
                    "nearest_stop_by_direction": nearest_stop_by_direction,
                })

        if not candidates:
            raise HTTPException(status_code=404, detail="No line serves any nearby stop")

        return {"candidates": candidates}

    @staticmethod
    def _build_stops_by_direction(
        repo: LineRepository, trips, lat: Optional[float] = None, lon: Optional[float] = None
    ):
        """Returns (stops_by_direction, nearest_stop_by_direction).

        stops_by_direction: per direction, the stop list of that direction's
        longest known trip (the canonical pattern).
        nearest_stop_by_direction: per direction, the id of the stop in that
        same list closest to (lat, lon), or omitted when lat/lon aren't given
        or the direction has no located stops.
        """
        stops_by_direction: dict = {}
        trip_stops_by_direction: dict = {}
        for trip in trips:
            direction = trip.direction
            trip_stops = repo.get_trip_stops_with_stops(trip.id)
            if len(trip_stops) > len(trip_stops_by_direction.get(direction, [])):
                trip_stops_by_direction[direction] = trip_stops
                stops_by_direction[direction] = [
                    {
                        "id": f"{stop.stop_id}_{stop.agency_name}",
                        "stop_id": stop.stop_id,
                        "name": stop.name,
                        "agency_name": stop.agency_name,
                        "sequence": sequence,
                    }
                    for stop, sequence in trip_stops
                ]

        nearest_stop_by_direction: dict = {}
        if lat is not None and lon is not None:
            for direction, trip_stops in trip_stops_by_direction.items():
                located = [s for s, _ in trip_stops if s.lat is not None and s.lon is not None]
                if not located:
                    continue
                nearest = min(located, key=lambda s: LineService._haversine_m(lat, lon, s.lat, s.lon))
                nearest_stop_by_direction[direction] = f"{nearest.stop_id}_{nearest.agency_name}"

        return stops_by_direction, nearest_stop_by_direction

    @staticmethod
    def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        p1, p2 = radians(lat1), radians(lat2)
        dphi = radians(lat2 - lat1)
        dlambda = radians(lon2 - lon1)
        a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlambda / 2) ** 2
        return 2 * 6371000 * asin(sqrt(a))

    @staticmethod
    def _line_sort_key(line):
        short_name = line.short_name or ""
        if short_name and short_name[0].isdigit():
            match = re.match(r"(\d+)", short_name)
            if match:
                return (0, int(match.group(1)), short_name)
        return (1, short_name)
