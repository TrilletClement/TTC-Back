from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker, declarative_base
from sqlalchemy.orm import Session
from fastapi import Request
import os

from app.core.config import settings

SQL_ECHO = os.environ.get("SQL_HEAVY_LOGS", "false").strip().lower() in {"1", "true", "yes"}

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    future=True,
    echo=SQL_ECHO,
)

SessionLocal = scoped_session(sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    future=True,
))

Base = declarative_base()

def get_db(request: Request = None):
    if request and request.method == "OPTIONS":
        yield None
        return
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def db_session():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
