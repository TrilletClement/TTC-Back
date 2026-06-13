import re
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

            stops_by_direction = LineService._build_stops_by_direction(repo, trips)

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

    @staticmethod
    def _build_stops_by_direction(repo: LineRepository, trips):
        stops_by_direction = {}
        for trip in trips:
            direction = trip.direction
            stops_by_direction.setdefault(direction, [])
            trip_stop_list = [
                {
                    "id": f"{stop.stop_id}_{stop.agency_name}",
                    "stop_id": stop.stop_id,
                    "name": stop.name,
                    "agency_name": stop.agency_name,
                    "sequence": sequence,
                }
                for stop, sequence in repo.get_trip_stops_with_stops(trip.id)
            ]
            if len(trip_stop_list) > len(stops_by_direction[direction]):
                stops_by_direction[direction] = trip_stop_list
        return stops_by_direction

    @staticmethod
    def _line_sort_key(line):
        short_name = line.short_name or ""
        if short_name and short_name[0].isdigit():
            match = re.match(r"(\d+)", short_name)
            if match:
                return (0, int(match.group(1)), short_name)
        return (1, short_name)
