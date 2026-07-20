from typing import Optional
from pydantic import BaseModel
from datetime import datetime


class TicketCreate(BaseModel):
    subject:  str
    message:  str
    order_id: Optional[int] = None


class TicketOut(BaseModel):
    id:          int
    subject:     str
    message:     str
    status:      str
    admin_reply: Optional[str] = None
    replied_at:  Optional[datetime] = None
    created_at:  Optional[datetime] = None
    order_id:    Optional[int] = None
    order_ref:   Optional[str] = None


class AdminTicketOut(TicketOut):
    user_email: Optional[str] = None
    archived:   bool = False


class TicketReply(BaseModel):
    message: str
    resolve: bool = True
