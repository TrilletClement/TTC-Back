from fastapi import APIRouter
from shared.db import get_db
from shared.models import User
from .schemas import UserOut  # assuming it's defined in schemas.py

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/all", response_model=list[UserOut])
def get_all_users():
    """
    Fetch all user names and emails.
    """
    with get_db() as db:
        users = db.query(User).all()
        return users