from pydantic import BaseModel


class LineIdsIn(BaseModel):
    line_ids: list[int]
