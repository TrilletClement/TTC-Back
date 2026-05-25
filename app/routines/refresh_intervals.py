"""Shared helper to refresh the active_incoming_intervals materialized view."""
import time

import sqlalchemy as sa

from app.orm_models.db import get_db


def refresh_active_intervals():
    """
    Refresh the active_incoming_intervals materialized view.
    Call this after any static GTFS import or TripUpdates upsert.
    CONCURRENTLY means reads are not blocked during refresh.
    """
    tic = time.time()
    session = next(get_db())
    try:
        # CONCURRENTLY requires the view to already be populated.
        populated = session.execute(sa.text(
            "SELECT COUNT(*) FROM pg_matviews "
            "WHERE matviewname = 'active_incoming_intervals' AND ispopulated = true"
        )).scalar()
        sql = (
            "REFRESH MATERIALIZED VIEW CONCURRENTLY active_incoming_intervals"
            if populated else
            "REFRESH MATERIALIZED VIEW active_incoming_intervals"
        )
        session.execute(sa.text(sql))
        session.commit()
        print(f"  active_incoming_intervals refreshed in {time.time()-tic:.2f}s")
    except Exception as e:
        session.rollback()
        print(f"  ERROR refreshing active_incoming_intervals: {e}")
    finally:
        session.close()
