from sqlalchemy.orm import Session
from app.orm_models.blog import BlogPost


class BlogRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_all(self, published_only: bool = True) -> list[BlogPost]:
        q = self.db.query(BlogPost)
        if published_only:
            q = q.filter(BlogPost.published == True)
        return q.order_by(BlogPost.created_at.desc()).all()

    def get_by_slug(self, slug: str, published_only: bool = True) -> BlogPost | None:
        q = self.db.query(BlogPost).filter(BlogPost.slug == slug)
        if published_only:
            q = q.filter(BlogPost.published == True)
        return q.first()

    def slug_exists(self, slug: str) -> bool:
        return self.db.query(BlogPost).filter(BlogPost.slug == slug).first() is not None

    def save(self, post: BlogPost) -> BlogPost:
        self.db.add(post)
        self.db.commit()
        self.db.refresh(post)
        return post

    def delete(self, post: BlogPost) -> None:
        self.db.delete(post)
        self.db.commit()