from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.api.services.transitService import TransitService
from app.core.security.jwt import get_current_user
from shared.db import get_db
from shared.models import User

router = APIRouter(prefix="/api/transit", tags=["transit"])

# --- Transit endpoints (pour Angular) ---

@router.get("/agencies")
def get_agencies(
    current_user: User = Depends(get_current_user),  # auth optionnelle selon besoin
    db: Session = Depends(get_db)
):
    return TransitService.get_agencies(db)

@router.get("/{agency_name}/lines")
def get_lines(
    agency_name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return TransitService.get_lines(agency_name, db)

@router.get("/stops")
def get_stops(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return TransitService.get_stops(db)

@router.get("/lines/{line_id}/stops")
def get_line_stops(
    line_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    result = TransitService.get_line_stops(line_id, db)
    if isinstance(result, tuple):
        raise HTTPException(status_code=result[1], detail=result[0])
    return result