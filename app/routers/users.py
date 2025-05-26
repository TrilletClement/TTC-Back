from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from shared.db import get_db
from shared.models import User
from .schemas import UserOut  # assuming it's defined in schemas.py

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/all", response_model=list[UserOut])
def get_all_users(db: Session = Depends(get_db)):
    """
    Fetch all user names and emails.
    """
    users = db.query(User).all()
    return users