import logging
import time
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from app.routines.gtfs_import import refresh_active_intervals
from app.routines.stib_import import _operator as stib_operator
from app.routines.tec_import import _operator as tec_operator
from app.routines.delijn_import import _operator as delijn_operator
from app.routines.sncb_import import _operator as sncb_operator

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

scheduler = BlockingScheduler()

def start():
    logger.info("Initializing scheduler...")

    # ===== STIB =====
    # 3 calls/min × 60 × 24h = 4 320 calls/day — maintained 24h/24 for night network analysis (Noctis)
    scheduler.add_job(
        stib_operator.import_static,
        CronTrigger(hour=2, minute=0),
        id='import_stib_gtfs',
        name='Daily STIB GTFS import',
        replace_existing=True, max_instances=1,
    )
    scheduler.add_job(
        stib_operator.update_realtime,
        CronTrigger(second='0,20,40'),
        id='fetch_stib_trip_updates',
        name='Fetch STIB TripUpdates (every 20s, 24h/24)',
        replace_existing=True, max_instances=1, coalesce=True,
    )

    # ===== TEC =====
    # 2 calls/min × 60 × 20h service = 2 400 calls/day — restricted to 05:00–01:00
    scheduler.add_job(
        tec_operator.import_static,
        CronTrigger(hour=2, minute=30),
        id='import_tec_gtfs',
        name='Daily TEC GTFS import',
        replace_existing=True, max_instances=1,
    )
    scheduler.add_job(
        tec_operator.update_realtime,
        CronTrigger(hour='0,5-23', second='0,30'),
        id='fetch_tec_trip_updates',
        name='Fetch TEC TripUpdates (every 30s, 05:00–01:00)',
        replace_existing=True, max_instances=1, coalesce=True,
    )
    scheduler.add_job(
        tec_operator.update_alerts,
        CronTrigger(minute='*/15'),
        id='fetch_tec_alerts',
        name='Fetch TEC service alerts (every 15 min)',
        replace_existing=True, max_instances=1, coalesce=True,
    )

    # ===== DE LIJN =====
    # 2 calls/min × 60 × 20h service = 2 400 calls/day — restricted to 05:00–01:00
    scheduler.add_job(
        delijn_operator.import_static,
        CronTrigger(hour=3, minute=0),
        id='import_delijn_gtfs',
        name='Daily De Lijn GTFS import',
        replace_existing=True, max_instances=1,
    )
    scheduler.add_job(
        delijn_operator.update_realtime,
        CronTrigger(hour='0,5-23', second='0,30'),
        id='fetch_delijn_trip_updates',
        name='Fetch De Lijn TripUpdates (every 30s, 05:00–01:00)',
        replace_existing=True, max_instances=1, coalesce=True,
    )
    scheduler.add_job(
        delijn_operator.update_alerts,
        CronTrigger(minute='*/15'),
        id='fetch_delijn_alerts',
        name='Fetch De Lijn service alerts (every 15 min)',
        replace_existing=True, max_instances=1, coalesce=True,
    )

    # ===== SNCB =====
    # 2 calls/min × 60 × 20h service = 2 400 calls/day — restricted to 05:00–01:00
    scheduler.add_job(
        sncb_operator.import_static,
        CronTrigger(hour=3, minute=30),
        id='import_sncb_gtfs',
        name='Daily SNCB GTFS import',
        replace_existing=True, max_instances=1,
    )
    scheduler.add_job(
        sncb_operator.update_realtime,
        CronTrigger(hour='0,5-23', second='0,30'),
        id='fetch_sncb_trip_updates',
        name='Fetch SNCB TripUpdates (every 30s, 05:00–01:00)',
        replace_existing=True, max_instances=1, coalesce=True,
    )
    scheduler.add_job(
        sncb_operator.update_alerts,
        CronTrigger(minute='*/15'),
        id='fetch_sncb_alerts',
        name='Fetch SNCB service alerts (every 15 min)',
        replace_existing=True, max_instances=1, coalesce=True,
    )

    # ===== MATVIEW REFRESH =====
    # Single dedicated refresh instead of one per agency per cycle: 3× less DB
    # load, and the view stays fresh even if an operator API is down.
    # Offset +5 s so it runs just after the :00/:30 upserts land.
    scheduler.add_job(
        refresh_active_intervals,
        CronTrigger(second='5,25,45'),
        id='refresh_active_intervals',
        name='Refresh active_incoming_intervals (every 20s, 24h/24)',
        replace_existing=True, max_instances=1, coalesce=True,
    )

    logger.info("Starting scheduler...")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler shutting down...")
        scheduler.shutdown()

if __name__ == "__main__":
    start()