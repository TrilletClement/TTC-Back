from apscheduler.schedulers.background import BackgroundScheduler
from app.routines import stib_import
import logging

scheduler = BackgroundScheduler()
logging.basicConfig()
logging.getLogger('apscheduler').setLevel(logging.DEBUG)

def start():
    # Daily routines (run once every day at 2AM)
    scheduler.add_job(stib_import.import_stib_gtfs, 'cron', hour=2, minute=0, id='import_stib_gtfs')

    # Frequent routine (every 20 seconds)
    scheduler.add_job(stib_import.get_all_incoming_buses_export, 'interval', seconds=20, id='fetch_stib_vehicles')

    scheduler.start()


