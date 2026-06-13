from typing import Optional

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
