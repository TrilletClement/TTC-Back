from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.user_access import require_user
from app.orm_models.auth import User
from app.orm_models.db import get_db
from app.services.lineService import LineService

router = APIRouter(prefix="/api/lines", tags=["lines"])


@router.get("/agencies")
def get_agencies(db: Session = Depends(get_db)):
    return LineService.get_agencies(db)


@router.get("/{agency_name}/lines")
@require_user
def get_lines(
    agency_name: str,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return LineService.get_lines(agency_name, search, db)


@router.get("/stops")
@require_user
def get_stops(db: Session = Depends(get_db)):
    return LineService.get_stops(db)


@router.get("/{line_id}/stops")
@require_user
def get_line_stops(line_id: str, db: Session = Depends(get_db)):
    result = LineService.get_line_stops(line_id, db)
    if isinstance(result, tuple):
        raise HTTPException(status_code=result[1], detail=result[0])
    return result
