from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, List
from app.services.blogService import BlogService
from app.core.security.jwt import get_current_user
from app.orm_models.db import get_db
from app.orm_models.auth import User

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
    published: Optional[bool] = None
    
# Routes publiques
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

# Routes protégées (éditeurs uniquement)
@router.get("/admin/posts")
def get_all_posts_admin(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Récupère tous les articles (publics et brouillons) - Admin uniquement"""
    if not any(role.id == 1 or role.id == 2 for role in current_user.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Editor role required"
        )
    posts = BlogService.get_all_posts(db, published_only=False)
    return [post.to_dict() for post in posts]

@router.post("/posts")
def create_post(
    payload: BlogPostCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Crée un nouvel article - Éditeurs uniquement"""
    post = BlogService.create_post(
        title=payload.title,
        description=payload.description,
        content=payload.content,
        author=current_user,
        db=db,
        published=payload.published
    )
    return post.to_dict()

@router.put("/posts/{slug}")
def update_post(
    slug: str,
    payload: BlogPostUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Met à jour un article - Éditeurs ou auteur uniquement"""
    post = BlogService.update_post(
        slug=slug,
        title=payload.title,
        description=payload.description,
        content=payload.content,
        published=payload.published,
        author=current_user,
        db=db
    )
    return post.to_dict()

@router.delete("/posts/{slug}")
def delete_post(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Supprime un article - Éditeurs ou auteur uniquement"""
    return BlogService.delete_post(slug, current_user, db)