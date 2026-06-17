from fastapi import FastAPI, Request, Security
from fastapi.responses import Response
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware

from app.routines import scheduler
from app.routers import payments, auth, boards, devices, ledstrips, orders, line, blog, update, adminOta, adminUsers, adminDevices, adminPrices, adminOrders, shipping, provisioning, adminSettings, adminShipping, public
from app.core.config import settings
from app.core.security.jwt import get_current_user
from app.orm_models.auth import User

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="Transport API",
    lifespan=lifespan
)

@app.middleware("http")
async def handle_options(request: Request, call_next):
    if request.method == "OPTIONS":
        return Response(
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": request.headers.get("origin", "*"),
                "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
                "Access-Control-Allow-Headers": "Content-Type, Authorization, Accept, Origin",
                "Access-Control-Allow-Credentials": "true",
                "Access-Control-Max-Age": "3600",
            }
        )
    response = await call_next(request)
    return response

# CORS Middleware (keep this as-is)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS, # Utilise ta liste du fichier config.py
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router)
app.include_router(boards.router)
app.include_router(devices.router)
app.include_router(ledstrips.router)
app.include_router(orders.router)
app.include_router(line.router)
app.include_router(blog.router)
app.include_router(update.router)
app.include_router(adminOta.router)
app.include_router(adminUsers.router)
app.include_router(adminDevices.router)
app.include_router(adminPrices.router)
app.include_router(adminOrders.router)
app.include_router(payments.router)
app.include_router(shipping.router)
app.include_router(provisioning.router)
app.include_router(adminSettings.router)
app.include_router(adminShipping.router)
app.include_router(public.router)

@app.get("/")
def root():
    return {"message": "API is running"}

@app.get("/admin/hello")
def admin_hello(current_user: User = Security(get_current_user, scopes=["admin"])):
    return {"message": "Hello admin"}
