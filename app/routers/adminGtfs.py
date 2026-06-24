import threading
from datetime import datetime, timedelta

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.user_access import require_admin
from app.orm_models.db import get_db
from app.orm_models.gtfs import GtfsImportLog
from app.routines.stib_import import _operator as stib_operator
from app.routines.sncb_import import _operator as sncb_operator
from app.routines.tec_import import _operator as tec_operator
from app.routines.delijn_import import _operator as delijn_operator

router = APIRouter(prefix="/api/admin/gtfs", tags=["admin-gtfs"])

KNOWN_AGENCIES = ["STIB", "SNCB", "TEC", "DE_LIJN"]
STUCK_THRESHOLD = timedelta(minutes=15)

OPERATORS = {
    "STIB":    stib_operator,
    "SNCB":    sncb_operator,
    "TEC":     tec_operator,
    "DE_LIJN": delijn_operator,
}


@router.get("/status")
@require_admin
def get_import_status(db: Session = Depends(get_db)):
    rows = {r.agency_name: r for r in db.query(GtfsImportLog).all()}

    today = datetime.now().strftime("%Y%m%d")
    rt_rows = db.execute(sa.text("""
        SELECT agency_name,
               COUNT(*)              AS override_count,
               MAX(updated_at)       AS last_update,
               MAX(feed_timestamp)   AS feed_timestamp
        FROM realtime_stop_time_override
        WHERE start_date = :today
        GROUP BY agency_name
    """), {"today": today}).fetchall()
    rt = {r.agency_name: r for r in rt_rows}

    now = datetime.utcnow()
    result = []
    for agency in KNOWN_AGENCIES:
        r    = rows.get(agency)
        rt_r = rt.get(agency)
        is_stuck = (
            r is not None
            and r.status == "running"
            and r.started_at is not None
            and (now - r.started_at) > STUCK_THRESHOLD
        )
        result.append({
            "agency_name":       agency,
            "status":            r.status           if r else "never",
            "started_at":        r.started_at       if r else None,
            "completed_at":      r.completed_at     if r else None,
            "duration_seconds":  r.duration_seconds if r else None,
            "error_message":     r.error_message    if r else None,
            "is_stuck":          is_stuck,
            "rt_override_count": int(rt_r.override_count) if rt_r else 0,
            "rt_last_update":    rt_r.last_update   if rt_r else None,
            "rt_feed_timestamp": int(rt_r.feed_timestamp) if rt_r else None,
        })
    return result


@router.post("/{agency}/trigger")
@require_admin
def trigger_import(agency: str, db: Session = Depends(get_db)):
    if agency not in OPERATORS:
        raise HTTPException(status_code=404, detail=f"Unknown agency: {agency}")

    row = db.query(GtfsImportLog).filter_by(agency_name=agency).first()
    if row and row.status == "running":
        stuck = (
            row.started_at is not None
            and (datetime.utcnow() - row.started_at) > STUCK_THRESHOLD
        )
        if not stuck:
            raise HTTPException(status_code=409, detail=f"Import already running for {agency}")
        # Stuck import: reset to error so the new thread can take over
        row.status = "error"
        row.error_message = "Annulé automatiquement (bloqué > 15 min)"
        row.completed_at = datetime.utcnow()
        db.commit()

    thread = threading.Thread(target=OPERATORS[agency].import_static, daemon=True)
    thread.start()
    return {"detail": f"Import triggered for {agency}"}
