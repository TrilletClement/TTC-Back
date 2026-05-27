#!/usr/bin/env python3
"""
TEC GTFS operator.

TecOperator subclasses GtfsOperator.  update_realtime() (inherited) fetches
GTFS-RT TripUpdates and upserts into realtime_stop_time_override, then
refreshes active_incoming_intervals.

scheduler.py uses: from app.routines.tec_import import _operator as tec_operator
"""

if __name__ == "__main__":
    import sys, os
    BASE_DIR    = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
    FASTAPI_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
    sys.path.insert(0, BASE_DIR)
    sys.path.insert(0, FASTAPI_DIR)

import os

from app.routines.gtfs_import import GtfsOperator

BMC_API_BASE = "https://opendata-discovery-gtfs-static.api.production.belgianmobility.io"
BMC_API_KEY  = os.environ.get("BMC_API_KEY", "").strip()

print(f"[tec_import] BMC_API_KEY={'***' + BMC_API_KEY[-4:] if len(BMC_API_KEY) > 4 else '(empty — anonymous)'}")


class TecOperator(GtfsOperator):
    AGENCY_NAME     = "TEC"
    GTFS_STATIC_URL = f"{BMC_API_BASE}/api/gtfs/feed/tec/static"
    GTFS_RT_URL     = (
        "https://opendata-discovery-gtfs-realtime.api.production.belgianmobility.io"
        "/api/gtfs-rt/tec/TripUpdates.pbf"
    )

    @property
    def _headers(self) -> dict:
        return {"bmc-partner-key": BMC_API_KEY} if BMC_API_KEY else {}


_operator = TecOperator()


if __name__ == "__main__":
    import sys
    if "--static" in sys.argv:
        _operator.import_static()
    elif "--rt" in sys.argv:
        _operator.update_realtime()
    else:
        _operator.import_static()
        _operator.update_realtime()
