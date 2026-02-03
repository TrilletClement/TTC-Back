from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.services.boardService import BoardService
from app.core.security.jwt import get_current_user
from app.orm_models.db import get_db
from app.orm_models.auth import User

router = APIRouter(prefix="/api/boards", tags=["boards"])

class BoardCreate(BaseModel):
    name: str

@router.get("")
def get_boards(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return BoardService.get_boards(current_user, db)

@router.post("/create")
def create_board(
    payload: BoardCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return BoardService.create_board(payload.name, current_user, db)

@router.delete("/{board_id}")
def delete_board(
    board_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return BoardService.delete_board(board_id, current_user, db)

@router.get("/{board_id}")
def get_board_details(
    board_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return BoardService.get_board_details(board_id, current_user, db)

