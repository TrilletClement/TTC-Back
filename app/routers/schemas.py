from pydantic import BaseModel
from typing import List

class LedStripCompact(BaseModel):
    id: int
    v: List[int]

class LedStripStatusResponse(BaseModel):
    strips: List[LedStripCompact]


class UserOut(BaseModel):
    id: int
    email: str

    class Config:
        from_attributes = True