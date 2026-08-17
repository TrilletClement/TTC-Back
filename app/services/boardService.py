import logging

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.content_filter import assert_clean_text
from app.orm_models.auth import User
from app.orm_models.board import Board, BoardType, Led, LedStrip
from app.orm_models.gtfs import Line, Stop, Trip
from app.orm_models.price import BoardTypePrice, PriceVersion
from app.repositories.board_repo import BoardRepository

logger = logging.getLogger(__name__)

class BoardService:
    BOARD_LIMIT = 10

    def __init__(self, repo: BoardRepository):
        self.repo = repo

    # ── public methods ────────────────────────────────────────────────────────

    def get_boards(self, current_user: User, owner_email: str | None = None):
        is_admin = "admin" in [role.name for role in current_user.roles]

        if is_admin and owner_email:
            owner = self.repo.get_user_by_email(owner_email)
            owner_id = owner.id if owner else -1
        else:
            owner_id = current_user.id

        boards = self.repo.get_boards_for_owner(owner_id)
        return [
            {
                "id": b.id,
                "name": b.name,
                "owner_id": b.owner_id,
                "type": {
                    "id": b.board_type.id,
                    "name": b.board_type.name,
                    "maxLedstrip": b.board_type.max_ledstrip,
                } if b.board_type else None,
                "ledstripCount": len(b.led_strips),
                "device": {
                    "id": b.esp32_devices[0].id,
                    "name": b.esp32_devices[0].name or b.esp32_devices[0].mac_address,
                } if b.esp32_devices else None,
                "lines": BoardService._build_board_lines_summary(b),
            }
            for b in boards
        ]

    @staticmethod
    def _resolve_line_color(strip: LedStrip, line_obj: Line) -> str:
        # NULL line_color means "use the line's official GTFS color" — see
        # LedStrip.line_color's docstring in orm_models/board.py.
        return strip.line_color or line_obj.color

    @staticmethod
    def _build_board_lines_summary(board: Board) -> list[dict]:
        # One badge per distinct line on the board (not per strip — a line
        # can have two strips, e.g. both directions). Keyed on (line_id,
        # agency_name) like LedStrip.line's own join condition, since line
        # ids aren't unique across agencies.
        seen: dict[tuple[int, str], dict] = {}
        for strip in board.led_strips:
            line_obj = strip.line
            if not line_obj:
                continue
            key = (strip.line_id, strip.line_agency_name)
            if key in seen:
                continue
            seen[key] = {
                "lineId": line_obj.id,
                "shortName": line_obj.short_name or str(line_obj.id),
                "color": BoardService._resolve_line_color(strip, line_obj),
                "textColor": line_obj.text_color,
            }
        return list(seen.values())

    def get_board_types(self):
        latest_version = self.repo.get_latest_price_version()

        prices: dict[int, BoardTypePrice] = {}
        if latest_version:
            for p in self.repo.get_prices_for_version(latest_version.id):
                prices[p.board_type_id] = p

        types = self.repo.get_all_board_types()
        return [
            {
                "id": t.id,
                "name": t.name,
                "maxLed": t.max_led,
                "maxLedstrip": t.max_ledstrip,
                "basePriceCents": prices[t.id].base_price_cents if t.id in prices else None,
                "reducedPriceCents": prices[t.id].reduced_price_cents if t.id in prices else None,
            }
            for t in types
        ]

    def create_board(self, name: str, current_user: User, board_type_id: int | None = None):
        name = (name or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Board name is required")
        assert_clean_text(name, "BOARD_NAME", max_length=100)

        active_count = self.repo.count_active_boards(current_user.id)
        if active_count >= self.BOARD_LIMIT:
            raise HTTPException(
                status_code=409,
                detail=f"Board limit reached ({self.BOARD_LIMIT} active boards maximum)",
            )

        if self.repo.find_duplicate_name(current_user.id, name):
            raise HTTPException(status_code=409, detail="You already have a board with this name")

        if board_type_id is not None:
            if not self.repo.get_board_type_by_id(board_type_id):
                raise HTTPException(status_code=400, detail="Invalid board type")

        new_board = Board(name=name, owner=current_user, board_type_id=board_type_id)
        new_board = self.repo.add(new_board)
        return {"message": "Board added successfully!", "board_id": new_board.id}

    def rename_board(self, board_id: int, new_name: str, current_user: User) -> dict:
        new_name = (new_name or "").strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="Board name cannot be empty")
        assert_clean_text(new_name, "BOARD_NAME", max_length=100)

        board = self.repo.get_board_by_id(board_id)
        if not board or board.archived:
            raise HTTPException(status_code=404, detail="Board not found")

        is_admin = "admin" in [r.name for r in current_user.roles]
        if not is_admin and board.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="Unauthorized")

        if board.name.lower() != new_name.lower() and self.repo.find_duplicate_name(board.owner_id, new_name):
            raise HTTPException(
                status_code=409,
                detail="You already have a board with this name",
            )

        board.name = new_name
        self.repo.db.commit()
        return {"id": board_id, "name": new_name}

    def delete_board(self, board_id: int, current_user: User, force_unlink_devices: bool = False):
        from app.orm_models.device import ESP32Device

        board = self.repo.get_board_with_strips(board_id)
        if not board:
            raise HTTPException(status_code=404, detail="Board not found")

        is_admin = "admin" in [role.name for role in current_user.roles]
        if not is_admin and board.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="Unauthorized")

        linked_devices = self.repo.get_devices_linked_to_board(board_id)
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

        for device in linked_devices:
            device.board_id = None

        if self.repo.board_has_orders(board_id):
            self.repo.archive(board)
            return {"archived": True, "id": board_id, "message": "Board archived (linked orders preserved)"}

        self.repo.delete_cascade(board)
        return {"archived": False, "id": board_id, "message": "Board deleted successfully"}

    def get_board_details(self, board_id: int, current_user: User):
        is_admin = "admin" in [role.name for role in current_user.roles]
        board = self.repo.get_board_details_full(board_id)

        if not board:
            raise HTTPException(status_code=404, detail="Board not found")
        if not is_admin and board.owner_id != current_user.id:
            raise HTTPException(status_code=404, detail="Board not found")

        led_strips_data = self._build_led_strips_data(board, self.repo.db)
        bt = board.board_type

        board_price = None
        if bt:
            current_version = self.repo.get_latest_price_version()
            if current_version:
                board_price = self.repo.get_price_for_board_type(current_version.id, bt.id)

        return {
            "id": board.id,
            "name": board.name,
            "ownerId": board.owner_id,
            "boardTypeId": bt.id if bt else None,
            "boardTypeName": bt.name if bt else None,
            "boardTypeMaxLed": bt.max_led if bt else None,
            "boardTypeMaxLedstrip": bt.max_ledstrip if bt else None,
            "boardTypeMaxWidthMm": bt.max_width_mm if bt else None,
            "boardTypeMaxHeightMm": bt.max_height_mm if bt else None,
            "boardTypeDeltaXMm": bt.delta_x_mm if bt else None,
            "boardTypeDeltaYMm": bt.delta_y_mm if bt else None,
            "boardTypeFrameInnerXMm": bt.frame_inner_x_mm if bt else None,
            "boardTypeFrameInnerYMm": bt.frame_inner_y_mm if bt else None,
            "boardTypeFrameOuterXMm": bt.frame_outer_x_mm if bt else None,
            "boardTypeFrameOuterYMm": bt.frame_outer_y_mm if bt else None,
            "boardTypeFrameOverlapXMm": bt.frame_overlap_x_mm if bt else None,
            "boardTypeFrameOverlapYMm": bt.frame_overlap_y_mm if bt else None,
            "basePriceCents": board_price.base_price_cents if board_price else None,
            "reducedPriceCents": board_price.reduced_price_cents if board_price else None,
            "ledStrips": led_strips_data,
        }

    def get_board_status(self, board_id: int, current_user: User):
        is_admin = "admin" in [role.name for role in current_user.roles]
        board = self.repo.get_board_details_full(board_id)

        if not board:
            raise HTTPException(status_code=404, detail="Board not found")
        if not is_admin and board.owner_id != current_user.id:
            raise HTTPException(status_code=404, detail="Board not found")

        return {"ledStrips": self._build_led_strips_status(board, self.repo.db)}

    # ── interval-based realtime helpers ──────────────────────────────────────

    @staticmethod
    def _collect_trip_stop_ids(board) -> list[int]:
        ids = []
        for strip in board.led_strips:
            for led in strip.leds:
                for ts in led.trip_stops:
                    ids.append(ts.id)
        return ids

    @staticmethod
    def _get_interval_active_trip_stop_ids(db: Session, trip_stop_ids: list[int]) -> dict[int, bool]:
        if not trip_stop_ids:
            return {}

        try:
            # bool_or: when several vehicles are inbound to the same stop at once
            # (tracked + untracked), one realtime interval is enough — without the
            # aggregate, the flag depended on arbitrary row order and flickered.
            rows = db.execute(sa.text("""
                SELECT canonical_trip_stop_id, bool_or(is_realtime) AS is_realtime
                FROM active_incoming_intervals
                WHERE canonical_trip_stop_id = ANY(:ts_ids)
                  AND EXTRACT(EPOCH FROM NOW())::bigint BETWEEN led_on_from AND led_on_until
                GROUP BY canonical_trip_stop_id
            """), {"ts_ids": trip_stop_ids}).all()

            return {row.canonical_trip_stop_id: row.is_realtime for row in rows}

        except Exception:
            logger.exception("active_incoming_intervals query failed — all LEDs fall back to off/theoretical")
            return {}

    # ── LED strip / LED builders ──────────────────────────────────────────────

    @staticmethod
    def _build_led_strips_data(board, db: Session):
        trip_stop_ids = BoardService._collect_trip_stop_ids(board)
        interval_active_ids = BoardService._get_interval_active_trip_stop_ids(db, trip_stop_ids)

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
                "integratedTerminus": bool(getattr(strip, "integrated_terminus", False)),
                "rtOnly": bool(getattr(strip, "rt_only", False)),
                "customTerminusLeftName":  getattr(strip, "custom_terminus_left_name",  None),
                "customTerminusRightName": getattr(strip, "custom_terminus_right_name", None),
            }

            if line_obj:
                term0_name = BoardService._resolve_terminus_name(line_obj.best_trip_b, db)
                term1_name = BoardService._resolve_terminus_name(line_obj.best_trip_f, db)
                strip_data["line"] = {
                    "id": line_obj.id,
                    "shortName": line_obj.short_name,
                    "color": line_obj.color,
                    "textColor": line_obj.text_color,
                    "agencyName": line_obj.agency_name,
                    "terminus0Name": term0_name,
                    "terminus1Name": term1_name,
                }
                strip_data["color"] = BoardService._resolve_line_color(strip, line_obj)
                strip_data["textColor"] = line_obj.text_color

            rt_only = bool(getattr(strip, "rt_only", False))
            leds_sorted = sorted(strip.leds, key=lambda led: (led.ledstrip_index or 0, led.id or 0))
            strip_data["leds"] = [
                BoardService._build_led_data(led_obj, interval_active_ids, rt_only)
                for led_obj in leds_sorted
            ]

            led_strips_data.append(strip_data)

        return led_strips_data

    @staticmethod
    def _build_led_strips_status(board, db: Session):
        """Dynamic-only counterpart to `_build_led_strips_data` — no line/pricing/geometry."""
        trip_stop_ids = BoardService._collect_trip_stop_ids(board)
        interval_active_ids = BoardService._get_interval_active_trip_stop_ids(db, trip_stop_ids)

        led_strips_status = []
        for strip in board.led_strips:
            rt_only = bool(getattr(strip, "rt_only", False))
            leds_sorted = sorted(strip.leds, key=lambda led: (led.ledstrip_index or 0, led.id or 0))
            led_strips_status.append({
                "id": strip.id,
                "leds": [
                    BoardService._build_led_status(led_obj, interval_active_ids, rt_only)
                    for led_obj in leds_sorted
                ],
            })

        return led_strips_status

    @staticmethod
    def _build_led_status(led_obj: Led, interval_active_ids: dict[int, bool] | None = None,
                           rt_only: bool = False):
        _interval = interval_active_ids or {}

        trip_stops_status = []
        for ts in led_obj.trip_stops:
            legacy_incoming = bool(ts.vehicle_incoming)
            interval_incoming = ts.id in _interval
            is_realtime_flag = legacy_incoming or (interval_incoming and _interval[ts.id])
            is_on = is_realtime_flag if rt_only else (legacy_incoming or interval_incoming)

            trip_stops_status.append({
                "tripStopId":      ts.id,
                "vehicleIncoming": legacy_incoming,
                "intervalActive":  interval_incoming,
                "isOn":            is_on,
                "isRealtime":      is_realtime_flag,
            })

        return {
            "ledId": led_obj.id,
            "isOn":  any(ts["isOn"] for ts in trip_stops_status),
            "tripStops": trip_stops_status,
        }

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
    def _build_led_data(led_obj: Led, interval_active_ids: dict[int, bool] | None = None,
                        rt_only: bool = False):
        _interval = interval_active_ids or {}

        trip_stops_data = []
        for ts in led_obj.trip_stops:
            legacy_incoming = bool(ts.vehicle_incoming)
            interval_incoming = ts.id in _interval
            # legacy_incoming means STIB confirmed vehicle position → always realtime
            # for interval-only stops, use the matview's is_realtime flag (TEC/De Lijn = False, SNCB = depends)
            is_realtime_flag = legacy_incoming or (interval_incoming and _interval[ts.id])
            # rt_only strips ignore pure-schedule intervals: LED lights only on confirmed RT
            is_on = is_realtime_flag if rt_only else (legacy_incoming or interval_incoming)

            trip_stops_data.append({
                "tripStopId":      ts.id,
                "ledId":           led_obj.id,
                "vehicleIncoming": legacy_incoming,
                "intervalActive":  interval_incoming,
                "isOn":            is_on,
                "isRealtime":      is_realtime_flag,
                "stopStopId":      ts.stop_stop_id,
                "stopAgencyName":  ts.stop_agency_name,
                "stopName":        ts.stop.name if ts.stop else None,
            })

        led_is_on = any(ts["isOn"] for ts in trip_stops_data)

        return {
            "ledId":          led_obj.id,
            "ledstripIndex":  led_obj.ledstrip_index,
            "customName":     led_obj.custom_name,
            "customSubname":  led_obj.custom_subname,
            "type":           led_obj.type,
            "ledColor":       led_obj.led_color,
            "preStopMinutes": led_obj.pre_travel_minutes,
            "isOn":           led_is_on,
            "tripStops":      trip_stops_data,
        }