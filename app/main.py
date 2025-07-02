import sys
import os
# Add the project root to the Python path (before importing other modules)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
sys.path.insert(0, BASE_DIR)
from fastapi import FastAPI
from strawberry.fastapi import GraphQLRouter
from app.routers import users, esp
from app.graphql_schema import schema
from app.routines import scheduler
from apscheduler.schedulers.background import BackgroundScheduler

from shared.db import Base, engine

# Initialize FastAPI app
app = FastAPI(title="FastAPI Scalable Starter")

# Create tables on startup if needed
@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    scheduler.start()  # <-- Start scheduled jobs

# Include routers
app.include_router(users.router)
app.include_router(esp.router)

@app.get("/")
def read_root():
    return {"message": "Welcome to the FastAPI Starter!"}

# Add GraphQL router
graphql_app = GraphQLRouter(schema)
app.include_router(graphql_app, prefix="/graphql")

