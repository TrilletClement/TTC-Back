from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.orm_models.blog import BlogPost
from app.orm_models.auth import User
from typing import List, Optional
from datetime import datetime
import re

class BlogService:
    
    @staticmethod
    def generate_slug(title: str) -> str:
        """Génère un slug à partir du titre"""
        slug = title.lower()
        slug = re.sub(r'[^a-z0-9]+', '-', slug)
        slug = slug.strip('-')
        return slug
    
    @staticmethod
    def get_all_posts(db: Session, published_only: bool = True) -> List[BlogPost]:
        """Récupère tous les articles"""
        query = db.query(BlogPost)
        if published_only:
            query = query.filter(BlogPost.published == True)
        return query.order_by(BlogPost.created_at.desc()).all()
    
    @staticmethod
    def get_post_by_slug(slug: str, db: Session, published_only: bool = True) -> Optional[BlogPost]:
        """Récupère un article par son slug"""
        query = db.query(BlogPost).filter(BlogPost.slug == slug)
        if published_only:
            query = query.filter(BlogPost.published == True)
        post = query.first()
        if not post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Article not found"
            )
        return post
    
    @staticmethod
    def create_post(
        title: str,
        description: str,
        content: str,
        author: User,
        db: Session,
        published: bool = False
    ) -> BlogPost:
        """Crée un nouvel article"""
        # Vérifie que l'utilisateur a le rôle editor
        if not any(role.id == 1 or role.id == 2 for role in author.roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only editors can create blog posts"
            )
        
        slug = BlogService.generate_slug(title)
        
        # Vérifie si le slug existe déjà
        existing = db.query(BlogPost).filter(BlogPost.slug == slug).first()
        if existing:
            # Ajoute un timestamp au slug
            slug = f"{slug}-{int(datetime.utcnow().timestamp())}"
        
        new_post = BlogPost(
            slug=slug,
            title=title,
            description=description,
            content=content,
            author_id=author.id,
            published=published
        )
        
        db.add(new_post)
        db.commit()
        db.refresh(new_post)
        
        return new_post
    
    @staticmethod
    def update_post(
        slug: str,
        title: Optional[str],
        description: Optional[str],
        content: Optional[str],
        published: Optional[bool],
        author: User,
        db: Session
    ) -> BlogPost:
        """Met à jour un article"""
        post = db.query(BlogPost).filter(BlogPost.slug == slug).first()
        
        if not post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Article not found"
            )
        
        # Vérifie les permissions
        is_editor = any(role.id == 1 or role.id == 2 for role in author.roles)
        is_author = post.author_id == author.id
        
        if not (is_editor or is_author):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to edit this post"
            )
        
        if title:
            post.title = title
            post.slug = BlogService.generate_slug(title)
        if description:
            post.description = description
        if content:
            post.content = content
        if published is not None:
            post.published = published
        
        post.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(post)
        
        return post
    
    @staticmethod
    def delete_post(slug: str, author: User, db: Session) -> dict:
        """Supprime un article"""
        post = db.query(BlogPost).filter(BlogPost.slug == slug).first()
        
        if not post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Article not found"
            )
        
        # Vérifie les permissions
        is_editor = any(role.id == 1 or role.id == 2 for role in author.roles)
        is_author = post.author_id == author.id
        
        if not (is_editor or is_author):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to delete this post"
            )
        
        db.delete(post)
        db.commit()
        
        return {"message": "Article deleted successfully"}