from fastapi import HTTPException
from sqlalchemy.orm import Session
import sqlalchemy as sa
from shared.models import Board, Trip, TripStop, Stop, LedStrip, Led, Line

class LedStripService:
    ALLOWED_COLORS = {'red', 'blue', 'white', 'green', 'yellow'}

    @staticmethod
    def create_led_strip(
        board_id: int,
        agency_name: str,
        line_id: int,
        central_stop_left_name: str,
        central_stop_right_name: str,
        led_color: str = None,
        order_index_override: int = None,
        db: Session = None
    ):
        if not all([agency_name, line_id]) or (not central_stop_left_name and not central_stop_right_name):
            raise HTTPException(status_code=400,
                                detail="agency_name, line_id, and (central_stop_left_name or central_stop_right_name) are required")

        if led_color and led_color not in LedStripService.ALLOWED_COLORS:
            raise HTTPException(status_code=400,
                                detail=f"Invalid led_color. Allowed: {', '.join(sorted(LedStripService.ALLOWED_COLORS))}")
    
        board = db.query(Board).filter_by(id=board_id).first()

        if not board:
            raise HTTPException(status_code=404, detail="Board not found")

        next_order = order_index_override or ((db.query(sa.func.max(LedStrip.order_index))
                                              .filter(LedStrip.board_id == board.id).scalar() or 0) + 1)

        trips = LedStripService._get_trips_by_direction(db, agency_name, line_id)
        if not trips[0] or not trips[1]:
            raise HTTPException(status_code=404, detail="Could not find trips in both directions")

        trip_stops = LedStripService._get_trip_stops_by_direction(db, trips)
        central_indexes = LedStripService._find_central_indexes(db, trip_stops,
                                                                central_stop_left_name,
                                                                central_stop_right_name)
        selected_stops = LedStripService._select_stops_around_central(db, trip_stops, central_indexes)

        led_strip = LedStrip(
            board_id=board.id,
            line_id=line_id,
            line_agency_name=agency_name,
            order_index=next_order,
            led_color=led_color or 'red'
        )
        db.add(led_strip)
        db.flush()

        led_ids = LedStripService._create_leds(db, selected_stops)
        for idx, led_id in enumerate(led_ids):
            setattr(led_strip, f'led{idx+1}', led_id)

        db.commit()
        return {"message": "LED strip created successfully", "led_strip_id": led_strip.id}

    # ----- fonctions internes conservées -----
    @staticmethod
    def _get_trips_by_direction(db, agency_name, line_id):
        line = db.query(Line).filter_by(id=line_id, agency_name=agency_name).first()
        if not line:
            raise HTTPException(status_code=404,
                                detail=f"Line with id {line_id} and agency_name {agency_name} not found")
        return {
            0: db.query(Trip).filter_by(id=line.best_trip_0_id).first(),
            1: db.query(Trip).filter_by(id=line.best_trip_1_id).first()
        }

    @staticmethod
    def _get_trip_stops_by_direction(db, trips):
        return {dir: db.query(TripStop).filter_by(trip_id=trips[dir].id)
                .order_by(TripStop.sequence).all() for dir in [0, 1]}

    @staticmethod
    def _find_central_indexes(db, trip_stops, central_stop_left_name, central_stop_right_name):
        central_indexes = {}
        for dir in [0, 1]:
            if not central_stop_left_name and dir == 0:
                central_indexes[0] = 0
                continue
            if not central_stop_right_name and dir == 1:
                central_indexes[1] = 0
                continue
            central_index = next((i for i, ts in enumerate(trip_stops[dir])
                                  if (s := db.query(Stop).filter_by(
                                        stop_id=ts.stop_stop_id,
                                        agency_name=ts.stop_agency_name).first()) and
                                  ((dir == 0 and s.name.strip().lower() == central_stop_left_name.strip().lower()) or
                                   (dir == 1 and s.name.strip().lower() == central_stop_right_name.strip().lower()))), None)
            if central_index is None:
                raise HTTPException(status_code=404,
                                    detail=f'Central stop name not found in trip direction {dir}')
            central_indexes[dir] = central_index
        return central_indexes

    @staticmethod
    def _select_stops_around_central(db, trip_stops, central_indexes):
        selected_stops = {}
        for dir in [0, 1]:
            if central_indexes[dir] == 0:
                selected_stops[dir] = None
            else:
                start = max(0, central_indexes[dir] - 5 if dir == 0 else central_indexes[dir] - 5)
                selected = trip_stops[dir][start:central_indexes[dir]+1]
                selected_stops[dir] = selected if dir == 0 else list(reversed(selected))
        # Pad with None to 6 or 12 LEDs
        for dir in [0, 1]:
            if selected_stops[dir] is not None:
                while len(selected_stops[dir]) < (12 if (selected_stops[1] is None or selected_stops[0] is None) else 6):
                    selected_stops[dir].insert(0 if dir == 0 else len(selected_stops[dir]), None)
        return selected_stops

    @staticmethod
    def _create_leds(db, selected_stops):
        led_ids = []
        only0 = selected_stops[1] is None
        only1 = selected_stops[0] is None

        for i in range(12):
            if not only0 and not only1:
                dir, stop_idx = (0, i) if i < 6 else (1, i - 6)
                is_c_left = i == 5
                is_c_right = i == 6
                is_left = i < 5
                is_right = i >= 7
            elif only0:
                dir, stop_idx = 0, i
                is_c_left = i == 11
                is_c_right = False
                is_left = i < 11
                is_right = False
            else:
                dir, stop_idx = 1, i - 12
                is_c_left = False
                is_c_right = i == 0
                is_left = False
                is_right = i > 0

            ts = selected_stops[dir][stop_idx]
            custom_name = None
            if ts:
                stop = db.query(Stop).filter_by(
                    stop_id=ts.stop_stop_id,
                    agency_name=ts.stop_agency_name).first()
                custom_name = stop.name if stop else ts.stop_stop_id

            led = Led(custom_name=custom_name,
                      type='c_left' if is_c_left else ('c_right' if is_c_right else ('left' if is_left else 'right')))
            db.add(led)
            db.flush()
            if ts:
                led.trip_stops.append(ts)
            led_ids.append(led.id)
        return led_ids