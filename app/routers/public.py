import time

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.orm_models.db import get_db
from app.orm_models.gtfs import Line
from app.repositories.ledstrip_repo import LedStripRepository
from app.services.ledStripService import LedStripService

router = APIRouter(prefix="/api/public", tags=["public"])

# Server-side cache — single shared result, TTL matches STIB RT refresh (20 s).
_cache: tuple[dict, float] | None = None
_TTL = 20.0

# Hardcoded demo lines — never read from request params, no injection vector.
_DEMO_LINES = [
    {
        "agency":         "stib",
        "short_name":     "71",
        "central_left":   "Buyl",
        "central_right":  "Buyl",
        "fallback_color": "#1a9e4b",
        "text_color":     "#ffffff",
        "max_leds":       16,
    },
    {
        "agency":             "TEC",
        "short_name":         "6",
        "long_name_contains": "Guillemins",  # Liège line 6, not another city's 6
        "central_left":       None,
        "central_right":      None,
        "fallback_color":     "#ffd34e",
        "text_color":         "#1f3c88",
        "max_leds":           16,
    },
]


@router.get("/demo")
def get_demo(db: Session = Depends(get_db)):
    """
    Public real-time snapshot for the landing-page demo.
    Returns stop states for hardcoded demo lines — no auth, no user data.
    Response is cached 20 s server-side so DB load is minimal regardless of traffic.
    """
    global _cache
    now = time.monotonic()

    if _cache is not None and now < _cache[1]:
        return _cache[0]

    lines_out = []
    for cfg in _DEMO_LINES:
        data = _build_line_data(db, cfg)
        lines_out.append(data)

    result = {"lines": lines_out}
    _cache = (result, now + _TTL)
    return result


# ── helpers ──────────────────────────────────────────────────────────────────

def _build_line_data(db: Session, cfg: dict) -> dict:
    """Return station states for one demo line. Never raises — returns empty on any failure."""
    agency     = cfg["agency"]
    short_name = cfg["short_name"]
    text_color = cfg["text_color"]
    max_leds   = cfg["max_leds"]

    fallback = {
        "agency":        agency.lower(),
        "shortName":     short_name,
        "color":         cfg.get("fallback_color", "#888888"),
        "textColor":     text_color,
        "leftTerminus":  "",
        "rightTerminus": "",
        "stations":      [],
    }

    try:
        q = db.query(Line).filter_by(short_name=short_name, agency_name=agency)
        if cfg.get("long_name_contains"):
            q = q.filter(Line.long_name.ilike(f"%{cfg['long_name_contains']}%"))
        line = q.first()
        if not line or not line.best_trip_0_id or not line.best_trip_1_id:
            return fallback

        repo = LedStripRepository(db)
        trips = {
            0: repo.get_trip(line.best_trip_0_id),
            1: repo.get_trip(line.best_trip_1_id),
        }
        trip_stops = LedStripService._get_trip_stops_by_direction(repo, trips)

        # Central indexes: by stop name when known, else midpoint
        central_indexes = _resolve_central_indexes(
            repo, trip_stops,
            cfg["central_left"], cfg["central_right"],
        )

        selected_stops, central_position = LedStripService._select_stops_around_central(
            trip_stops, central_indexes, max_led=max_leds,
        )

        # Collect trip_stop IDs for interval query
        all_ts_ids: list[int] = [
            ts.id
            for direction in (0, 1)
            for ts in (selected_stops.get(direction) or [])
            if ts is not None
        ]

        active: dict[int, bool] = {}
        if all_ts_ids:
            rows = db.execute(sa.text("""
                SELECT canonical_trip_stop_id
                FROM active_incoming_intervals
                WHERE canonical_trip_stop_id = ANY(:ids)
                  AND is_realtime = true
                  AND EXTRACT(EPOCH FROM NOW())::bigint BETWEEN led_on_from AND led_on_until
            """), {"ids": all_ts_ids}).all()
            active = {row.canonical_trip_stop_id: True for row in rows}

        stations: list[dict] = []
        for direction in (0, 1):
            for idx, ts in enumerate(selected_stops.get(direction) or []):
                if ts is None:
                    continue
                stop = repo.get_stop(ts.stop_stop_id, ts.stop_agency_name)
                name = LedStripService._clean_stop_name(
                    stop.name if stop else "", agency
                )
                state = "realtime" if ts.id in active else "inactive"
                stations.append({
                    "name":     name,
                    "state":    state,
                    "transfer": idx == central_position.get(direction),
                })

        # Terminus names
        left_term  = trips[0].terminus.name if trips[0] and trips[0].terminus else ""
        right_term = trips[1].terminus.name if trips[1] and trips[1].terminus else ""

        raw_color = line.color or "888888"
        color = raw_color if raw_color.startswith("#") else f"#{raw_color}"

        return {
            "agency":        agency.lower(),
            "shortName":     line.short_name,
            "color":         color,
            "textColor":     text_color,
            "leftTerminus":  left_term,
            "rightTerminus": right_term,
            "stations":      stations,
        }

    except Exception:
        return fallback


def _resolve_central_indexes(repo, trip_stops: dict, left_name, right_name) -> dict:
    """Central by stop name when possible, else midpoint of each direction."""
    if left_name or right_name:
        try:
            return LedStripService._find_central_indexes(
                repo, trip_stops, left_name, right_name,
            )
        except Exception:
            pass

    # Fallback: midpoint
    return {
        d: (len(trip_stops[d]) // 2 if trip_stops.get(d) else None)
        for d in (0, 1)
    }
