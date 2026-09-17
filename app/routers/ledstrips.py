from typing import Literal, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.core.user_access import require_admin, require_user
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
    line_color: Optional[str] = Field(default=None, pattern=r"^#?[0-9a-fA-F]{6}$")
    pre_stop_left_name: Optional[str] = None
    pre_stop_left_minutes: Optional[int] = Field(default=None, ge=1, le=300)
    pre_stop_right_name: Optional[str] = None
    pre_stop_right_minutes: Optional[int] = Field(default=None, ge=1, le=300)
    order_index: Optional[int] = Field(default=None, ge=1)
    # Branch override for lines with several stop-sequence variants per
    # direction (e.g. TEC T1 Liège: Coronmeuse vs Liège Expo). None = follow
    # the line's best_trip_{0,1}_id, same as before this field existed.
    trip_0_id: Optional[int] = None
    trip_1_id: Optional[int] = None
    # Which language to show for stops with a split name (STIB, SNCB — see
    # Stop.name_fr/name_nl). None = leave it to the line's/stop's default
    # resolution (French first, see LedStripService._resolve_stop_name).
    stop_name_language: Optional[Literal["fr", "nl"]] = None

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


class LedStripSettingsPatch(BaseModel):
    integrated_terminus: Optional[bool] = None
    rt_only: Optional[bool] = None


class LedLabelPatch(BaseModel):
    custom_name: Optional[str] = Field(default=None, max_length=19)
    custom_subname: Optional[str] = Field(default=None, max_length=19)


class TerminusLabelPatch(BaseModel):
    # Matches led_strip.custom_terminus_left/right_name (String(50)) — unlike
    # per-LED labels, the terminus name is a single rotated badge that
    # truncates itself to fit on the frontend, so it isn't capped to the
    # LED display width.
    custom_terminus_left_name:  Optional[str] = Field(default=None, max_length=50)
    custom_terminus_right_name: Optional[str] = Field(default=None, max_length=50)


class LinkTrunkPayload(BaseModel):
    other_strip_id: int


class ReorderPayload(BaseModel):
    ordered_ids: list[int]


class MoveSlotPayload(BaseModel):
    order_index: int = Field(..., ge=1)


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
        current_user=current_user,
        led_color=payload.led_color,
        line_color=payload.line_color,
        pre_stop_left_name=payload.pre_stop_left_name,
        pre_stop_left_minutes=payload.pre_stop_left_minutes,
        pre_stop_right_name=payload.pre_stop_right_name,
        pre_stop_right_minutes=payload.pre_stop_right_minutes,
        order_index_override=payload.order_index,
        trip_0_id=payload.trip_0_id,
        trip_1_id=payload.trip_1_id,
        stop_name_language=payload.stop_name_language,
        db=db,
    )


@router.post("/boards/{board_id}/led_strips/preview")
@require_user
def preview_led_strip(
    board_id: int,
    payload: LedStripCreate,
    current_user: User,
    db: Session = Depends(get_db),
):
    return LedStripService.preview_led_strip(
        board_id=board_id,
        agency_name=payload.agency_name,
        line_id=payload.line_id,
        central_stop_left_name=payload.central_stop_left_name,
        central_stop_right_name=payload.central_stop_right_name,
        current_user=current_user,
        led_color=payload.led_color,
        pre_stop_left_name=payload.pre_stop_left_name,
        pre_stop_left_minutes=payload.pre_stop_left_minutes,
        pre_stop_right_name=payload.pre_stop_right_name,
        pre_stop_right_minutes=payload.pre_stop_right_minutes,
        trip_0_id=payload.trip_0_id,
        trip_1_id=payload.trip_1_id,
        stop_name_language=payload.stop_name_language,
        db=db,
    )


@router.patch("/boards/{board_id}/led_strips/reorder")
@require_user
def reorder_led_strips(
    board_id: int,
    payload: ReorderPayload,
    current_user: User,
    db: Session = Depends(get_db),
):
    return LedStripService.reorder_strips(board_id, payload.ordered_ids, current_user, db)


@router.patch("/boards/{board_id}/led_strips/{strip_id}/slot")
@require_user
def move_strip_to_slot(
    board_id: int,
    strip_id: int,
    payload: MoveSlotPayload,
    current_user: User,
    db: Session = Depends(get_db),
):
    return LedStripService.move_strip_to_slot(board_id, strip_id, payload.order_index, current_user, db)


@router.get("/boards/{board_id}/led_strips/{strip_id}")
@require_user
def get_led_strip(
    board_id: int,
    strip_id: int,
    current_user: User,
    db: Session = Depends(get_db),
):
    return LedStripService.get_led_strip_by_id(board_id, strip_id, current_user, db)


@router.delete("/boards/{board_id}/led_strips/{strip_id}")
@require_user
def delete_led_strip(
    board_id: int,
    strip_id: int,
    current_user: User,
    db: Session = Depends(get_db),
):
    return LedStripService.delete_led_strip(board_id, strip_id, current_user, db)


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
        current_user=current_user,
        line_color=payload.line_color,
        pre_stop_left_name=payload.pre_stop_left_name,
        pre_stop_left_minutes=payload.pre_stop_left_minutes,
        pre_stop_right_name=payload.pre_stop_right_name,
        pre_stop_right_minutes=payload.pre_stop_right_minutes,
        trip_0_id=payload.trip_0_id,
        trip_1_id=payload.trip_1_id,
        stop_name_language=payload.stop_name_language,
        db=db,
    )


@router.patch("/boards/{board_id}/led_strips/{strip_id}/settings")
@require_user
def patch_led_strip_settings(
    board_id: int,
    strip_id: int,
    payload: LedStripSettingsPatch,
    current_user: User,
    db: Session = Depends(get_db),
):
    return LedStripService.patch_strip_settings(
        board_id=board_id,
        strip_id=strip_id,
        current_user=current_user,
        integrated_terminus=payload.integrated_terminus,
        rt_only=payload.rt_only,
        db=db,
    )


@router.get("/boards/{board_id}/led_strips/{strip_id}/trunk_candidates")
@require_admin  # TODO: still being tested — open to require_user once the feature is validated
def get_trunk_candidates(
    board_id: int,
    strip_id: int,
    current_user: User,
    db: Session = Depends(get_db),
):
    return LedStripService.get_trunk_candidates(board_id, strip_id, db)


@router.post("/boards/{board_id}/led_strips/{strip_id}/link_trunk")
@require_admin  # TODO: still being tested — open to require_user once the feature is validated
def link_cross_line_trunk(
    board_id: int,
    strip_id: int,
    payload: LinkTrunkPayload,
    current_user: User,
    db: Session = Depends(get_db),
):
    return LedStripService.link_cross_line_trunk(board_id, strip_id, payload.other_strip_id, db)


@router.patch("/boards/{board_id}/led_strips/{strip_id}/terminus")
@require_user
def patch_terminus_labels(
    board_id: int,
    strip_id: int,
    payload: TerminusLabelPatch,
    current_user: User,
    db: Session = Depends(get_db),
):
    return LedStripService.patch_terminus_labels(
        board_id=board_id,
        strip_id=strip_id,
        fields_set=payload.model_fields_set,
        custom_terminus_left_name=payload.custom_terminus_left_name,
        custom_terminus_right_name=payload.custom_terminus_right_name,
        current_user=current_user,
        db=db,
    )


@router.patch("/boards/{board_id}/led_strips/{strip_id}/leds/{led_id}/label")
@require_user
def patch_led_label(
    board_id: int,
    strip_id: int,
    led_id: int,
    payload: LedLabelPatch,
    current_user: User,
    db: Session = Depends(get_db),
):
    return LedStripService.patch_led_label(
        board_id=board_id,
        strip_id=strip_id,
        led_id=led_id,
        custom_name=payload.custom_name,
        custom_subname=payload.custom_subname,
        current_user=current_user,
        db=db,
    )
