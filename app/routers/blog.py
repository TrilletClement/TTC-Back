from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.user_access import require_admin, require_admin_or_editor, require_editor
from app.domain.exceptions import NotFoundError, BusinessError, ValidationError
from app.orm_models.auth import User
from app.orm_models.db import get_db
from app.repositories.blog_repo import BlogRepository
from app.schemas.blog import BlogPostCreate, BlogPostPublish, BlogPostUpdate
from app.services.blogService import BlogCoverStorage, BlogEmbedStorage, BlogService

router = APIRouter(prefix="/api/blog", tags=["blog"])


def get_service(db: Session = Depends(get_db)) -> BlogService:
    return BlogService(
        BlogRepository(db),
        BlogEmbedStorage(settings.BLOG_EMBEDS_DIR),
        BlogCoverStorage(settings.BLOG_EMBEDS_DIR),
    )


def _handle(exc: NotFoundError | BusinessError | ValidationError) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValidationError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=403, detail=str(exc))


# ── public ────────────────────────────────────────────────────────────────────

@router.get("/posts")
def get_all_posts(svc: BlogService = Depends(get_service)):
    return [p.to_list_dict() for p in svc.list_posts(published_only=True)]


@router.get("/posts/{slug}")
def get_post(slug: str, svc: BlogService = Depends(get_service)):
    try:
        return svc.get_post(slug, published_only=True).to_dict()
    except NotFoundError as e:
        raise _handle(e)


# ── admin + editor ────────────────────────────────────────────────────────────

@router.get("/admin/posts")
@require_admin_or_editor
def get_all_posts_admin(svc: BlogService = Depends(get_service)):
    return [p.to_dict() for p in svc.list_posts(published_only=False)]


@router.get("/admin/preview/{slug}")
@require_admin_or_editor
def get_post_preview(slug: str, svc: BlogService = Depends(get_service)):
    try:
        return svc.get_post(slug, published_only=False).to_dict()
    except NotFoundError as e:
        raise _handle(e)


# ── admin ─────────────────────────────────────────────────────────────────────

@router.patch("/posts/{slug}/publish")
@require_admin
def set_published(slug: str, payload: BlogPostPublish, current_user: User, svc: BlogService = Depends(get_service)):
    try:
        return svc.update_post(slug, current_user, published=payload.published).to_dict()
    except (NotFoundError, BusinessError) as e:
        raise _handle(e)


@router.delete("/posts/{slug}")
@require_admin
def delete_post(slug: str, current_user: User, svc: BlogService = Depends(get_service)):
    try:
        return svc.delete_post(slug, current_user)
    except (NotFoundError, BusinessError) as e:
        raise _handle(e)


# ── editor ────────────────────────────────────────────────────────────────────

@router.post("/embeds")
@require_editor
def upload_embed(current_user: User, file: UploadFile = File(...), svc: BlogService = Depends(get_service)):
    try:
        return svc.upload_embed(file, current_user)
    except (BusinessError, ValidationError) as e:
        raise _handle(e)


@router.post("/covers")
@require_editor
def upload_cover(current_user: User, file: UploadFile = File(...), svc: BlogService = Depends(get_service)):
    try:
        return svc.upload_cover(file, current_user)
    except (BusinessError, ValidationError) as e:
        raise _handle(e)


@router.post("/posts")
@require_editor
def create_post(payload: BlogPostCreate, current_user: User, svc: BlogService = Depends(get_service)):
    is_admin = any(r.name == "admin" for r in current_user.roles)
    try:
        return svc.create_post(
            title=payload.title,
            description=payload.description,
            content=payload.content,
            author=current_user,
            published=payload.published if is_admin else False,
            cover_image_url=payload.cover_image_url,
        ).to_dict()
    except (NotFoundError, BusinessError) as e:
        raise _handle(e)


@router.put("/posts/{slug}")
@require_editor
def update_post(slug: str, payload: BlogPostUpdate, current_user: User, svc: BlogService = Depends(get_service)):
    try:
        return svc.update_post(
            slug=slug,
            author=current_user,
            title=payload.title,
            description=payload.description,
            content=payload.content,
            cover_image_url=payload.cover_image_url,
        ).to_dict()
    except (NotFoundError, BusinessError) as e:
        raise _handle(e)