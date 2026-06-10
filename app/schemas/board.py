from typing import Optional
from pydantic import BaseModel


class BoardCreate(BaseModel):
    name: str
    board_type_id: Optional[int] = None


class BoardDeleteQuery(BaseModel):
    force_unlink: bool = False