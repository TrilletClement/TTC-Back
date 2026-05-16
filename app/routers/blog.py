from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.core.user_access import require_admin, require_admin_or_editor, require_editor
from app.orm_models.auth import User
from app.orm_models.db import get_db
from app.services.blogService import BlogService

router = APIRouter(prefix="/api/blog", tags=["blog"])


class BlogPostCreate(BaseModel):
    title: str
    description: str
    content: str
    published: bool = False


class BlogPostUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None


class BlogPostPublish(BaseModel):
    published: bool


# Public routes
@router.get("/posts")
def get_all_posts(db: Session = Depends(get_db)):
    """Récupère tous les articles publiés"""
    posts = BlogService.get_all_posts(db, published_only=True)
    return [post.to_list_dict() for post in posts]


@router.get("/posts/{slug}")
def get_post(slug: str, db: Session = Depends(get_db)):
    """Récupère un article par son slug"""
    post = BlogService.get_post_by_slug(slug, db, published_only=True)
    return post.to_dict()


# Admin + editor routes
@router.get("/admin/posts")
@require_admin_or_editor
def get_all_posts_admin(db: Session = Depends(get_db)):
    """Récupère tous les articles (publics et brouillons)"""
    posts = BlogService.get_all_posts(db, published_only=False)
    return [post.to_dict() for post in posts]


@router.get("/admin/preview/{slug}")
@require_admin_or_editor
def get_post_preview(slug: str, db: Session = Depends(get_db)):
    """Récupère un article par slug (publié ou brouillon) pour prévisualisation"""
    post = BlogService.get_post_by_slug(slug, db, published_only=False)
    return post.to_dict()


# Admin-only routes
@router.patch("/posts/{slug}/publish")
@require_admin
def set_published(slug: str, payload: BlogPostPublish, current_user: User, db: Session = Depends(get_db)):
    """Publie ou dépublie un article"""
    return BlogService.update_post(
        slug=slug,
        title=None,
        description=None,
        content=None,
        published=payload.published,
        author=current_user,
        db=db,
    ).to_dict()


@router.delete("/posts/{slug}")
@require_admin
def delete_post(slug: str, current_user: User, db: Session = Depends(get_db)):
    """Supprime un article"""
    return BlogService.delete_post(slug, current_user, db)


# Editor routes
@router.post("/posts")
@require_editor
def create_post(
    payload: BlogPostCreate,
    current_user: User,
    db: Session = Depends(get_db),
):
    """Crée un nouvel article — seul l'admin peut le publier directement"""
    is_admin = any(r.name == "admin" for r in current_user.roles)
    return BlogService.create_post(
        title=payload.title,
        description=payload.description,
        content=payload.content,
        author=current_user,
        db=db,
        published=payload.published if is_admin else False,
    ).to_dict()


@router.put("/posts/{slug}")
@require_editor
def update_post(
    slug: str,
    payload: BlogPostUpdate,
    current_user: User,
    db: Session = Depends(get_db),
):
    """Met à jour le contenu d'un article (auteur uniquement)"""
    return BlogService.update_post(
        slug=slug,
        title=payload.title,
        description=payload.description,
        content=payload.content,
        published=None,
        author=current_user,
        db=db,
    ).to_dict()
