import logging
import time
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.routines import stib_import, tec_import

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
    
    # ===== STIB - Tâches fréquentes (temps réel) =====
    scheduler.add_job(
        stib_import.get_all_incoming_buses_export,
        IntervalTrigger(seconds=20),
        id='fetch_stib_vehicles',
        name='Fetch STIB vehicles (every 20s)',
        replace_existing=True,
        max_instances=1,
        coalesce=True  # Évite l'accumulation si une tâche prend du retard
    )
    
    # ===== TEC - Tâches fréquentes (temps réel) =====
    scheduler.add_job(
        tec_import.get_all_incoming_buses_tec,
        IntervalTrigger(seconds=20),
        id='fetch_tec_vehicles',
        name='Fetch TEC vehicles (every 20s)',
        replace_existing=True,
        max_instances=1,
        coalesce=True
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