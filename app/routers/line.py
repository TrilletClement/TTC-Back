from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.services.lineService import LineService
from app.core.security.jwt import get_current_user
from app.orm_models.db import get_db
from app.orm_models.auth import User

router = APIRouter(prefix="/api/lines", tags=["lines"])

# --- Transit endpoints (pour Angular) ---

@router.get("/agencies")
def get_agencies(
    current_user: User = Depends(get_current_user),  # auth optionnelle selon besoin
    db: Session = Depends(get_db)
):
    return LineService.get_agencies(db)

@router.get("/{agency_name}/lines")
def get_lines(
    agency_name: str,
    search: Optional[str] = None,  # Paramètre de recherche optionnel
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return LineService.get_lines(agency_name, search, db)

@router.get("/stops")
def get_stops(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return LineService.get_stops(db)

@router.get("/{line_id}/stops")
def get_line_stops(
    line_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    result = LineService.get_line_stops(line_id, db)
    if isinstance(result, tuple):
        raise HTTPException(status_code=result[1], detail=result[0])
    return result

