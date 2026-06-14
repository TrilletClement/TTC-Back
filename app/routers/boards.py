from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.user_access import require_user
from app.orm_models.auth import User
from app.orm_models.db import get_db
from app.repositories.board_repo import BoardRepository
from app.schemas.board import BoardCreate
from app.services.boardService import BoardService
from app.services.board_svg_service import build_export_svg, load_board_for_export

router = APIRouter(prefix="/api/boards", tags=["boards"])


def get_service(db: Session = Depends(get_db)) -> BoardService:
    return BoardService(BoardRepository(db))


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