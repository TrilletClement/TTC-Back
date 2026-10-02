"""Scheduler job: sends the "time to leave" notifications that are due."""
import logging

from app.orm_models.db import get_db
from app.repositories.departure_alert_repo import DepartureAlertRepository
from app.services.departureAlertService import DepartureAlertService

logger = logging.getLogger(__name__)


def send_departure_alerts() -> None:
    session = next(get_db())
    try:
        sent = DepartureAlertService(DepartureAlertRepository(session)).evaluate()
        if sent:
            logger.info("Departure alerts: %d notification(s) sent", sent)
    except Exception:
        session.rollback()
        logger.exception("Departure alerts evaluation failed")
    finally:
        session.close()
