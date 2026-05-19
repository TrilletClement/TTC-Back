from typing import Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.user_access import require_user
from app.orm_models.auth import User
from app.orm_models.db import get_db
from app.services.boardService import BoardService

router = APIRouter(prefix="/api/boards", tags=["boards"])

class BoardCreate(BaseModel):
    name: str
    board_type_id: Optional[int] = None


@router.get("/types")
@require_user
def get_board_types(current_user: User, db: Session = Depends(get_db)):
    return BoardService.get_board_types(db)


@router.get("")
@require_user
def get_boards(current_user: User, db: Session = Depends(get_db)):
    return BoardService.get_boards(current_user, db)


@router.post("/create")
@require_user
def create_board(payload: BoardCreate, current_user: User, db: Session = Depends(get_db)):
    return BoardService.create_board(payload.name, current_user, db, board_type_id=payload.board_type_id)


@router.delete("/{board_id}")
@require_user
def delete_board(
    board_id: int,
    current_user: User,
    force_unlink: bool = Query(False),
    db: Session = Depends(get_db),
):
    return BoardService.delete_board(board_id, current_user, db, force_unlink_devices=force_unlink)


@router.get("/{board_id}")
@require_user
def get_board_details(board_id: int, current_user: User, db: Session = Depends(get_db)):
    return BoardService.get_board_details(board_id, current_user, db)
