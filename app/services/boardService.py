from sqlalchemy.orm import joinedload, Session
from fastapi import Depends, HTTPException, status
from app.orm_models.db import get_db
from app.orm_models.auth import User
from app.orm_models.board import Board, Led, LedStrip
from app.orm_models.gtfs import Line, Stop, Trip

class BoardService:
    @staticmethod
    def get_boards(current_user: User, db: Session):
        if "admin" in [role.name for role in current_user.roles]:
            boards = db.query(Board).all()
        else:
            boards = db.query(Board).filter_by(owner_id=current_user.id).all()
        
        return [{
            'id': board.id,
            'name': board.name,
            'owner_id': board.owner_id
        } for board in boards]

    @staticmethod
    def create_board(name: str, current_user: User, db: Session):
        if not name:
            raise HTTPException(status_code=400, detail="Board name is required")

        new_board = Board(name=name, owner=current_user)
        db.add(new_board)
        db.commit()
        db.refresh(new_board)
        return {"message": "Board added successfully!", "board_id": new_board.id}

    @staticmethod
    def delete_board(board_id: int, current_user: User, db: Session):
        board = db.query(Board)\
            .options(joinedload(Board.led_strips)
                     .joinedload(LedStrip.led1_obj)
                     .joinedload(Led.trip_stops))\
            .filter_by(id=board_id).first()

        if not board:
            raise HTTPException(status_code=404, detail="Board not found")

        if "admin" not in [role.name for role in current_user.roles] and board.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="Unauthorized")

        # Supprimer LEDs et TripStops
        leds_to_delete = set()
        for strip in board.led_strips:
            for i in range(1, 13):
                led_obj = getattr(strip, f'led{i}_obj', None)
                if led_obj:
                    leds_to_delete.add(led_obj)

        for led in leds_to_delete:
            led.trip_stops.clear()
        db.flush()

        for led in leds_to_delete:
            db.delete(led)
        for strip in board.led_strips:
            db.delete(strip)
        db.delete(board)
        db.commit()

        return {"message": "Board and related data deleted successfully!", "id": board_id}

    @staticmethod
    def get_board_details(board_id: int, current_user: User, db: Session):
        query = db.query(Board).options(
            joinedload(Board.led_strips)
            .joinedload(LedStrip.line)
            .joinedload(Line.best_trip_b)
            .joinedload(Trip.terminus),
            joinedload(Board.led_strips)
            .joinedload(LedStrip.line)
            .joinedload(Line.best_trip_f)
            .joinedload(Trip.terminus)
        )

        if "admin" in [role.name for role in current_user.roles]:
            board = query.filter_by(id=board_id).first()
        else:
            board = query.filter_by(id=board_id, owner_id=current_user.id).first()

        if not board:
            raise HTTPException(status_code=404, detail="Board not found")

        led_strips_data = BoardService._build_led_strips_data(board, db)
        return {
            'id': board.id,
            'name': board.name,
            'ownerId': board.owner_id,
            'ledStrips': led_strips_data
        }

    @staticmethod
    def _build_led_strips_data(board, db: Session):
        led_strips_data = []
        for strip in board.led_strips:
            line_obj = strip.line or db.query(Line)\
                .options(
                    joinedload(Line.best_trip_b).joinedload(Trip.terminus),
                    joinedload(Line.best_trip_f).joinedload(Trip.terminus)
                ).filter_by(id=strip.line_id).first()

            strip_data = {
                'id': strip.id,
                'boardId': strip.board_id,
                'lineId': strip.line_id,
                'lineAgencyName': strip.line_agency_name,
                'orderIndex': getattr(strip, 'order_index', None),
                'led_color': getattr(strip, 'led_color', None)
            }

            if line_obj:
                terminus0 = line_obj.best_trip_b
                terminus1 = line_obj.best_trip_f
                term0_name = BoardService._resolve_terminus_name(terminus0, db)
                term1_name = BoardService._resolve_terminus_name(terminus1, db)
                strip_data['line'] = {
                    'id': line_obj.id,
                    'routeId': line_obj.route_id,
                    'shortName': line_obj.short_name,
                    'name': line_obj.short_name,
                    'longName': line_obj.long_name,
                    'routeType': line_obj.route_type,
                    'color': line_obj.color,
                    'textColor': line_obj.text_color,
                    'bestTrip0Id': line_obj.best_trip_0_id,
                    'bestTrip1Id': line_obj.best_trip_1_id,
                    'agencyName': line_obj.agency_name,
                    'terminus0Name': term0_name,
                    'terminus1Name': term1_name
                }
                strip_data['color'] = line_obj.color
                strip_data['textColor'] = line_obj.text_color

            # LEDs
            for i in range(1, 13):
                led_obj = getattr(strip, f'led{i}_obj', None)
                if led_obj:
                    strip_data[f'led{i}'] = BoardService._build_led_data(led_obj)

            led_strips_data.append(strip_data)
        return led_strips_data

    @staticmethod
    def _resolve_terminus_name(trip: Trip | None, db: Session):
        if not trip:
            return None
        if getattr(trip, "terminus", None) and trip.terminus.name:
            return trip.terminus.name
        if trip.terminus_stop_id and trip.terminus_agency_name:
            stop = db.query(Stop).filter_by(
                stop_id=trip.terminus_stop_id,
                agency_name=trip.terminus_agency_name
            ).first()
            return stop.name if stop else None
        return None

    @staticmethod
    def _build_led_data(led_obj):
        trip_stops_data = [{
            'tripStopId': ts.id,
            'ledId': led_obj.id,
            'vehicleIncoming': ts.vehicle_incoming,
            'stopStopId': ts.stop_stop_id,
            'stopAgencyName': ts.stop_agency_name,
            'stopName': ts.stop.name if ts.stop else None
        } for ts in led_obj.trip_stops]

        return {
            'ledId': led_obj.id,
            'customName': led_obj.custom_name,
            'type': led_obj.type,
            'tripStops': trip_stops_data
        }

