from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.core.user_access import require_user
from app.orm_models.auth import User
from app.orm_models.db import get_db
from app.services.ledStripService import LedStripService

router = APIRouter(prefix="/api", tags=["ledstrips"])

class LedStripCreate(BaseModel):
    agency_name: str
    line_id: str
    central_stop_left_name: Optional[str] = None
    central_stop_right_name: Optional[str] = None
    led_color: Optional[str] = Field(default=None, pattern=r"^#?[0-9a-fA-F]{6}$")
    pre_stop_left_name: Optional[str] = None
    pre_stop_left_minutes: Optional[int] = Field(default=None, ge=1, le=300)
    pre_stop_right_name: Optional[str] = None
    pre_stop_right_minutes: Optional[int] = Field(default=None, ge=1, le=300)

    @model_validator(mode="after")
    def check_central_stop_present(self) -> "LedStripCreate":
        if not self.central_stop_left_name and not self.central_stop_right_name:
            raise ValueError(
                "At least one of central_stop_left_name or central_stop_right_name is required"
            )
        return self

    @model_validator(mode="after")
    def check_pre_stop_consistency(self) -> "LedStripCreate":
        if bool(self.pre_stop_left_name) != bool(self.pre_stop_left_minutes):
            raise ValueError(
                "pre_stop_left_name and pre_stop_left_minutes must both be provided together"
            )
        if bool(self.pre_stop_right_name) != bool(self.pre_stop_right_minutes):
            raise ValueError(
                "pre_stop_right_name and pre_stop_right_minutes must both be provided together"
            )
        return self


class LedStripUpdate(LedStripCreate):
    pass


@router.post("/boards/{board_id}/add_led_strip", status_code=201)
@require_user
def add_led_strip(
    board_id: int,
    payload: LedStripCreate,
    current_user: User,
    db: Session = Depends(get_db),
):
    return LedStripService.create_led_strip(
        board_id=board_id,
        agency_name=payload.agency_name,
        line_id=payload.line_id,
        central_stop_left_name=payload.central_stop_left_name,
        central_stop_right_name=payload.central_stop_right_name,
        led_color=payload.led_color,
        pre_stop_left_name=payload.pre_stop_left_name,
        pre_stop_left_minutes=payload.pre_stop_left_minutes,
        pre_stop_right_name=payload.pre_stop_right_name,
        pre_stop_right_minutes=payload.pre_stop_right_minutes,
        db=db,
    )


@router.get("/boards/{board_id}/led_strips/{strip_id}")
@require_user
def get_led_strip(
    board_id: int,
    strip_id: int,
    current_user: User,
    db: Session = Depends(get_db),
):
    return LedStripService.get_led_strip_by_id(board_id, strip_id, db)


@router.delete("/boards/{board_id}/led_strips/{strip_id}")
@require_user
def delete_led_strip(
    board_id: int,
    strip_id: int,
    current_user: User,
    db: Session = Depends(get_db),
):
    return LedStripService.delete_led_strip(board_id, strip_id, db)


@router.put("/boards/{board_id}/led_strips/{strip_id}")
@require_user
def update_led_strip(
    board_id: int,
    strip_id: int,
    payload: LedStripUpdate,
    current_user: User,
    db: Session = Depends(get_db),
):
    return LedStripService.update_led_strip(
        board_id=board_id,
        strip_id=strip_id,
        agency_name=payload.agency_name,
        line_id=payload.line_id,
        central_stop_left_name=payload.central_stop_left_name,
        central_stop_right_name=payload.central_stop_right_name,
        led_color=payload.led_color,
        pre_stop_left_name=payload.pre_stop_left_name,
        pre_stop_left_minutes=payload.pre_stop_left_minutes,
        pre_stop_right_name=payload.pre_stop_right_name,
        pre_stop_right_minutes=payload.pre_stop_right_minutes,
        db=db,
    )
