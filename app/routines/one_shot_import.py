import logging
import sys
from app.routines.stib_import import _operator as stib_operator
from app.routines.tec_import import _operator as tec_operator
from app.routines.delijn_import import _operator as delijn_operator
from app.routines.sncb_import import _operator as sncb_operator

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("OneShotImport")

def run_all_imports():
    logger.info("Lancement séquentiel des imports statiques GTFS...")
    try:
        logger.info("⏳ [1/4] Import STIB...")
        stib_operator.import_static()
        
        logger.info("⏳ [2/4] Import TEC...")
        tec_operator.import_static()
        
        logger.info("⏳ [3/4] Import De Lijn...")
        delijn_operator.import_static()
        
        logger.info("⏳ [4/4] Import SNCB...")
        sncb_operator.import_static()
        
        logger.info("Base de données initialisée et synchronisée avec succès !")
    except Exception as e:
        logger.error(f"Échec d'un import : {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    run_all_imports()