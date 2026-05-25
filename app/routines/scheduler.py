import logging
import time
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.routines import stib_import, tec_import, tec_trip_updates

# Configuration logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Utiliser BlockingScheduler pour un processus dédié
scheduler = BlockingScheduler()

def start():
    """Configure et démarre le scheduler"""
    logger.info("Initializing scheduler...")
    
    # ===== STIB - Tâches quotidiennes =====
    scheduler.add_job(
        stib_import.import_stib_gtfs,
        CronTrigger(hour=2, minute=0),
        id='import_stib_gtfs',
        name='Daily STIB GTFS import',
        replace_existing=True,
        max_instances=1
    )
    
    # ===== TEC - Tâches quotidiennes =====
    scheduler.add_job(
        tec_import.import_tec_gtfs,
        CronTrigger(hour=2, minute=30),
        id='import_tec_gtfs',
        name='Daily TEC GTFS import',
        replace_existing=True,
        max_instances=1
    )
    
    # New interval-based realtime: upsert GTFS-RT TripUpdates overrides only.
    # LED state is derived at query time from active_incoming_intervals view.
    scheduler.add_job(
        tec_trip_updates.fetch_tec_trip_updates,
        IntervalTrigger(seconds=30),
        id='fetch_tec_trip_updates',
        name='Fetch TEC TripUpdates overrides (every 30s)',
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    
    # Démarrage du scheduler
    logger.info("Starting scheduler...")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler shutting down...")
        scheduler.shutdown()

if __name__ == "__main__":
    start()