from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.user_access import require_user
from app.orm_models.auth import User
from app.orm_models.db import get_db
from app.repositories.board_repo import BoardRepository
from app.schemas.board import BoardCreate, BoardRename
from app.services.boardService import BoardService
from app.services.board_svg_service import build_export_svg, load_board_for_export
from app.services.strip_render_service import StripRenderService
from app.core.rate_limit import limiter
from app.domain.exceptions import NotFoundError, ValidationError

router = APIRouter(prefix="/api/boards", tags=["boards"])


def get_service(db: Session = Depends(get_db)) -> BoardService:
    return BoardService(BoardRepository(db))


def get_render_service(db: Session = Depends(get_db)) -> StripRenderService:
    return StripRenderService(db, BoardService(BoardRepository(db)))


# A rendered strip only ever contains our own drawing: forbid everything else
# should the SVG be opened directly in a browser tab.
_SVG_CSP = "default-src 'none'; style-src 'unsafe-inline'; font-src data:"


def _render_headers(live: bool, leds_on: int) -> dict[str, str]:
    return {
        # Live renders change every poll; static ones only when the strip is edited.
        "Cache-Control": "private, no-store" if live else "private, max-age=300",
        "X-Content-Type-Options": "nosniff",
        # Lets the widgets show "N vehicles approaching" without a second call.
        "X-Leds-On": str(leds_on),
        "Access-Control-Expose-Headers": "X-Leds-On",
    }


@router.get("/types")
@require_user
def get_board_types(current_user: User, svc: BoardService = Depends(get_service)):
    return svc.get_board_types()


@router.get("")
@require_user
def get_boards(
    current_user: User,
    owner_email: Optional[str] = Query(None),
    svc: BoardService = Depends(get_service),
):
    return svc.get_boards(current_user, owner_email=owner_email)


@router.post("/create")
@require_user
def create_board(payload: BoardCreate, current_user: User, svc: BoardService = Depends(get_service)):
    return svc.create_board(payload.name, current_user, board_type_id=payload.board_type_id)


@router.patch("/{board_id}/name")
@require_user
def rename_board(board_id: int, payload: BoardRename, current_user: User, svc: BoardService = Depends(get_service)):
    return svc.rename_board(board_id, payload.name, current_user)


@router.delete("/{board_id}")
@require_user
def delete_board(
    board_id: int,
    current_user: User,
    force_unlink: bool = Query(False),
    svc: BoardService = Depends(get_service),
):
    return svc.delete_board(board_id, current_user, force_unlink_devices=force_unlink)


@router.get("/{board_id}")
@require_user
def get_board_details(board_id: int, current_user: User, svc: BoardService = Depends(get_service)):
    return svc.get_board_details(board_id, current_user)


@router.get("/{board_id}/status")
@require_user
def get_board_status(board_id: int, current_user: User, svc: BoardService = Depends(get_service)):
    """Lightweight realtime poll — only the fields that change (LED on/off, trip-stop flags).

    Static data (pricing, geometry, line metadata, custom names) is fetched once via
    GET /{board_id} and merged client-side; polling this endpoint every few seconds
    avoids re-sending the whole board on each tick.
    """
    return svc.get_board_status(board_id, current_user)


@router.get("/{board_id}/strips/{strip_id}/render.svg")
@limiter.limit("120/minute")
@require_user
def render_strip_svg(
    request: Request,
    board_id: int,
    strip_id: int,
    current_user: User,
    live: bool = Query(True),
    svc: StripRenderService = Depends(get_render_service),
):
    """One strip drawn exactly like the physical board (same generator as the
    export), with the LEDs currently on when `live`. Used by the app pages."""
    try:
        svg, leds_on = svc.render_svg(board_id, strip_id, live, current_user)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    headers = _render_headers(live, leds_on) | {"Content-Security-Policy": _SVG_CSP}
    return Response(content=svg, media_type="image/svg+xml", headers=headers)


@router.get("/{board_id}/strips/{strip_id}/render.png")
@limiter.limit("60/minute")
@require_user
def render_strip_png(
    request: Request,
    board_id: int,
    strip_id: int,
    current_user: User,
    live: bool = Query(True),
    width: int = Query(800),
    svc: StripRenderService = Depends(get_render_service),
):
    """PNG of the same render, for the Android home-screen widgets (which
    can't draw SVG). `width` in pixels, 200–1600."""
    try:
        png, leds_on = svc.render_png(board_id, strip_id, live, width, current_user)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return Response(content=png, media_type="image/png", headers=_render_headers(live, leds_on))


@router.get("/{board_id}/export")
@require_user
def export_board_svg(
    board_id: int,
    current_user: User,
    with_frame: bool = Query(False),
    db: Session = Depends(get_db),
):
    board = load_board_for_export(board_id, db)
    if not board:
        raise HTTPException(status_code=404, detail="Board not found")

    is_admin = any(r.name == "admin" for r in current_user.roles)
    if not is_admin and board.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Board not found")

    try:
        svg = build_export_svg(board, with_frame=with_frame, db=db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Content-Disposition": f'attachment; filename="board-{board_id}.svg"'},
    )