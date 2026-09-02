from typing import Optional
from pydantic import BaseModel


class BlogPostCreate(BaseModel):
    title:            str
    description:      str
    content:          str
    published:        bool = False
    cover_image_url:  Optional[str] = None


class BlogPostUpdate(BaseModel):
    title:            Optional[str] = None
    description:      Optional[str] = None
    content:          Optional[str] = None
    cover_image_url:  Optional[str] = None


class BlogPostPublish(BaseModel):
    published: bool