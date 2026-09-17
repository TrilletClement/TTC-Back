from sqlalchemy.orm import Session, joinedload
from app.orm_models.blog import BlogPost


class BlogRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_all(self, published_only: bool = True) -> list[BlogPost]:
        # to_dict()/to_list_dict() both read post.author — without eager
        # loading, listing N posts fires N extra lazy-load queries for their
        # authors on every call to the public blog list and the admin list.
        q = self.db.query(BlogPost).options(joinedload(BlogPost.author))
        if published_only:
            q = q.filter(BlogPost.published == True)
        return q.order_by(BlogPost.created_at.desc()).all()

    def get_by_slug(self, slug: str, published_only: bool = True) -> BlogPost | None:
        q = self.db.query(BlogPost).options(joinedload(BlogPost.author)).filter(BlogPost.slug == slug)
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