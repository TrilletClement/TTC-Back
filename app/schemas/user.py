from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class RoleOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class UserOut(BaseModel):
    id: int
    email: str
    active: bool
    roles: list[RoleOut] = []
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RoleCreate(BaseModel):
    name: str
    description: Optional[str] = None


class AssignRoleRequest(BaseModel):
    role_id: int