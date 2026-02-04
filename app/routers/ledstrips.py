from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.services.ledStripService import LedStripService
from app.core.security.jwt import get_current_user
from app.orm_models.db import get_db
from app.orm_models.auth import User

router = APIRouter(prefix="/api", tags=["ledstrips"])


class LedStripCreate(BaseModel):
    agency_name: str
    line_id: str
    central_stop_left_name: str
    central_stop_right_name: str
    led_color: str

#Exception en transit avec Angular pour l'ajout d'une led strip (Clément 02/01/2026)
@router.post("/line/{board_id}/add_led_strip")
def add_led_strip(
    board_id: int,
    payload: LedStripCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return LedStripService.create_led_strip(
        board_id,
        payload.agency_name,
        payload.line_id,
        payload.central_stop_left_name,
        payload.central_stop_right_name,
        payload.led_color,
        None,
        db
    )


@router.get("/boards/{board_id}/led_strips/{strip_id}")
def get_led_strip(
    board_id: int,
    strip_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return LedStripService.get_led_strip_by_id(board_id, strip_id, db)


class LedStripUpdate(BaseModel):
    agency_name: str
    line_id: str
    central_stop_left_name: str
    central_stop_right_name: str
    led_color: str


@router.put("/boards/{board_id}/led_strips/{strip_id}")
def update_led_strip(
    board_id: int,
    strip_id: int,
    payload: LedStripUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return LedStripService.update_led_strip(
        board_id,
        strip_id,
        payload.agency_name,
        payload.line_id,
        payload.central_stop_left_name,
        payload.central_stop_right_name,
        payload.led_color,
        db
    )
