import os
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker, declarative_base
from sqlalchemy.orm import Session
from fastapi import Request

# PostgreSQL database URL
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg2://mylocaldb:clement@localhost:5432/mylocaldb",
)
SQL_ECHO = os.environ.get("SQL_HEAVY_LOGS", "false").strip().lower() in {"1", "true", "yes"}

# Create engine without SQLite-specific args
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # helps with stale connections in long-lived apps
    future=True,
    echo=False,
)

# Session factory
SessionLocal = scoped_session(sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    future=True,
))

# Base class for models
Base = declarative_base()

def get_db(request: Request = None):
    # Skip database for OPTIONS (CORS preflight) requests
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
