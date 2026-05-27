#!/usr/bin/env python3
"""
STIB GTFS operator.

StibOperator subclasses GtfsOperator.  The static import path is identical to
any standard operator (delegated to import_gtfs_static).  The realtime path is
entirely custom: STIB exposes a JSON vehicle-positions endpoint (not GTFS-RT
protobuf), keyed by lineid + vehiclepositions, with stops identified by 4-digit
numeric IDs and direction by a terminus stop ID.  parse_rt_feed() is overridden
entirely; _match_rt_to_tripstops is never meaningful in the base class.

scheduler.py uses: from app.routines.stib_import import _operator as stib_operator
"""

if __name__ == "__main__":
    import sys, os
    BASE_DIR    = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../'))
    FASTAPI_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
    sys.path.insert(0, BASE_DIR)
    sys.path.insert(0, FASTAPI_DIR)

import json
import os
import re
import time
from collections import defaultdict

import requests
import sqlalchemy as sa

from app.orm_models.db import get_db
from app.orm_models.gtfs import Line, Stop, Trip
from app.routines.gtfs_import import GtfsOperator, _chunked, BATCH_SIZE

# --- CONFIGURATION API SECURISEE (HTTPS + NOUVELLES ROUTES) ---
STIB_API_BASE = "https://api-management-opendata-production.azure-api.net"

STIB_API_KEY = (
    os.environ.get("STIB_API_KEY", "")
    or os.environ.get("BMC_API_KEY", "")
).strip()

print(f"[stib_import] STIB_API_KEY={'***' + STIB_API_KEY[-4:] if len(STIB_API_KEY) > 4 else '(empty — anonymous)'}")


class StibOperator(GtfsOperator):
    AGENCY_NAME     = "STIB"
    GTFS_STATIC_URL = f"{STIB_API_BASE}/api/gtfs/feed/stibmivb/static"
    RT_CACHE_TTL    = 600
    
    # URL mise à jour (sans doublon de domaine)
    _VEHICLE_POSITIONS_URL = f"{STIB_API_BASE}/api/datasets/stibmivb/rt/VehiclePositions"

    def __init__(self):
        super().__init__()
        self._empty_matches = 0
        self._stib_cache: dict = {
            "ts_map": None, "line_map": None,
            "stops_base4": None, "terminus_by_line": None,
            "loaded_at": 0.0,
        }

    @property
    def _headers(self) -> dict:
        # Aligné sur le security scheme 'bmc-partner-key' de l'OpenAPI
        return {"bmc-partner-key": STIB_API_KEY} if STIB_API_KEY else {}

    # ── STIB-specific helpers ─────────────────────────────────────────────────

    @staticmethod
    def _base4(value) -> str:
        """Extract the 4-digit numeric base of a STIB stop/terminus ID."""
        digits = re.sub(r"[^0-9]", "", str(value))
        return digits[:4].zfill(4) if digits else ""

    @staticmethod
    def normalize_stop_id(stop_id) -> str:
        digits = re.sub(r'[A-Z]+$', '', str(stop_id))
        return digits.zfill(4) if len(digits) < 4 else digits

    # ── Tripstop cache ────────────────────────────────────────────────────────

    def _load_stib_cache(self, session) -> tuple:
        now = time.time()
        if (self._stib_cache["ts_map"] is not None
                and now - self._stib_cache["loaded_at"] < self.RT_CACHE_TTL):
            return (
                self._stib_cache["line_map"],
                self._stib_cache["ts_map"],
                self._stib_cache["stops_base4"],
                self._stib_cache["terminus_by_line"],
            )

        line_map: dict[str, list[int]] = defaultdict(list)
        for line_id, short_name in session.query(Line.id, Line.short_name).filter_by(agency_name="STIB"):
            line_map[short_name].append(line_id)

        stops_base4: set[str] = set()
        for (stop_id,) in session.query(Stop.stop_id).filter_by(agency_name="STIB").all():
            b = self._base4(stop_id)
            if b:
                stops_base4.add(b)

        terminus_by_line: dict[int, set[str]] = defaultdict(set)
        for line_id, terminus_id in (session.query(Trip.line_id, Trip.terminus_stop_id)
                                             .filter_by(line_agency_name="STIB")):
            b = self._base4(terminus_id)
            if b:
                terminus_by_line[line_id].add(b)

        rows = session.execute(
            sa.text("""
                SELECT ts.id AS ts_id, ts.stop_stop_id AS stop_id,
                       t.line_id, t.terminus_stop_id AS terminus_id,
                       LEAD(ts.id) OVER (PARTITION BY ts.trip_id ORDER BY ts.sequence) AS next_ts_id
                FROM trip_stop ts
                JOIN trip t ON t.id = ts.trip_id
                WHERE t.line_agency_name = 'STIB'
            """),
        ).all()

        ts_map: dict[tuple, list] = defaultdict(list)
        for row in rows:
            key = (row.line_id, self._base4(row.terminus_id), self._base4(row.stop_id))
            ts_map[key].append((row.ts_id, row.next_ts_id))

        self._stib_cache.update({
            "line_map": line_map, "ts_map": ts_map,
            "stops_base4": stops_base4, "terminus_by_line": terminus_by_line,
            "loaded_at": now,
        })
        return line_map, ts_map, stops_base4, terminus_by_line

    # ── STIB RT matching ──────────────────────────────────────────────────────

    def _match_rt_to_tripstops(self, data: list, cache: tuple) -> tuple[set[int], int]:
        line_map, ts_map, stops_base4, terminus_by_line = cache
        incoming: set[int] = set()
        matched_positions   = 0

        for entry in data:
            # Azure encapsule les propriétés de l'entité sous 'results'
            l_short = entry.get("lineid")
            l_ids   = line_map.get(l_short)
            if not l_ids:
                continue

            v_pos = entry.get("vehiclepositions")
            if not v_pos:
                continue
                
            if isinstance(v_pos, str):
                v_pos = json.loads(v_pos)

            for pos in v_pos:
                t_id = self._base4(pos.get("directionId"))
                s_id = self._base4(pos.get("pointId"))
                if not t_id or not s_id:
                    continue
                if t_id not in stops_base4:
                    continue
                if s_id not in stops_base4:
                    continue
                if not any(t_id in terminus_by_line.get(lid, set()) for lid in l_ids):
                    continue

                for lid in l_ids:
                    matches = ts_map.get((lid, t_id, s_id))
                    if not matches:
                        continue
                    for tsid, next_id in matches:
                        if pos.get("distanceFromPoint") in ("0", 0):
                            incoming.add(tsid)
                        elif next_id:
                            incoming.add(next_id)
                    matched_positions += 1

        return incoming, matched_positions

    # ── update_realtime override ──────────────────────────────────────────────

    def update_realtime(self) -> None:
        """STIB JSON vehicle positions → vehicle_incoming flags on trip_stop."""
        tic = time.time()
        print(f"[{time.strftime('%H:%M:%S')}] [STIB] Mise à jour Temps Réel…")
        try:
            r = requests.get(self._VEHICLE_POSITIONS_URL, headers=self._headers, timeout=self.RT_TIMEOUT)
            if r.status_code != 200:
                raise RuntimeError(f"VehiclePositions HTTP {r.status_code}: {r.text[:200]}")
            
            # Adaptation ODSQL : extraction obligatoire du tableau contenu dans 'results'
            res_json = r.json()
            data = res_json.get("results") if isinstance(res_json, dict) else None
            if data is None:
                data = res_json if isinstance(res_json, list) else []
                
        except Exception as e:
            print(f"  [STIB] ERREUR fetch RT: {e}")
            return

        if not data:
            print("  [STIB] Aucune donnée RT reçue ou tableau 'results' vide.")
            return

        session = next(get_db())
        try:
            cache = self._load_stib_cache(session)
            incoming, matched = self._match_rt_to_tripstops(data, cache)

            if matched == 0:
                self._empty_matches += 1
                if self._empty_matches < 3:
                    print(f"  [STIB] Aucune position appariée (#{self._empty_matches}), cycle ignoré.")
                    return
                print("  [STIB] Aucune position appariée (x3+), reset incoming.")
            else:
                self._empty_matches = 0

            session.execute(sa.text(
                "UPDATE trip_stop SET vehicle_incoming = false WHERE stop_agency_name = 'STIB'"
            ))
            if incoming:
                for batch in _chunked(list(incoming), BATCH_SIZE):
                    session.execute(
                        sa.text("UPDATE trip_stop SET vehicle_incoming = true WHERE id = ANY(:ids)"),
                        {"ids": batch},
                    )
            session.commit()
            print(f"  [STIB] {len(incoming)} TripStops 'incoming' ({matched} positions) "
                  f"en {time.time()-tic:.2f}s")
        except Exception as e:
            session.rollback()
            print(f"  [STIB] ERREUR CRITIQUE RT: {e}")
            import traceback
            traceback.print_exc()
        finally:
            session.close()


_operator = StibOperator()


if __name__ == "__main__":
    import sys
    if "--static" in sys.argv:
        print("Lancement mise à jour GTFS statique STIB…")
        _operator.import_static()
    elif "--rt" in sys.argv:
        print("Lancement mise à jour Temps Réel STIB…")
        _operator.update_realtime()
    else:
        print("Lancement mise à jour GTFS statique STIB…")
        _operator.import_static()
        print("Lancement mise à jour Temps Réel STIB…")
        _operator.update_realtime()