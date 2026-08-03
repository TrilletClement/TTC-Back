from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.orm_models.db import get_db
from app.repositories.alert_repo import AlertRepository
from app.services.alertService import AlertService
from app.schemas.alert import LineIdsIn

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


def get_service(db: Session = Depends(get_db)) -> AlertService:
    return AlertService(AlertRepository(db))


@router.post("/for-lines")
def get_alerts_for_lines(payload: LineIdsIn, svc: AlertService = Depends(get_service)):
    return svc.get_alerts_for_lines(payload.line_ids)
