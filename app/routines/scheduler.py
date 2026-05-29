import logging
import time
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

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
    scheduler.add_job(
        stib_operator.import_static,
        CronTrigger(hour=2, minute=0),
        id='import_stib_gtfs',
        name='Daily STIB GTFS import',
        replace_existing=True, max_instances=1,
    )

    # ===== TEC =====
    scheduler.add_job(
        tec_operator.import_static,
        CronTrigger(hour=2, minute=30),
        id='import_tec_gtfs',
        name='Daily TEC GTFS import',
        replace_existing=True, max_instances=1,
    )
    scheduler.add_job(
        tec_operator.update_realtime,
        IntervalTrigger(seconds=30),
        id='fetch_tec_trip_updates',
        name='Fetch TEC TripUpdates (every 30s)',
        replace_existing=True, max_instances=1, coalesce=True,
    )

    # ===== DE LIJN =====
    scheduler.add_job(
        delijn_operator.import_static,
        CronTrigger(hour=3, minute=0),
        id='import_delijn_gtfs',
        name='Daily De Lijn GTFS import',
        replace_existing=True, max_instances=1,
    )
    scheduler.add_job(
        delijn_operator.update_realtime,
        IntervalTrigger(seconds=30),
        id='fetch_delijn_trip_updates',
        name='Fetch De Lijn TripUpdates (every 30s)',
        replace_existing=True, max_instances=1, coalesce=True,
    )

    # ===== SNCB =====
    scheduler.add_job(
        sncb_operator.import_static,
        CronTrigger(hour=3, minute=30),
        id='import_sncb_gtfs',
        name='Daily SNCB GTFS import',
        replace_existing=True, max_instances=1,
    )
    scheduler.add_job(
        sncb_operator.update_realtime,
        IntervalTrigger(seconds=30),
        id='fetch_sncb_trip_updates',
        name='Fetch SNCB TripUpdates (every 30s)',
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