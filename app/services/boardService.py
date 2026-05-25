import logging
import time

from fastapi import HTTPException

logger = logging.getLogger(__name__)
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload
import sqlalchemy as sa

from app.orm_models.auth import User
from app.orm_models.board import Board, BoardType, Led, LedStrip
from app.orm_models.price import BoardTypePrice, PriceVersion
from app.orm_models.gtfs import Line, Stop, Trip


class BoardService:
    @staticmethod
    def get_boards(current_user: User, db: Session, owner_email: str | None = None):
        is_admin = "admin" in [role.name for role in current_user.roles]

        if is_admin and owner_email:
            owner = db.query(User).filter(func.lower(User.email) == owner_email.strip().lower()).first()
            owner_id = owner.id if owner else -1
        else:
            owner_id = current_user.id

        boards = db.query(Board).filter_by(owner_id=owner_id, archived=False).all()
        return [{"id": b.id, "name": b.name, "owner_id": b.owner_id} for b in boards]

    @staticmethod
    def get_board_types(db: Session):
        latest_version = (
            db.query(PriceVersion)
            .order_by(PriceVersion.created_at.desc())
            .first()
        )

        prices: dict[int, BoardTypePrice] = {}
        if latest_version:
            for p in db.query(BoardTypePrice).filter_by(price_version_id=latest_version.id).all():
                prices[p.board_type_id] = p

        types = db.query(BoardType).all()
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

    BOARD_LIMIT = 10

    @staticmethod
    def create_board(name: str, current_user: User, db: Session, board_type_id: int | None = None):
        name = (name or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Board name is required")

        active_count = db.query(Board).filter_by(owner_id=current_user.id, archived=False).count()
        if active_count >= BoardService.BOARD_LIMIT:
            raise HTTPException(
                status_code=409,
                detail=f"Board limit reached ({BoardService.BOARD_LIMIT} active boards maximum)"
            )

        duplicate = db.query(Board).filter(
            Board.owner_id == current_user.id,
            Board.archived == False,
            func.lower(Board.name) == name.lower(),
        ).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="You already have a board with this name")

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
        from sqlalchemy.orm import joinedload as jl
        query = db.query(Board).options(
            jl(Board.board_type),
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
        bt = board.board_type

        board_price = None
        if bt:
            current_version = (
                db.query(PriceVersion)
                .order_by(PriceVersion.created_at.desc())
                .first()
            )
            if current_version:
                board_price = (
                    db.query(BoardTypePrice)
                    .filter_by(price_version_id=current_version.id, board_type_id=bt.id)
                    .first()
                )

        return {
            "id": board.id,
            "name": board.name,
            "ownerId": board.owner_id,
            "boardTypeId": bt.id if bt else None,
            "boardTypeName": bt.name if bt else None,
            "boardTypeMaxLed": bt.max_led if bt else None,
            "boardTypeMaxLedstrip": bt.max_ledstrip if bt else None,
            "basePriceCents": board_price.base_price_cents if board_price else None,
            "reducedPriceCents": board_price.reduced_price_cents if board_price else None,
            "ledStrips": led_strips_data,
        }

    # ── Interval-based realtime helpers ─────────────────────────────────────

    @staticmethod
    def _collect_trip_stop_ids(board) -> list[int]:
        """Gather every TripStop id linked to any LED on this board."""
        ids = []
        for strip in board.led_strips:
            for led in strip.leds:
                for ts in led.trip_stops:
                    ids.append(ts.id)
        return ids

    @staticmethod
    def _get_interval_active_trip_stop_ids(
        db: Session, trip_stop_ids: list[int]
    ) -> set[int]:
        """
        Return the subset of trip_stop_ids currently active.

        The materialized view stores all today's intervals with their
        led_on_from / led_on_until timestamps. We apply NOW() here so
        the view never needs a time-driven refresh — only data-driven
        (after static GTFS import or TripUpdates upsert).
        """
        if not trip_stop_ids:
            return set()

        try:
            rows = db.execute(sa.text("""
                SELECT canonical_trip_stop_id, led_on_from, led_on_until
                FROM active_incoming_intervals
                WHERE canonical_trip_stop_id = ANY(:ts_ids)
                  AND EXTRACT(EPOCH FROM NOW())::bigint BETWEEN led_on_from AND led_on_until
            """), {"ts_ids": trip_stop_ids}).all()

            active = {row.canonical_trip_stop_id for row in rows}

            if rows:
                for row in rows:
                    logger.info(
                        "interval active ts_id=%s led_on_from=%s led_on_until=%s now=%s",
                        row.canonical_trip_stop_id,
                        row.led_on_from,
                        row.led_on_until,
                        int(__import__("time").time()),
                    )
            else:
                # Log ranges for requested ids to help diagnose misses
                debug_rows = db.execute(sa.text("""
                    SELECT canonical_trip_stop_id, led_on_from, led_on_until
                    FROM active_incoming_intervals
                    WHERE canonical_trip_stop_id = ANY(:ts_ids)
                    LIMIT 20
                """), {"ts_ids": trip_stop_ids}).all()
                now = int(__import__("time").time())
                for row in debug_rows:
                    logger.info(
                        "interval miss ts_id=%s led_on_from=%s led_on_until=%s now=%s",
                        row.canonical_trip_stop_id,
                        row.led_on_from,
                        row.led_on_until,
                        now,
                    )

            return active

        except Exception as e:
            logger.warning("interval query failed: %s", e)
            return set()

    # ── LED strip / LED builders ─────────────────────────────────────────────

    @staticmethod
    def _build_led_strips_data(board, db: Session):
        t0 = time.perf_counter()

        trip_stop_ids = BoardService._collect_trip_stop_ids(board)
        t1 = time.perf_counter()

        interval_active_ids = BoardService._get_interval_active_trip_stop_ids(
            db, trip_stop_ids
        )
        t2 = time.perf_counter()

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
            strip_data["leds"] = [
                BoardService._build_led_data(led_obj, interval_active_ids)
                for led_obj in leds_sorted
            ]

            # Backward compatibility with old payload shape: led1..ledN
            for led_obj in leds_sorted:
                if led_obj.ledstrip_index and led_obj.ledstrip_index > 0:
                    strip_data[f"led{led_obj.ledstrip_index}"] = BoardService._build_led_data(
                        led_obj, interval_active_ids
                    )

            led_strips_data.append(strip_data)

        t3 = time.perf_counter()
        logger.info(
            "board=%s collect=%.1fms interval_query=%.1fms build=%.1fms total=%.1fms",
            board.id,
            (t1 - t0) * 1000,
            (t2 - t1) * 1000,
            (t3 - t2) * 1000,
            (t3 - t0) * 1000,
        )
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
    def _build_led_data(led_obj: Led, interval_active_ids: set[int] | None = None):
        """
        Build the LED payload.

        is_on logic (dual-source):
          • legacy:   any linked TripStop has vehicle_incoming = True
                      (STIB vehicle-positions poller, or legacy TEC poller)
          • interval: any linked TripStop id is in interval_active_ids
                      (new GTFS interval system, populated from TripUpdates)

        A LED is ON if EITHER source reports activity.  This allows STIB and
        TEC to coexist without either blocking the other.
        """
        _interval = interval_active_ids or set()

        trip_stops_data = []
        for ts in led_obj.trip_stops:
            legacy_incoming   = bool(ts.vehicle_incoming)
            interval_incoming = ts.id in _interval
            trip_stops_data.append({
                "tripStopId":        ts.id,
                "ledId":             led_obj.id,
                # Legacy boolean kept for backward compat with frontend
                "vehicleIncoming":   legacy_incoming,
                # New interval-based flag
                "intervalActive":    interval_incoming,
                # Combined: ON if either source says so
                "isOn":              legacy_incoming or interval_incoming,
                "stopStopId":        ts.stop_stop_id,
                "stopAgencyName":    ts.stop_agency_name,
                "stopName":          ts.stop.name if ts.stop else None,
            })

        led_is_on = any(ts["isOn"] for ts in trip_stops_data)

        return {
            "ledId":          led_obj.id,
            "ledstripIndex":  led_obj.ledstrip_index,
            "customName":     led_obj.custom_name,
            "type":           led_obj.type,
            "ledColor":       led_obj.led_color,
            "preStopMinutes": led_obj.pre_travel_minutes,
            "isOn":           led_is_on,
            "tripStops":      trip_stops_data,
        }
