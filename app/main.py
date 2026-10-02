import os

from fastapi import FastAPI, Request, Security
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.routines import scheduler
from app.routers import payments, auth, boards, devices, ledstrips, orders, line, blog, update, adminOta, adminUsers, adminDevices, adminPrices, adminOrders, shipping, provisioning, adminSettings, adminShipping, adminGtfs, public, gifts, support, adminSupport, alerts, newsletter, adminNewsletter, departure_alerts
from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.security.jwt import get_current_user
from app.orm_models.auth import User
from app.services.blogService import backfill_embed_resize_scripts

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="Transport API",
    lifespan=lifespan
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

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

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # No-op over plain HTTP (browsers only honor HSTS on HTTPS responses) —
    # safe to send unconditionally for local/dev traffic.
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"

    # Blog artifact embeds are served from here and framed by the blog page
    # (see BlogService._sanitize_content — iframe src is restricted to
    # https:// and always sandboxed there). X-Frame-Options only supports a
    # single origin (or DENY/SAMEORIGIN) so it can't express "embeddable only
    # by our own frontend, cross-origin" — CSP frame-ancestors can, and
    # modern browsers prefer it over X-Frame-Options when both are present.
    # Every other response keeps the blanket DENY.
    if request.url.path.startswith("/static/blog-embeds/"):
        ancestors = " ".join(settings.CORS_ORIGINS)
        response.headers["Content-Security-Policy"] = f"frame-ancestors {ancestors}"
    else:
        response.headers["X-Frame-Options"] = "DENY"
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
app.include_router(alerts.router)
app.include_router(provisioning.router)
app.include_router(adminSettings.router)
app.include_router(adminShipping.router)
app.include_router(adminGtfs.router)
app.include_router(public.router)
app.include_router(gifts.router)
app.include_router(support.router)
app.include_router(adminSupport.router)
app.include_router(newsletter.router)
app.include_router(adminNewsletter.router)
app.include_router(departure_alerts.router)

# Static bundle files embedded in blog posts via <iframe> (see BlogEditorComponent's
# "Artifact" toolbar button + BlogEmbedStorage.save). Framing is re-opened for
# this path only in security_headers above. Docker mounts a volume at
# BLOG_EMBEDS_DIR so uploads survive redeploys — same reasoning as firmware.
os.makedirs(settings.BLOG_EMBEDS_DIR, exist_ok=True)
# Self-heal embeds uploaded before the resize-reporting script existed (see
# backfill_embed_resize_scripts) — otherwise those posts stay stuck with a
# fixed-height iframe + internal scrollbar on every environment until someone
# manually re-uploads them, which is exactly what made this look like it
# "only works locally" (fresh local test uploads got the script; older posts
# already sitting on the server's persisted volume didn't).
backfill_embed_resize_scripts(settings.BLOG_EMBEDS_DIR)
app.mount(
    "/static/blog-embeds",
    StaticFiles(directory=settings.BLOG_EMBEDS_DIR),
    name="blog-embeds",
)

@app.get("/")
def root():
    return {"message": "API is running"}

@app.get("/admin/hello")
def admin_hello(current_user: User = Security(get_current_user, scopes=["admin"])):
    return {"message": "Hello admin"}
