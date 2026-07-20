import re
import threading

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.orm_models.board import Led, LedStrip
from app.repositories.ledstrip_repo import LedStripRepository
from app.routines.gtfs_import import refresh_active_intervals


def _refresh_intervals_bg() -> None:
    threading.Thread(target=refresh_active_intervals, daemon=True).start()


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
    def _get_max_led(board) -> int:
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

        repo = LedStripRepository(db)
        led_color_hex = LedStripService._normalize_hex_color(led_color)

        board = repo.get_board(board_id)
        if not board:
            raise HTTPException(status_code=404, detail="Board not found")

        max_led = LedStripService._get_max_led(board)

        if board.board_type and board.board_type.max_ledstrip is not None:
            if repo.count_strips(board_id) >= board.board_type.max_ledstrip:
                raise HTTPException(
                    status_code=400,
                    detail=f"Maximum number of LED strips reached ({board.board_type.max_ledstrip}) for this board type",
                )

        next_order = (
            order_index_override
            if order_index_override is not None
            else repo.max_order_index(board_id) + 1
        )

        trips = LedStripService._get_trips_by_direction(repo, agency_name, line_id)
        if not trips[0] and not trips[1]:
            raise HTTPException(status_code=404, detail="Could not find any trips for this line")

        trip_stops = LedStripService._get_trip_stops_by_direction(repo, trips)
        central_indexes = LedStripService._find_central_indexes(
            repo, trip_stops, central_stop_left_name, central_stop_right_name,
        )
        pre_stop_overrides = LedStripService._resolve_pre_stop_overrides(
            repo, trip_stops,
            pre_stop_left_name, pre_stop_left_minutes,
            pre_stop_right_name, pre_stop_right_minutes,
        )
        selected_stops, central_position = LedStripService._select_stops_around_central(
            trip_stops, central_indexes, pre_stop_overrides, max_led=max_led,
        )

        left_t, right_t = LedStripService._compute_terminus_names(trip_stops, agency_name)
        strip = repo.add_strip(LedStrip(
            board_id=board.id,
            line_id=line_id,
            line_agency_name=agency_name,
            order_index=next_order,
            integrated_terminus=True,
            custom_terminus_left_name=left_t,
            custom_terminus_right_name=right_t,
        ))

        LedStripService._create_leds(
            repo,
            agency_name=agency_name,
            led_strip_id=strip.id,
            selected_stops=selected_stops,
            central_position=central_position,
            led_color=led_color_hex,
            pre_stop_overrides=pre_stop_overrides,
            max_led=max_led,
        )

        repo.commit()
        _refresh_intervals_bg()
        return {"message": "LED strip created successfully", "led_strip_id": strip.id}

    @staticmethod
    def preview_led_strip(
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
        db: Session = None,
    ):
        """Read-only dry run of create_led_strip: computes the exact LED layout
        (same stop-selection window, same padding around the central stop) a
        real save would produce, without writing anything to the database.
        """
        if not all([agency_name, line_id]) or (not central_stop_left_name and not central_stop_right_name):
            raise HTTPException(
                status_code=400,
                detail="agency_name, line_id, and (central_stop_left_name or central_stop_right_name) are required",
            )

        repo = LedStripRepository(db)
        led_color_hex = LedStripService._normalize_hex_color(led_color)

        board = repo.get_board(board_id)
        if not board:
            raise HTTPException(status_code=404, detail="Board not found")

        max_led = LedStripService._get_max_led(board)

        trips = LedStripService._get_trips_by_direction(repo, agency_name, line_id)
        if not trips[0] and not trips[1]:
            raise HTTPException(status_code=404, detail="Could not find any trips for this line")

        trip_stops = LedStripService._get_trip_stops_by_direction(repo, trips)
        central_indexes = LedStripService._find_central_indexes(
            repo, trip_stops, central_stop_left_name, central_stop_right_name,
        )
        pre_stop_overrides = LedStripService._resolve_pre_stop_overrides(
            repo, trip_stops,
            pre_stop_left_name, pre_stop_left_minutes,
            pre_stop_right_name, pre_stop_right_minutes,
        )
        selected_stops, central_position = LedStripService._select_stops_around_central(
            trip_stops, central_indexes, pre_stop_overrides, max_led=max_led,
        )

        left_t, right_t = LedStripService._compute_terminus_names(trip_stops, agency_name)

        descriptors = LedStripService._build_led_descriptors(
            repo, agency_name, selected_stops, central_position, led_color_hex, pre_stop_overrides, max_led,
        )

        return {
            "customTerminusLeftName":  left_t,
            "customTerminusRightName": right_t,
            "leds":                    LedStripService._descriptors_to_preview_payload(descriptors),
        }

    @staticmethod
    def get_led_strip_by_id(board_id: int, strip_id: int, db: Session):
        repo  = LedStripRepository(db)
        strip = repo.get_strip(strip_id, board_id)
        if not strip:
            raise HTTPException(status_code=404, detail="LED strip not found")

        leds_sorted = sorted(strip.leds, key=lambda led: (led.ledstrip_index or 0, led.id or 0))
        leds_payload = []
        for led in leds_sorted:
            trip_stops_payload = [
                {
                    "tripStopId":    ts.id,
                    "stopStopId":    ts.stop_stop_id,
                    "stopAgencyName": ts.stop_agency_name,
                    "stopName": ts.stop.name if ts.stop else None,
                    "vehicleIncoming": ts.vehicle_incoming,
                }
                for ts in led.trip_stops
            ]
            leds_payload.append({
                "ledId":          led.id,
                "ledstripIndex":  led.ledstrip_index,
                "customName":     led.custom_name,
                "customSubname":  led.custom_subname,
                "type":           led.type,
                "ledColor":       led.led_color,
                "preStopMinutes": led.pre_travel_minutes,
                "tripStops":      trip_stops_payload,
            })

        return {
            "id":              strip.id,
            "boardId":         strip.board_id,
            "board_id":        strip.board_id,
            "lineId":          strip.line_id,
            "line_id":         strip.line_id,
            "lineAgencyName":  strip.line_agency_name,
            "agency_name":     strip.line_agency_name,
            "orderIndex":      strip.order_index,
            "order_index":     strip.order_index,
            "customTerminusLeftName":  strip.custom_terminus_left_name,
            "customTerminusRightName": strip.custom_terminus_right_name,
            "leds":            leds_payload,
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

        repo = LedStripRepository(db)
        led_color_hex = LedStripService._normalize_hex_color(led_color)

        strip = repo.get_strip(strip_id, board_id)
        if not strip:
            raise HTTPException(status_code=404, detail="LED strip not found")

        board = repo.get_board(board_id)
        if not board:
            raise HTTPException(status_code=404, detail="Board not found")

        max_led = LedStripService._get_max_led(board)

        trips = LedStripService._get_trips_by_direction(repo, agency_name, line_id)
        if not trips[0] and not trips[1]:
            raise HTTPException(status_code=404, detail="Could not find any trips for this line")

        trip_stops = LedStripService._get_trip_stops_by_direction(repo, trips)
        central_indexes = LedStripService._find_central_indexes(
            repo, trip_stops, central_stop_left_name, central_stop_right_name,
        )
        pre_stop_overrides = LedStripService._resolve_pre_stop_overrides(
            repo, trip_stops,
            pre_stop_left_name, pre_stop_left_minutes,
            pre_stop_right_name, pre_stop_right_minutes,
        )
        selected_stops, central_position = LedStripService._select_stops_around_central(
            trip_stops, central_indexes, pre_stop_overrides, max_led=max_led,
        )

        left_t, right_t = LedStripService._compute_terminus_names(trip_stops, agency_name)
        strip.line_id = int(line_id)
        strip.line_agency_name = agency_name
        strip.custom_terminus_left_name  = left_t
        strip.custom_terminus_right_name = right_t

        for led in list(strip.leds):
            led.trip_stops.clear()
            repo.db.delete(led)
        repo.flush()

        LedStripService._create_leds(
            repo,
            agency_name=agency_name,
            led_strip_id=strip.id,
            selected_stops=selected_stops,
            central_position=central_position,
            led_color=led_color_hex,
            pre_stop_overrides=pre_stop_overrides,
            max_led=max_led,
        )

        repo.commit()
        _refresh_intervals_bg()
        return {"message": "LED strip updated successfully", "led_strip_id": strip.id}

    @staticmethod
    def move_strip_to_slot(board_id: int, strip_id: int, order_index: int, db: Session):
        repo  = LedStripRepository(db)
        strip = repo.get_strip(strip_id, board_id)
        if not strip:
            raise HTTPException(status_code=404, detail="LED strip not found")
        other     = repo.get_strip_at_slot(board_id, order_index, strip_id)
        old_index = strip.order_index
        strip.order_index = order_index
        if other:
            other.order_index = old_index
        repo.commit()
        return {"message": "OK"}

    @staticmethod
    def reorder_strips(board_id: int, ordered_ids: list[int], db: Session):
        repo = LedStripRepository(db)
        for position, strip_id in enumerate(ordered_ids, start=1):
            strip = repo.get_strip_by_id_for_reorder(strip_id, board_id)
            if strip:
                strip.order_index = position
        repo.commit()
        return {"message": "Strips reordered"}

    @staticmethod
    def delete_led_strip(board_id: int, strip_id: int, db: Session):
        repo  = LedStripRepository(db)
        strip = repo.get_strip(strip_id, board_id)
        if not strip:
            raise HTTPException(status_code=404, detail="LED strip not found")
        repo.delete_strip(strip)
        repo.commit()
        return {"message": "LED strip deleted successfully", "led_strip_id": strip_id}

    @staticmethod
    def patch_strip_settings(
        board_id: int,
        strip_id: int,
        db: Session,
        integrated_terminus: bool | None = None,
        rt_only: bool | None = None,
    ):
        repo  = LedStripRepository(db)
        strip = repo.get_strip(strip_id, board_id)
        if not strip:
            raise HTTPException(status_code=404, detail="LED strip not found")
        if integrated_terminus is not None:
            strip.integrated_terminus = integrated_terminus
        if rt_only is not None:
            strip.rt_only = rt_only
        repo.commit()
        return {"message": "OK", "led_strip_id": strip_id}

    @staticmethod
    def patch_led_label(
        board_id: int,
        strip_id: int,
        led_id: int,
        custom_name: str | None,
        custom_subname: str | None,
        db: Session,
    ):
        repo  = LedStripRepository(db)
        strip = repo.get_strip(strip_id, board_id)
        if not strip:
            raise HTTPException(status_code=404, detail="LED strip not found")
        led = repo.get_led(led_id, strip_id)
        if not led:
            raise HTTPException(status_code=404, detail="LED not found")
        led.custom_name = custom_name
        led.custom_subname = custom_subname
        repo.commit()
        return {
            "message": "OK",
            "led_id": led_id,
            "customName": led.custom_name,
            "customSubname": led.custom_subname,
        }

    @staticmethod
    def patch_terminus_labels(
        board_id: int,
        strip_id: int,
        fields_set: set[str],
        custom_terminus_left_name: str | None,
        custom_terminus_right_name: str | None,
        db: Session,
    ):
        repo  = LedStripRepository(db)
        strip = repo.get_strip(strip_id, board_id)
        if not strip:
            raise HTTPException(status_code=404, detail="LED strip not found")
        t = LedStripService._truncate
        if "custom_terminus_left_name" in fields_set:
            strip.custom_terminus_left_name  = t(custom_terminus_left_name)
        if "custom_terminus_right_name" in fields_set:
            strip.custom_terminus_right_name = t(custom_terminus_right_name)
        repo.commit()
        return {
            "message": "OK",
            "led_strip_id": strip_id,
            "customTerminusLeftName":  strip.custom_terminus_left_name,
            "customTerminusRightName": strip.custom_terminus_right_name,
        }

    # ── Helpers privés ───────────────────────────────────────────────────────────

    @staticmethod
    def _compute_terminus_names(trip_stops: dict, agency_name: str) -> tuple[str | None, str | None]:
        """Return (left_name, right_name) formatted from the last stop of each direction.

        direction 1 → left terminus
        direction 0 → right terminus
        """
        def _last_stop_name(stops) -> str | None:
            if not stops:
                return None
            last_ts = stops[-1]
            return last_ts.stop.name if last_ts and last_ts.stop else None

        left_raw  = _last_stop_name(trip_stops.get(1))
        right_raw = _last_stop_name(trip_stops.get(0))

        left_name,  _ = LedStripService.format_stop_label(left_raw,  agency_name) if left_raw  else (None, None)
        right_name, _ = LedStripService.format_stop_label(right_raw, agency_name) if right_raw else (None, None)

        return left_name, right_name

    @staticmethod
    def _get_trips_by_direction(repo: LedStripRepository, agency_name, line_id):
        line = repo.get_line(line_id, agency_name)
        if not line:
            raise HTTPException(
                status_code=404,
                detail=f"Line with id {line_id} and agency_name {agency_name} not found",
            )
        return {
            0: repo.get_trip(line.best_trip_0_id),
            1: repo.get_trip(line.best_trip_1_id),
        }

    @staticmethod
    def _get_trip_stops_by_direction(repo: LedStripRepository, trips):
        return {
            direction: repo.get_trip_stops(trips[direction].id) if trips[direction] else []
            for direction in [0, 1]
        }

    @staticmethod
    def _find_central_indexes(repo: LedStripRepository, trip_stops, central_stop_left_name, central_stop_right_name):
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
                ts   = trip_stops[direction][i]
                stop = repo.get_stop(ts.stop_stop_id, ts.stop_agency_name)
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
        repo: LedStripRepository, trip_stops,
        pre_stop_left_name,  pre_stop_left_minutes,
        pre_stop_right_name, pre_stop_right_minutes,
    ) -> dict:
        overrides = {0: (None, None), 1: (None, None)}
        pairs = {
            0: (pre_stop_left_name,  pre_stop_left_minutes),
            1: (pre_stop_right_name, pre_stop_right_minutes),
        }
        for direction, (name, minutes) in pairs.items():
            if not name or not trip_stops[direction]:
                continue
            target = name.strip().lower()
            found  = False
            for i in range(len(trip_stops[direction]) - 1, -1, -1):
                ts   = trip_stops[direction][i]
                stop = repo.get_stop(ts.stop_stop_id, ts.stop_agency_name)
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
    def _select_stops_around_central(trip_stops, central_indexes, pre_stop_overrides=None, max_led: int = 12):
        """Builds, for each active direction, the list of TripStop|None entries to
        place on the strip (left to right), plus the index of the actual central
        stop within that list.

        Two-direction strips: each direction fills its own half exactly, with the
        central stop adjacent to the middle of the strip and any history shortfall
        padded as empty (None) LEDs at the outer edge of that half.

        One-direction strips: the occupied block (history + central) is centered
        on the strip, with one LED always left empty immediately after the central
        stop (reserved for the direction/terminus rendering) and any remaining
        shortfall split as evenly as possible between the two outer edges.
        """
        selected_stops = {}
        central_position = {}
        only_one_direction = (central_indexes[0] is None) != (central_indexes[1] is None)
        stops_per_side = max_led // 2

        for direction in [0, 1]:
            if central_indexes[direction] is None:
                selected_stops[direction] = None
                central_position[direction] = None
                continue

            central_idx = central_indexes[direction]
            all_stops   = trip_stops[direction]

            pre_ts = None
            pre_idx = None
            if pre_stop_overrides:
                pre_ts, _ = pre_stop_overrides.get(direction, (None, None))
                if pre_ts:
                    pre_idx = next((i for i, ts in enumerate(all_stops) if ts.id == pre_ts.id), None)

            if only_one_direction:
                # 1 LED is always reserved as a buffer right after the central
                # stop, so `capacity` is what's left for history + central.
                capacity = max_led - 1
                if pre_idx is not None:
                    start  = max(0, pre_idx - (capacity - 2))
                    window = list(all_stops[start : pre_idx + 1])
                    while len(window) < capacity - 1:
                        window.insert(0, None)
                    window.append(all_stops[central_idx])
                else:
                    start  = max(0, central_idx - (capacity - 1))
                    window = list(all_stops[start : central_idx + 1])
                    while len(window) < capacity:
                        window.insert(0, None)

                deficiency   = sum(1 for ts in window if ts is None)
                total_blanks = deficiency + 1  # +1 for the mandatory buffer
                left_blanks  = total_blanks // 2
                right_extra  = total_blanks - left_blanks - 1

                trimmed = window[deficiency - left_blanks:]
                final   = trimmed + [None] + [None] * right_extra
                central_pos = len(trimmed) - 1

                if direction == 1:
                    final = list(reversed(final))
                    central_pos = len(final) - 1 - central_pos

                selected_stops[direction]   = final
                central_position[direction] = central_pos
            else:
                # Two-direction: collect history for each direction, then
                # center the entire occupied block by splitting blanks equally
                # between the outer-left and outer-right edges of the strip.
                # (Processed after both directions are known — see post-loop block.)
                pre_ts_d, _ = (pre_stop_overrides or {}).get(direction, (None, None))
                pre_idx_d   = next(
                    (i for i, ts in enumerate(all_stops) if ts.id == pre_ts_d.id), None
                ) if pre_ts_d else None

                if pre_idx_d is not None:
                    start   = max(0, pre_idx_d - (stops_per_side - 2))
                    history = list(all_stops[start : pre_idx_d + 1])
                else:
                    start   = max(0, central_idx - (stops_per_side - 1))
                    history = list(all_stops[start : central_idx])

                selected_stops[direction]   = history          # temporary; finalised below
                central_position[direction] = all_stops[central_idx]  # store the stop obj

        # ── Finalise two-direction centering ──────────────────────────────────
        if not only_one_direction and selected_stops[0] is not None and selected_stops[1] is not None:
            h0           = selected_stops[0]           # history list for direction 0
            h1           = selected_stops[1]           # history list for direction 1
            central_0    = central_position[0]         # actual central TripStop obj
            central_1    = central_position[1]
            total_occ    = len(h0) + 1 + len(h1) + 1
            total_blanks = max_led - total_occ
            left_blanks  = total_blanks // 2
            right_blanks = total_blanks - left_blanks

            # Left half: [None]*left_blanks + history_0 + [central_0]
            selected_stops[0]   = [None] * left_blanks + h0 + [central_0]
            central_position[0] = left_blanks + len(h0)   # index of central_0

            # Right half: [central_1] + reversed(history_1) + [None]*right_blanks.
            # h1 is in direction-1 travel order (approaching the central), so the
            # stop nearest the central must sit right next to it on the strip —
            # without the reversal the right half reads mirror-ordered.
            selected_stops[1]   = [central_1] + list(reversed(h1)) + [None] * right_blanks
            central_position[1] = 0                       # central_1 always first

        return selected_stops, central_position

    @staticmethod
    def _build_led_descriptors(
        repo: LedStripRepository,
        agency_name: str,
        selected_stops,
        central_position,
        led_color: str,
        pre_stop_overrides=None,
        max_led: int = 12,
    ) -> list[dict]:
        """Compute, for each of the `max_led` slots, the (type, label, trip_stop)
        that slot would get. Pure/read-only — used both to persist real LEDs and
        to build a dry-run preview of what a strip would look like.
        """
        only0  = selected_stops[1] is None
        only1  = selected_stops[0] is None
        # For two-direction strips the halves may be unequal after centering.
        half   = len(selected_stops[0]) if (not only0 and not only1) else max_led // 2

        pre_minutes_by_ts_id: dict[int, int] = {}
        if pre_stop_overrides:
            for direction in [0, 1]:
                override_ts, override_minutes = pre_stop_overrides.get(direction, (None, None))
                if override_ts and override_minutes is not None:
                    pre_minutes_by_ts_id[override_ts.id] = override_minutes

        descriptors: list[dict] = []
        for i in range(max_led):
            if not only0 and not only1:
                direction, stop_idx = (0, i) if i < half else (1, i - half)
            elif only0:
                direction, stop_idx = 0, i
            else:
                direction, stop_idx = 1, i

            ts = selected_stops[direction][stop_idx] if selected_stops[direction] else None
            pre_travel_minutes = pre_minutes_by_ts_id.get(ts.id) if ts else None

            custom_name = None
            custom_subname = None
            if ts:
                stop = repo.get_stop(ts.stop_stop_id, agency_name)
                if stop and stop.name:
                    custom_name, custom_subname = LedStripService.format_stop_label(stop.name, agency_name)
                else:
                    custom_name = ts.stop_stop_id

            is_central = stop_idx == central_position[direction]
            if direction == 0:
                led_type = "c_left" if is_central else "left"
            else:
                led_type = "c_right" if is_central else "right"

            descriptors.append({
                "ledstrip_index":     i + 1,
                "type":               led_type,
                "led_color":          led_color,
                "pre_travel_minutes": pre_travel_minutes,
                "custom_name":        custom_name,
                "custom_subname":     custom_subname,
                "trip_stop":          ts,
            })

        return descriptors

    @staticmethod
    def _descriptors_to_preview_payload(descriptors: list[dict]) -> list[dict]:
        payload = []
        for d in descriptors:
            ts = d["trip_stop"]
            trip_stops_payload = []
            if ts:
                trip_stops_payload = [{
                    "tripStopId":     ts.id,
                    "stopStopId":     ts.stop_stop_id,
                    "stopAgencyName": ts.stop_agency_name,
                    "stopName":       ts.stop.name if ts.stop else None,
                    "vehicleIncoming": False,
                }]
            payload.append({
                "ledId":          None,
                "ledstripIndex":  d["ledstrip_index"],
                "customName":     d["custom_name"],
                "customSubname":  d["custom_subname"],
                "type":           d["type"],
                "ledColor":       d["led_color"],
                "preStopMinutes": d["pre_travel_minutes"],
                "tripStops":      trip_stops_payload,
            })
        return payload

    @staticmethod
    def _create_leds(
        repo: LedStripRepository,
        agency_name: str,
        led_strip_id: int,
        selected_stops,
        central_position,
        led_color: str,
        pre_stop_overrides=None,
        max_led: int = 12,
    ):
        descriptors = LedStripService._build_led_descriptors(
            repo, agency_name, selected_stops, central_position, led_color, pre_stop_overrides, max_led,
        )

        for d in descriptors:
            led = repo.add_led(Led(
                ledstrip_id       = led_strip_id,
                ledstrip_index    = d["ledstrip_index"],
                custom_name       = d["custom_name"],
                custom_subname    = d["custom_subname"],
                type              = d["type"],
                led_color         = d["led_color"],
                pre_travel_minutes = d["pre_travel_minutes"],
            ))

            if d["trip_stop"]:
                led.trip_stops.append(d["trip_stop"])

    _SMART_LOWER: frozenset[str] = frozenset({
        'le','la','les','un','une','de','du','des','à','au','aux','en','par','pour',
        'sur','sous','dans','avec','vers','entre','chez','et','ou','mais','ni','car',
        'que','qui','dont','où','het','een','van','voor','op','in','aan','bij','met',
        'te','naar','tot','over','onder','om','per','of','maar','den','der','ter',
    })

    @staticmethod
    def _smart_title(s: str) -> str:
        """Title-case a string with smart lower-case for common prepositions/articles."""
        if not s:
            return s
        words = s.split(' ')
        out = []
        for i, word in enumerate(words):
            if '-' in word:
                out.append('-'.join(seg.lower().capitalize() for seg in word.split('-')))
            elif "'" in word:
                ap = word.index("'")
                pre = word[:ap].lower()
                suf = word[ap + 1:].lower().capitalize()
                out.append((pre.capitalize() if i == 0 else pre) + "'" + suf)
            else:
                low = word.lower()
                out.append(low if (i > 0 and low in LedStripService._SMART_LOWER) else low.capitalize())
        return ' '.join(out)

    @staticmethod
    def _truncate(text: str | None, limit: int = 19) -> str | None:
        """Truncate to at most `limit` characters, appending '...' when cut."""
        if not text or len(text) <= limit:
            return text
        return text[:limit - 3] + '...'

    @staticmethod
    def format_stop_label(name: str, agency_name: str) -> tuple[str | None, str | None]:
        """Return (custom_name, custom_subname) for a stop, by agency.

        Both values are truncated to 19 characters (with trailing '...') so the
        result can be stored directly in the DB and displayed without further
        formatting.

        TEC     — subname: leading ALL-CAPS words; name: remainder minus " - …" suffix
        STIB    — subname: None; name: stop name with normalised whitespace
        DE_LIJN — subname: first word (uppercased); name: everything after
        SNCB    — subname: None; name: stop name as-is
        Other   — subname: None; name: stop name with trailing parenthetical stripped
        """
        if not name:
            return None, None

        t = LedStripService._truncate
        name = " ".join(name.split())

        if agency_name == "TEC":
            cleaned = re.sub(r'\s*\(.*?\)\s*$', '', name).strip()
            subname: str | None = None
            if len(cleaned.split()) >= 2:
                m = re.match(r'^([A-ZÀ-ÿ]+(?:[\s\-][A-ZÀ-ÿ]+)*)\s+', cleaned)
                if m:
                    subname = m.group(1).strip()
                    cleaned = cleaned[m.end():]
            dash = cleaned.find(' - ')
            if dash != -1:
                cleaned = cleaned[:dash]
            return t(cleaned.strip() or None), t(subname)

        if agency_name == "STIB":
            cleaned = re.sub(r'\s*\(.*?\)\s*$', '', name).strip()
            return t(LedStripService._smart_title(cleaned) or None), None

        if agency_name == "DE_LIJN":
            parts = name.split(' ', 1)
            if len(parts) == 1:
                return t(parts[0] or None), None
            return t(parts[1].strip() or None), t(parts[0].upper())

        if agency_name == "SNCB":
            return t(name or None), None

        cleaned = re.sub(r'\s*\(.*?\)\s*$', '', name).strip()
        return t(cleaned or None), None
