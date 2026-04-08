from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, DateTime
from sqlalchemy.orm import relationship
from flask_security import UserMixin, RoleMixin

from app.orm_models.db import Base


class Role(Base, RoleMixin):
    __tablename__ = "role"
    id = Column(Integer, primary_key=True)
    name = Column(String(80), unique=True)
    description = Column(String(255))


class User(Base, UserMixin):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True)
    email = Column(String(120), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    active = Column(Boolean, default=True)
    fs_uniquifier = Column(String(255), unique=True, nullable=False)
    roles = relationship("Role", secondary="user_roles", backref="users")
    reset_token = Column(String(100), nullable=True)         
    reset_token_expiry = Column(DateTime, nullable=True)   
    confirmation_token = Column(String(100), nullable=True)
    confirmation_token_expiry = Column(DateTime, nullable=True)


class UserRoles(Base):
    __tablename__ = "user_roles"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id"))
    role_id = Column(Integer, ForeignKey("role.id"))