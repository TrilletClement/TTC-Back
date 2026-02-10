from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.orm_models.db import Base

class BlogPost(Base):
    __tablename__ = "blog_post"
    
    id = Column(Integer, primary_key=True)
    slug = Column(String(255), unique=True, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(String(500))
    content = Column(Text, nullable=False)  # Contenu HTML
    author_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    published = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relations
    author = relationship("User", backref="blog_posts")
    
    def to_dict(self):
        return {
            "id": self.id,
            "slug": self.slug,
            "title": self.title,
            "description": self.description,
            "content": self.content,
            "author": {
                "id": self.author.id,
                "email": self.author.email
            } if self.author else None,
            "published": self.published,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
    
    def to_list_dict(self):
        """Version sans le contenu complet pour les listings"""
        return {
            "slug": self.slug,
            "title": self.title,
            "description": self.description,
            "date": self.created_at.strftime("%Y-%m-%d") if self.created_at else None,
            "author": self.author.email if self.author else None
        }

