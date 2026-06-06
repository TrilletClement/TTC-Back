import logging
import sys
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("CleanDB")

# Modifie l'URI si tes identifiants/noms de base sont différents en prod
DATABASE_URL = "postgresql://mylocaldb:password@db:5432/mylocaldb" 

CLEAN_QUERY = """
TRUNCATE TABLE
  orders, order_details,
  trip_stop_led_link, led, led_strip,
  esp32_device, board,
  trip_stop, trip,
  raw_gtfs_service_date, raw_gtfs_stop_time, raw_gtfs_trip,
  realtime_stop_time_override,
  stop, line, agency
CASCADE;
"""

def clean_transport_data():
    try:
        engine = create_engine(DATABASE_URL)
        logger.info("Nettoyage ciblé de la base de données (Préservation des utilisateurs)...")
        
        with engine.begin() as connection:
            connection.execute(text(CLEAN_QUERY))
            
        logger.info("Tables vidées avec succès.")
        
    except Exception as e:
        logger.error(f"Erreur lors du TRUNCATE : {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    clean_transport_data()