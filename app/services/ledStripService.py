from fastapi import HTTPException
from sqlalchemy.orm import Session
import sqlalchemy as sa
import re

from app.orm_models.board import Board, Led, LedStrip
from app.orm_models.gtfs import Line, Stop, Trip, TripStop


class LedStripService:
    HEX_COLOR_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")

    # ── Helpers utilitaires ──────────────────────────────────────────────────────

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
    def _get_max_led(board: Board) -> int:
        if board.board_type and board.board_type.max_led:
            return board.board_type.max_led
        return 12

    # ── CRUD publics ─────────────────────────────────────────────────────────────

    @staticmethod
    def create_led_strip(
        board_id: int,
        agency_name: str,
        line_id: int,
        central_stop_left_name: str,
        central_stop_right_name: str,
        led_color: str = None,
        pre_stop_left_name: str | None = None,
        pre_stop_left_minutes: int | None = None,
        pre_stop_right_name: str | None = None,
        pre_stop_right_minutes: int | None = None,
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

        max_led = LedStripService._get_max_led(board)

        if board.board_type and board.board_type.max_ledstrip is not None:
            current_count = (
                db.query(sa.func.count(LedStrip.id))
                .filter(LedStrip.board_id == board_id)
                .scalar()
            )
            if current_count >= board.board_type.max_ledstrip:
                raise HTTPException(
                    status_code=400,
                    detail=f"Maximum number of LED strips reached ({board.board_type.max_ledstrip}) for this board type",
                )

        next_order = order_index_override if order_index_override is not None else (
            (db.query(sa.func.max(LedStrip.order_index)).filter(LedStrip.board_id == board.id).scalar() or 0) + 1
        )

        trips = LedStripService._get_trips_by_direction(db, agency_name, line_id)
        if not trips[0] and not trips[1]:
            raise HTTPException(status_code=404, detail="Could not find any trips for this line")

        trip_stops = LedStripService._get_trip_stops_by_direction(db, trips)
        central_indexes = LedStripService._find_central_indexes(
            db, trip_stops, central_stop_left_name, central_stop_right_name,
        )
        pre_stop_overrides = LedStripService._resolve_pre_stop_overrides(
            db, trip_stops,
            pre_stop_left_name, pre_stop_left_minutes,
            pre_stop_right_name, pre_stop_right_minutes,
        )
        selected_stops = LedStripService._select_stops_around_central(
            db, trip_stops, central_indexes, pre_stop_overrides, max_led=max_led,
        )

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
            agency_name=agency_name,
            led_strip_id=led_strip.id,
            selected_stops=selected_stops,
            led_color=led_color_hex,
            pre_stop_overrides=pre_stop_overrides,
            max_led=max_led,
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
            trip_stops_payload = [
                {
                    "tripStopId": ts.id,
                    "stopStopId": ts.stop_stop_id,
                    "stopAgencyName": ts.stop_agency_name,
                    "stopName": (
                        LedStripService._clean_stop_name(ts.stop.name, ts.stop_agency_name)
                        if ts.stop else None
                    ),
                    "vehicleIncoming": ts.vehicle_incoming,
                }
                for ts in led.trip_stops
            ]
            leds_payload.append(
                {
                    "ledId": led.id,
                    "ledstripIndex": led.ledstrip_index,
                    "customName": led.custom_name,
                    "type": led.type,
                    "ledColor": led.led_color,
                    "preStopMinutes": led.pre_travel_minutes,
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
        pre_stop_left_name: str | None = None,
        pre_stop_left_minutes: int | None = None,
        pre_stop_right_name: str | None = None,
        pre_stop_right_minutes: int | None = None,
        db: Session = None,
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

        board = db.query(Board).filter_by(id=board_id).first()
        if not board:
            raise HTTPException(status_code=404, detail="Board not found")

        max_led = LedStripService._get_max_led(board)

        trips = LedStripService._get_trips_by_direction(db, agency_name, line_id)
        if not trips[0] and not trips[1]:
            raise HTTPException(status_code=404, detail="Could not find any trips for this line")

        trip_stops = LedStripService._get_trip_stops_by_direction(db, trips)
        central_indexes = LedStripService._find_central_indexes(
            db, trip_stops, central_stop_left_name, central_stop_right_name,
        )
        pre_stop_overrides = LedStripService._resolve_pre_stop_overrides(
            db, trip_stops,
            pre_stop_left_name, pre_stop_left_minutes,
            pre_stop_right_name, pre_stop_right_minutes,
        )
        selected_stops = LedStripService._select_stops_around_central(
            db, trip_stops, central_indexes, pre_stop_overrides, max_led=max_led,
        )

        strip.line_id = int(line_id)
        strip.line_agency_name = agency_name

        for led in list(strip.leds):
            led.trip_stops.clear()
            db.delete(led)
        db.flush()

        LedStripService._create_leds(
            db,
            agency_name=agency_name,
            led_strip_id=strip.id,
            selected_stops=selected_stops,
            led_color=led_color_hex,
            pre_stop_overrides=pre_stop_overrides,
            max_led=max_led,
        )

        db.commit()
        return {"message": "LED strip updated successfully", "led_strip_id": strip.id}

    @staticmethod
    def move_strip_to_slot(board_id: int, strip_id: int, order_index: int, db: Session):
        strip = db.query(LedStrip).filter_by(id=strip_id, board_id=board_id).first()
        if not strip:
            raise HTTPException(status_code=404, detail="LED strip not found")
        other = db.query(LedStrip).filter(
            LedStrip.board_id == board_id,
            LedStrip.order_index == order_index,
            LedStrip.id != strip_id,
        ).first()
        old_index = strip.order_index
        strip.order_index = order_index
        if other:
            other.order_index = old_index
        db.commit()
        return {"message": "OK"}

    @staticmethod
    def reorder_strips(board_id: int, ordered_ids: list[int], db: Session):
        for position, strip_id in enumerate(ordered_ids, start=1):
            strip = db.query(LedStrip).filter_by(id=strip_id, board_id=board_id).first()
            if strip:
                strip.order_index = position
        db.commit()
        return {"message": "Strips reordered"}

    @staticmethod
    def delete_led_strip(board_id: int, strip_id: int, db: Session):
        strip = db.query(LedStrip).filter_by(id=strip_id, board_id=board_id).first()
        if not strip:
            raise HTTPException(status_code=404, detail="LED strip not found")

        for led in list(strip.leds):
            led.trip_stops.clear()
            db.delete(led)

        db.delete(strip)
        db.commit()
        return {"message": "LED strip deleted successfully", "led_strip_id": strip_id}

    # ── Helpers privés ───────────────────────────────────────────────────────────

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
    def _resolve_pre_stop_overrides(
        db, trip_stops,
        pre_stop_left_name,  pre_stop_left_minutes,
        pre_stop_right_name, pre_stop_right_minutes,
    ) -> dict:
        """
        Retourne { direction: (TripStop | None, minutes | None) }.
        Le pre-stop tombe naturellement dans la séquence du trip.
        Les minutes sont une métadonnée attachée au LED correspondant.
        """
        overrides = {0: (None, None), 1: (None, None)}
        pairs = {
            0: (pre_stop_left_name,  pre_stop_left_minutes),
            1: (pre_stop_right_name, pre_stop_right_minutes),
        }

        for direction, (name, minutes) in pairs.items():
            if not name or not trip_stops[direction]:
                continue
            target = name.strip().lower()
            found = False
            for i in range(len(trip_stops[direction]) - 1, -1, -1):
                ts = trip_stops[direction][i]
                stop = db.query(Stop).filter_by(
                    stop_id=ts.stop_stop_id, agency_name=ts.stop_agency_name,
                ).first()
                if stop and stop.name.strip().lower() == target:
                    overrides[direction] = (ts, minutes)
                    found = True
                    break
            if not found:
                raise HTTPException(
                    status_code=404,
                    detail=f'Pre-stop "{name}" not found in direction {direction}',
                )

        return overrides

    @staticmethod
    def _select_stops_around_central(
        db, trip_stops, central_indexes, pre_stop_overrides=None, max_led: int = 12,
    ):
        selected_stops = {}

        only_one_direction = (central_indexes[0] is None) != (central_indexes[1] is None)
        stops_per_side = max_led // 2
        stops_to_take = max_led if only_one_direction else stops_per_side

        for direction in [0, 1]:
            if central_indexes[direction] is None:
                selected_stops[direction] = None
                continue

            central_idx = central_indexes[direction]
            all_stops = trip_stops[direction]

            pre_ts = None
            pre_idx = None
            if pre_stop_overrides:
                pre_ts, _ = pre_stop_overrides.get(direction, (None, None))
                if pre_ts:
                    pre_idx = next(
                        (i for i, ts in enumerate(all_stops) if ts.id == pre_ts.id), None
                    )

            if pre_idx is not None:
                start = max(0, pre_idx - (stops_to_take - 2))
                selected = list(all_stops[start : pre_idx + 1])
                while len(selected) < stops_to_take - 1:
                    selected.insert(0, None)
                selected.append(all_stops[central_idx])
                if direction == 1:
                    selected = list(reversed(selected))
            else:
                start = max(0, central_idx - (stops_to_take - 1))
                selected = list(all_stops[start : central_idx + 1])
                while len(selected) < stops_to_take:
                    selected.insert(0, None)
                if direction == 1:
                    selected = list(reversed(selected))

            selected_stops[direction] = selected[:stops_to_take]

        return selected_stops

    @staticmethod
    def _create_leds(
        db,
        agency_name: str,
        led_strip_id: int,
        selected_stops,
        led_color: str,
        pre_stop_overrides=None,
        max_led: int = 12,
    ):
        half = max_led // 2
        only0 = selected_stops[1] is None
        only1 = selected_stops[0] is None

        # Map TripStop.id → minutes pour identifier le pre-stop
        pre_minutes_by_ts_id: dict[int, int] = {}
        if pre_stop_overrides:
            for direction in [0, 1]:
                override_ts, override_minutes = pre_stop_overrides.get(direction, (None, None))
                if override_ts and override_minutes is not None:
                    pre_minutes_by_ts_id[override_ts.id] = override_minutes

        for i in range(max_led):
            if not only0 and not only1:
                if i < half:
                    direction, stop_idx = 0, i
                    is_c_left  = i == half - 1
                    is_c_right = False
                    is_left    = i < half - 1
                    is_right   = False
                else:
                    direction, stop_idx = 1, i - half
                    is_c_left  = False
                    is_c_right = i == half
                    is_left    = False
                    is_right   = i > half
            elif only0:
                direction, stop_idx = 0, i
                is_c_left  = i == max_led - 1
                is_c_right = False
                is_left    = i < max_led - 1
                is_right   = False
            else:
                direction, stop_idx = 1, i
                is_c_left  = False
                is_c_right = i == max_led - 1
                is_left    = False
                is_right   = i < max_led - 1

            ts = selected_stops[direction][stop_idx] if selected_stops[direction] else None
            pre_travel_minutes = pre_minutes_by_ts_id.get(ts.id) if ts else None

            custom_name = None
            if ts:
                stop = db.query(Stop).filter_by(
                    stop_id=ts.stop_stop_id,
                    agency_name=agency_name,
                ).first()
                custom_name = (
                    LedStripService._clean_stop_name(stop.name, agency_name)
                    if stop and stop.name
                    else ts.stop_stop_id
                )

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
                pre_travel_minutes=pre_travel_minutes,
            )
            db.add(led)
            db.flush()

            if ts:
                led.trip_stops.append(ts)

    @staticmethod
    def _clean_stop_name(name: str, agency_name: str = "") -> str:
        if not name:
            return ""

        name = " ".join(name.split())
        cleaned = re.sub(r'\s*\(.*?\)\s*$', '', name).strip()

        if agency_name == 'TEC' and len(cleaned.split()) >= 2:
            cleaned = re.sub(
                r'^(?:[A-ZÀ-ÿ]+(?:[\s\-][A-ZÀ-ÿ]+)*)\s+',
                '',
                cleaned,
            )

        print(f"Cleaned stop name: '{cleaned}' from original '{name}'")
        return cleaned.strip()