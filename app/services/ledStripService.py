from fastapi import HTTPException
from sqlalchemy.orm import Session
import sqlalchemy as sa
import re

from app.orm_models.board import Board, Led, LedStrip
from app.orm_models.gtfs import Line, Stop, Trip, TripStop


class LedStripService:
    HEX_COLOR_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")

    @staticmethod
    def _normalize_hex_color(value: str | None) -> str:
        if value is None:
            return "#00FF00"
        color = value.strip()
        if not LedStripService.HEX_COLOR_RE.fullmatch(color):
            raise HTTPException(
                status_code=400,
                detail="Invalid led_color. Expected HEX RGB like #00FF00",
            )
        if not color.startswith("#"):
            color = f"#{color}"
        return color.upper()

    @staticmethod
    def create_led_strip(
        board_id: int,
        agency_name: str,
        line_id: int,
        central_stop_left_name: str,
        central_stop_right_name: str,
        led_color: str = None,
        order_index_override: int = None,
        db: Session = None,
    ):
        if not all([agency_name, line_id]) or (not central_stop_left_name and not central_stop_right_name):
            raise HTTPException(
                status_code=400,
                detail="agency_name, line_id, and (central_stop_left_name or central_stop_right_name) are required",
            )

        led_color_hex = LedStripService._normalize_hex_color(led_color)

        board = db.query(Board).filter_by(id=board_id).first()
        if not board:
            raise HTTPException(status_code=404, detail="Board not found")

        next_order = order_index_override or (
            (db.query(sa.func.max(LedStrip.order_index)).filter(LedStrip.board_id == board.id).scalar() or 0) + 1
        )

        trips = LedStripService._get_trips_by_direction(db, agency_name, line_id)
        if not trips[0] and not trips[1]:
            raise HTTPException(status_code=404, detail="Could not find any trips for this line")

        trip_stops = LedStripService._get_trip_stops_by_direction(db, trips)
        central_indexes = LedStripService._find_central_indexes(
            db,
            trip_stops,
            central_stop_left_name,
            central_stop_right_name,
        )
        selected_stops = LedStripService._select_stops_around_central(db, trip_stops, central_indexes)

        led_strip = LedStrip(
            board_id=board.id,
            line_id=line_id,
            line_agency_name=agency_name,
            order_index=next_order,
        )
        db.add(led_strip)
        db.flush()

        LedStripService._create_leds(
            db,
            led_strip_id=led_strip.id,
            selected_stops=selected_stops,
            led_color=led_color_hex,
        )

        db.commit()
        return {"message": "LED strip created successfully", "led_strip_id": led_strip.id}

    @staticmethod
    def get_led_strip_by_id(board_id: int, strip_id: int, db: Session):
        strip = db.query(LedStrip).filter_by(id=strip_id, board_id=board_id).first()
        if not strip:
            raise HTTPException(status_code=404, detail="LED strip not found")

        leds_sorted = sorted(strip.leds, key=lambda led: (led.ledstrip_index or 0, led.id or 0))
        leds_payload = []
        for led in leds_sorted:
            trip_stops_payload = []
            for ts in led.trip_stops:
                trip_stops_payload.append(
                    {
                        "tripStopId": ts.id,
                        "stopStopId": ts.stop_stop_id,
                        "stopAgencyName": ts.stop_agency_name,
                        "stopName": ts.stop.name if ts.stop else None,
                        "vehicleIncoming": ts.vehicle_incoming,
                    }
                )

            leds_payload.append(
                {
                    "ledId": led.id,
                    "ledstripIndex": led.ledstrip_index,
                    "customName": led.custom_name,
                    "type": led.type,
                    "ledColor": led.led_color,
                    "tripStops": trip_stops_payload,
                }
            )

        return {
            "id": strip.id,
            "boardId": strip.board_id,
            "board_id": strip.board_id,
            "lineId": strip.line_id,
            "line_id": strip.line_id,
            "lineAgencyName": strip.line_agency_name,
            "agency_name": strip.line_agency_name,
            "orderIndex": strip.order_index,
            "order_index": strip.order_index,
            "leds": leds_payload,
        }

    @staticmethod
    def update_led_strip(
        board_id: int,
        strip_id: int,
        agency_name: str,
        line_id: int,
        central_stop_left_name: str | None,
        central_stop_right_name: str | None,
        led_color: str | None,
        db: Session,
    ):
        if not all([agency_name, line_id]) or (not central_stop_left_name and not central_stop_right_name):
            raise HTTPException(
                status_code=400,
                detail="agency_name, line_id, and (central_stop_left_name or central_stop_right_name) are required",
            )

        led_color_hex = LedStripService._normalize_hex_color(led_color)

        strip = db.query(LedStrip).filter_by(id=strip_id, board_id=board_id).first()
        if not strip:
            raise HTTPException(status_code=404, detail="LED strip not found")

        trips = LedStripService._get_trips_by_direction(db, agency_name, line_id)
        if not trips[0] and not trips[1]:
            raise HTTPException(status_code=404, detail="Could not find any trips for this line")

        trip_stops = LedStripService._get_trip_stops_by_direction(db, trips)
        central_indexes = LedStripService._find_central_indexes(
            db,
            trip_stops,
            central_stop_left_name,
            central_stop_right_name,
        )
        selected_stops = LedStripService._select_stops_around_central(db, trip_stops, central_indexes)

        strip.line_id = int(line_id)
        strip.line_agency_name = agency_name

        for led in list(strip.leds):
            led.trip_stops.clear()
            db.delete(led)
        db.flush()

        LedStripService._create_leds(
            db,
            led_strip_id=strip.id,
            selected_stops=selected_stops,
            led_color=led_color_hex,
        )

        db.commit()
        return {"message": "LED strip updated successfully", "led_strip_id": strip.id}

    @staticmethod
    def _get_trips_by_direction(db, agency_name, line_id):
        line = db.query(Line).filter_by(id=line_id, agency_name=agency_name).first()
        if not line:
            raise HTTPException(
                status_code=404,
                detail=f"Line with id {line_id} and agency_name {agency_name} not found",
            )
        return {
            0: db.query(Trip).filter_by(id=line.best_trip_0_id).first(),
            1: db.query(Trip).filter_by(id=line.best_trip_1_id).first(),
        }

    @staticmethod
    def _get_trip_stops_by_direction(db, trips):
        result = {}
        for direction in [0, 1]:
            if trips[direction]:
                result[direction] = (
                    db.query(TripStop)
                    .filter_by(trip_id=trips[direction].id)
                    .order_by(TripStop.sequence)
                    .all()
                )
            else:
                result[direction] = []
        return result

    @staticmethod
    def _find_central_indexes(db, trip_stops, central_stop_left_name, central_stop_right_name):
        central_indexes = {}

        for direction in [0, 1]:
            if not trip_stops[direction]:
                central_indexes[direction] = None
                continue

            target_name = central_stop_left_name if direction == 0 else central_stop_right_name
            if not target_name:
                central_indexes[direction] = None
                continue

            central_index = None
            for i in range(len(trip_stops[direction]) - 1, -1, -1):
                ts = trip_stops[direction][i]
                stop = db.query(Stop).filter_by(
                    stop_id=ts.stop_stop_id,
                    agency_name=ts.stop_agency_name,
                ).first()
                if stop and stop.name.strip().lower() == target_name.strip().lower():
                    central_index = i
                    break

            if central_index is None:
                raise HTTPException(
                    status_code=404,
                    detail=f'Central stop "{target_name}" not found in trip direction {direction}',
                )
            central_indexes[direction] = central_index

        return central_indexes

    @staticmethod
    def _select_stops_around_central(db, trip_stops, central_indexes):
        selected_stops = {}

        only_one_direction = (central_indexes[0] is None) != (central_indexes[1] is None)
        stops_to_take = 12 if only_one_direction else 6

        for direction in [0, 1]:
            if central_indexes[direction] is None:
                selected_stops[direction] = None
            else:
                start = max(0, central_indexes[direction] - (stops_to_take - 1))
                selected = trip_stops[direction][start : central_indexes[direction] + 1]

                if direction == 1:
                    selected = list(reversed(selected))

                while len(selected) < stops_to_take:
                    selected.insert(0, None)

                if len(selected) > stops_to_take:
                    selected = selected[-stops_to_take:]

                selected_stops[direction] = selected

        return selected_stops

    @staticmethod
    def _create_leds(db, led_strip_id: int, selected_stops, led_color: str):
        only0 = selected_stops[1] is None
        only1 = selected_stops[0] is None

        for i in range(12):
            if not only0 and not only1:
                if i < 6:
                    direction, stop_idx = 0, i
                    is_c_left = i == 5
                    is_c_right = False
                    is_left = i < 5
                    is_right = False
                else:
                    direction, stop_idx = 1, i - 6
                    is_c_left = False
                    is_c_right = i == 6
                    is_left = False
                    is_right = i > 6
            elif only0:
                direction, stop_idx = 0, i
                is_c_left = i == 11
                is_c_right = False
                is_left = i < 11
                is_right = False
            else:
                direction, stop_idx = 1, i
                is_c_left = False
                is_c_right = i == 11
                is_left = False
                is_right = i < 11

            ts = selected_stops[direction][stop_idx] if selected_stops[direction] else None

            custom_name = None
            if ts:
                stop = db.query(Stop).filter_by(
                    stop_id=ts.stop_stop_id,
                    agency_name=ts.stop_agency_name,
                ).first()
                custom_name = stop.name if stop else ts.stop_stop_id

            if is_c_left:
                led_type = "c_left"
            elif is_c_right:
                led_type = "c_right"
            elif is_left:
                led_type = "left"
            else:
                led_type = "right"

            led = Led(
                ledstrip_id=led_strip_id,
                ledstrip_index=i + 1,
                custom_name=custom_name,
                type=led_type,
                led_color=led_color,
            )
            db.add(led)
            db.flush()

            if ts:
                led.trip_stops.append(ts)
