from typing import Optional
from pydantic import BaseModel, Field


class BoardCreate(BaseModel):
    name: str
    board_type_id: Optional[int] = None


class BoardRename(BaseModel):
    name: str = Field(max_length=100)


class BoardDeleteQuery(BaseModel):
    force_unlink: bool = False