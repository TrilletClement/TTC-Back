import re
from typing import Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.orm_models.gtfs import Agency, Line, Stop, Trip, TripStop

class LineService:

    @staticmethod
    def get_agencies(db: Session):
        agencies = db.query(Agency).all()
        return [{'id': a.id, 'name': a.name} for a in agencies]


    @staticmethod
    def get_lines(agency_name: str, search: Optional[str], db: Session):
        query = db.query(Line).filter_by(agency_name=agency_name)
        
        # Si un terme de recherche est fourni, filtrer les résultats
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                or_(
                    Line.short_name.ilike(search_pattern),
                    Line.long_name.ilike(search_pattern)
                )
            )
        
        lines = query.all()
        lines = sorted(lines, key=LineService._line_sort_key)

        return [{
            'id': str(line.id),
            'longName': line.long_name,
            'name': line.short_name,
            'color': line.color,
            'textColor': line.text_color,
            'text_color': line.text_color,
        } for line in lines]

    @staticmethod
    def get_stops(db: Session):
        stops = db.query(Stop).all()
        return [{
            'id': stop.stop_id,
            'name': stop.name,
            'agency_name': stop.agency_name
        } for stop in stops]

    @staticmethod
    def get_line_stops(line_id: int, db: Session):
        try:
            line = db.query(Line).filter_by(id=line_id).first()
            if not line:
                raise HTTPException(status_code=404, detail="Line not found")

            trips = [
                db.query(Trip).filter_by(id=line.best_trip_0_id).first(),
                db.query(Trip).filter_by(id=line.best_trip_1_id).first()
            ]
            trips = [t for t in trips if t]

            if not trips:
                raise HTTPException(status_code=404, detail="No trips found")

            stops_by_direction = LineService._build_stops_by_direction(db, trips)

            return {
                'line': {
                    'id': line.id,
                    'route_id': line.route_id,
                    'agency_name': line.agency_name,
                    'short_name': line.short_name,
                    'long_name': line.long_name,
                    'color': line.color,
                    'text_color': line.text_color,
                    'textColor': line.text_color,
                },
                'stops_by_direction': stops_by_direction
            }

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @staticmethod
    def _build_stops_by_direction(db: Session, trips):
        stops_by_direction = {}

        for trip in trips:
            direction = trip.direction
            stops_by_direction.setdefault(direction, [])

            trip_stops = db.query(
                Stop,
                TripStop.sequence
            ).join(
                TripStop,
                (TripStop.stop_stop_id == Stop.stop_id) &
                (TripStop.stop_agency_name == Stop.agency_name)
            ).filter(
                TripStop.trip_id == trip.id
            ).order_by(TripStop.sequence).all()

            trip_stop_list = [{
                'id': f"{stop.stop_id}_{stop.agency_name}",
                'stop_id': stop.stop_id,
                'name': stop.name,
                'agency_name': stop.agency_name,
                'sequence': sequence
            } for stop, sequence in trip_stops]

            # garder la liste la plus longue par direction
            if len(trip_stop_list) > len(stops_by_direction[direction]):
                stops_by_direction[direction] = trip_stop_list

        return stops_by_direction

    @staticmethod
    def _line_sort_key(line):
        short_name = line.short_name or ""
        if short_name and short_name[0].isdigit():
            match = re.match(r'(\d+)', short_name)
            if match:
                return (0, int(match.group(1)), short_name)
        return (1, short_name)
