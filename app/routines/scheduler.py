from apscheduler.schedulers.background import BackgroundScheduler
from app.routines import stib_import, tec_import
import logging

scheduler = BackgroundScheduler()
logging.basicConfig()
logging.getLogger('apscheduler').setLevel(logging.DEBUG)

def start():
    # STIB - Daily routines (run once every day at 2AM)
    scheduler.add_job(stib_import.import_stib_gtfs, 'cron', hour=2, minute=0, id='import_stib_gtfs')
    
    # TEC - Daily routines (run once every day at 2:30 AM)
    scheduler.add_job(tec_import.import_tec_gtfs, 'cron', hour=2, minute=30, id='import_tec_gtfs')

    # STIB - Frequent routine (every 20 seconds)
    scheduler.add_job(stib_import.get_all_incoming_buses_export_test, 'interval', seconds=20, id='fetch_stib_vehicles')
    
    # TEC - Frequent routine (every 20 seconds)
    scheduler.add_job(tec_import.get_all_incoming_buses_tec, 'interval', seconds=20, id='fetch_tec_vehicles')

    scheduler.start()