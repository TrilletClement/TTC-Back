from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, DateTime, func
from sqlalchemy.orm import relationship

from app.orm_models.db import Base


class Role(Base):
    __tablename__ = "role"
    id = Column(Integer, primary_key=True)
    name = Column(String(80), unique=True)
    description = Column(String(255))


class User(Base):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True)
    email = Column(String(120), unique=True, nullable=False)
    password = Column(String(255), nullable=True) # Nullable to allow Google OAuth users without a password
    active = Column(Boolean, default=True)
    fs_uniquifier = Column(String(255), unique=True, nullable=False)
    roles = relationship("Role", secondary="user_roles", backref="users")
    reset_token = Column(String(100), nullable=True)         
    reset_token_expiry = Column(DateTime, nullable=True)   
    confirmation_token = Column(String(100), nullable=True)
    confirmation_token_expiry = Column(DateTime, nullable=True)
    oauth_handoff_token = Column(String(100), nullable=True)
    oauth_handoff_token_expiry = Column(DateTime, nullable=True)
    preferred_agency = Column(String(50), nullable=True)
    google_id = Column(String, nullable=True, unique=True, index=True)
    alert_display_pref = Column(String(10), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=True, server_default=func.now())


class UserRoles(Base):
    __tablename__ = "user_roles"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id"))
    role_id = Column(Integer, ForeignKey("role.id"))