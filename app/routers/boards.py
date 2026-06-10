from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.user_access import require_user
from app.orm_models.auth import User
from app.orm_models.db import get_db
from app.repositories.board_repo import BoardRepository
from app.schemas.board import BoardCreate
from app.services.boardService import BoardService

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