from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.orm_models.auth import User
from app.orm_models.board import Board, BoardType, Led, LedStrip
from app.orm_models.gtfs import Line, Stop, Trip


class BoardService:
    @staticmethod
    def get_boards(current_user: User, db: Session):
        if "admin" in [role.name for role in current_user.roles]:
            boards = db.query(Board).filter_by(archived=False).all()
        else:
            boards = db.query(Board).filter_by(owner_id=current_user.id, archived=False).all()

        return [{"id": board.id, "name": board.name, "owner_id": board.owner_id} for board in boards]

    @staticmethod
    def get_board_types(db: Session):
        types = db.query(BoardType).all()
        return [
            {"id": t.id, "name": t.name, "maxLed": t.max_led, "maxLedstrip": t.max_ledstrip}
            for t in types
        ]

    @staticmethod
    def create_board(name: str, current_user: User, db: Session, board_type_id: int | None = None):
        if not name:
            raise HTTPException(status_code=400, detail="Board name is required")

        if board_type_id is not None:
            board_type = db.query(BoardType).filter_by(id=board_type_id).first()
            if not board_type:
                raise HTTPException(status_code=400, detail="Invalid board type")

        new_board = Board(name=name, owner=current_user, board_type_id=board_type_id)
        db.add(new_board)
        db.commit()
        db.refresh(new_board)
        return {"message": "Board added successfully!", "board_id": new_board.id}

    @staticmethod
    def delete_board(board_id: int, current_user: User, db: Session, force_unlink_devices: bool = False):
        from app.orm_models.device import ESP32Device
        from app.orm_models.order import Order

        board = (
            db.query(Board)
            .options(
                joinedload(Board.led_strips)
                .joinedload(LedStrip.leds)
                .joinedload(Led.trip_stops)
            )
            .filter_by(id=board_id)
            .first()
        )

        if not board:
            raise HTTPException(status_code=404, detail="Board not found")

        if "admin" not in [role.name for role in current_user.roles] and board.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="Unauthorized")

        # Devices linked — require explicit confirmation before proceeding
        linked_devices = db.query(ESP32Device).filter_by(board_id=board_id).all()
        if linked_devices and not force_unlink_devices:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "devices_linked",
                    "devices": [
                        {"id": d.id, "name": d.name or d.mac_address, "mac": d.mac_address}
                        for d in linked_devices
                    ],
                },
            )

        # Unlink devices if confirmed
        for device in linked_devices:
            device.board_id = None

        # Orders exist — archive instead of hard-delete
        has_orders = db.query(Order).filter_by(board_id=board_id).first() is not None
        if has_orders:
            board.archived = True
            db.commit()
            return {"archived": True, "id": board_id, "message": "Board archived (linked orders preserved)"}

        # Hard delete: cascade strips → leds → trip_stop links
        for strip in board.led_strips:
            for led in strip.leds:
                led.trip_stops.clear()
                db.delete(led)
            db.delete(strip)
        db.delete(board)
        db.commit()

        return {"archived": False, "id": board_id, "message": "Board deleted successfully"}

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
            .joinedload(Trip.terminus),
            joinedload(Board.led_strips)
            .joinedload(LedStrip.leds)
            .joinedload(Led.trip_stops),
        )

        if "admin" in [role.name for role in current_user.roles]:
            board = query.filter_by(id=board_id).first()
        else:
            board = query.filter_by(id=board_id, owner_id=current_user.id).first()

        if not board:
            raise HTTPException(status_code=404, detail="Board not found")

        led_strips_data = BoardService._build_led_strips_data(board, db)
        return {
            "id": board.id,
            "name": board.name,
            "ownerId": board.owner_id,
            "ledStrips": led_strips_data,
        }

    @staticmethod
    def _build_led_strips_data(board, db: Session):
        led_strips_data = []
        for strip in board.led_strips:
            line_obj = strip.line or (
                db.query(Line)
                .options(
                    joinedload(Line.best_trip_b).joinedload(Trip.terminus),
                    joinedload(Line.best_trip_f).joinedload(Trip.terminus),
                )
                .filter_by(id=strip.line_id)
                .first()
            )

            strip_data = {
                "id": strip.id,
                "boardId": strip.board_id,
                "lineId": strip.line_id,
                "lineAgencyName": strip.line_agency_name,
                "orderIndex": getattr(strip, "order_index", None),
            }

            if line_obj:
                terminus0 = line_obj.best_trip_b
                terminus1 = line_obj.best_trip_f
                term0_name = BoardService._resolve_terminus_name(terminus0, db)
                term1_name = BoardService._resolve_terminus_name(terminus1, db)
                strip_data["line"] = {
                    "id": line_obj.id,
                    "routeId": line_obj.route_id,
                    "shortName": line_obj.short_name,
                    "name": line_obj.short_name,
                    "longName": line_obj.long_name,
                    "routeType": line_obj.route_type,
                    "color": line_obj.color,
                    "textColor": line_obj.text_color,
                    "bestTrip0Id": line_obj.best_trip_0_id,
                    "bestTrip1Id": line_obj.best_trip_1_id,
                    "agencyName": line_obj.agency_name,
                    "terminus0Name": term0_name,
                    "terminus1Name": term1_name,
                }
                strip_data["color"] = line_obj.color
                strip_data["textColor"] = line_obj.text_color

            leds_sorted = sorted(strip.leds, key=lambda led: (led.ledstrip_index or 0, led.id or 0))
            strip_data["leds"] = [BoardService._build_led_data(led_obj) for led_obj in leds_sorted]

            # Backward compatibility with old payload shape: led1..ledN
            for led_obj in leds_sorted:
                if led_obj.ledstrip_index and led_obj.ledstrip_index > 0:
                    strip_data[f"led{led_obj.ledstrip_index}"] = BoardService._build_led_data(led_obj)

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
                agency_name=trip.terminus_agency_name,
            ).first()
            return stop.name if stop else None
        return None

    @staticmethod
    def _build_led_data(led_obj: Led):
        trip_stops_data = [
            {
                "tripStopId": ts.id,
                "ledId": led_obj.id,
                "vehicleIncoming": ts.vehicle_incoming,
                "stopStopId": ts.stop_stop_id,
                "stopAgencyName": ts.stop_agency_name,
                "stopName": ts.stop.name if ts.stop else None,
            }
            for ts in led_obj.trip_stops
        ]

        return {
            "ledId": led_obj.id,
            "ledstripIndex": led_obj.ledstrip_index,
            "customName": led_obj.custom_name,
            "type": led_obj.type,
            "ledColor": led_obj.led_color,
            "tripStops": trip_stops_data,
        }
