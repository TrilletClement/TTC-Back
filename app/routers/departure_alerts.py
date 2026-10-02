from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.rate_limit import limiter
from app.core.user_access import require_user
from app.domain.exceptions import NotFoundError, ValidationError
from app.orm_models.auth import User
from app.orm_models.db import get_db
from app.repositories.departure_alert_repo import DepartureAlertRepository
from app.schemas.departure_alert import (
    DepartureAlertIn,
    DepartureAlertPatch,
    PushDeviceIn,
    PushDeviceTokenIn,
    StripAlertsEnabledIn,
)
from app.services.departureAlertService import DepartureAlertService

# "Time to leave" notifications of the Android app. Distinct from /api/alerts
# (operators' service disruption alerts).
router = APIRouter(prefix="/api", tags=["departure-alerts"])


def get_service(db: Session = Depends(get_db)) -> DepartureAlertService:
    return DepartureAlertService(DepartureAlertRepository(db))


def _call(fn, *args):
    try:
        return fn(*args)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Phones ───────────────────────────────────────────────────────────────────

@router.post("/push-devices")
@require_user
def register_push_device(payload: PushDeviceIn, current_user: User, svc: DepartureAlertService = Depends(get_service)):
    _call(svc.register_device, current_user, payload.token, payload.platform, payload.lang)
    return {"registered": True}


@router.post("/push-devices/unregister")
@require_user
def unregister_push_device(payload: PushDeviceTokenIn, current_user: User, svc: DepartureAlertService = Depends(get_service)):
    svc.unregister_device(current_user, payload.token)
    return {"registered": False}


@router.post("/push-devices/test")
@limiter.limit("5/minute")
@require_user
def send_test_push(request: Request, current_user: User, svc: DepartureAlertService = Depends(get_service)):
    return {"sent": svc.send_test(current_user)}


# ── Alerts ───────────────────────────────────────────────────────────────────

@router.get("/departure-alerts")
@require_user
def list_departure_alerts(current_user: User, svc: DepartureAlertService = Depends(get_service)):
    return svc.list_alerts(current_user)


@router.get("/departure-alerts/strips/{strip_id}/stations")
@require_user
def strip_stations(strip_id: int, current_user: User, svc: DepartureAlertService = Depends(get_service)):
    """The strip's stations (stop ids, name, directions) to pick an alert's stop from."""
    return _call(svc.strip_stations, current_user, strip_id)


@router.put("/departure-alerts/strips/{strip_id}/enabled")
@require_user
def set_strip_alerts_enabled(strip_id: int, payload: StripAlertsEnabledIn, current_user: User,
                             svc: DepartureAlertService = Depends(get_service)):
    """On/off for every alert of the user on that strip (the widget's bell)."""
    return _call(svc.set_strip_enabled, current_user, strip_id, payload.enabled)


@router.post("/departure-alerts", status_code=201)
@require_user
def create_departure_alert(payload: DepartureAlertIn, current_user: User, svc: DepartureAlertService = Depends(get_service)):
    data = payload.model_dump()
    data["windows"] = [w.model_dump() for w in payload.windows]
    return _call(svc.create_alert, current_user, data)


@router.patch("/departure-alerts/{alert_id}")
@require_user
def update_departure_alert(alert_id: int, payload: DepartureAlertPatch, current_user: User,
                           svc: DepartureAlertService = Depends(get_service)):
    # Only the fields sent; "direction": null (both directions) is a real value.
    data = payload.model_dump(exclude_unset=True)
    if payload.windows is not None:
        data["windows"] = [w.model_dump() for w in payload.windows]
    return _call(svc.update_alert, current_user, alert_id, data)


@router.delete("/departure-alerts/{alert_id}", status_code=204)
@require_user
def delete_departure_alert(alert_id: int, current_user: User, svc: DepartureAlertService = Depends(get_service)):
    _call(svc.delete_alert, current_user, alert_id)
