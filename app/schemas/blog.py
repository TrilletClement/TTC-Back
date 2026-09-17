from typing import Any, Optional
from pydantic import BaseModel, Field


# `blocks` : document de l'éditeur visuel. Volontairement typé large
# (list[dict]) côté API — la forme de chaque bloc est validée par le frontend
# qui en est l'unique producteur, et le HTML qui compte est `content`, lui
# assaini. Un schéma Pydantic par type de bloc obligerait à faire évoluer le
# backend à chaque nouveau bloc éditorial.
class BlogPostCreate(BaseModel):
    title:            str
    description:      str
    content:          str
    published:        bool = False
    cover_image_url:  Optional[str] = None
    blocks:           Optional[list[dict[str, Any]]] = None
    accent_color:     Optional[str] = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")


class BlogPostUpdate(BaseModel):
    title:            Optional[str] = None
    description:      Optional[str] = None
    content:          Optional[str] = None
    cover_image_url:  Optional[str] = None
    blocks:           Optional[list[dict[str, Any]]] = None
    accent_color:     Optional[str] = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")


class BlogPostPublish(BaseModel):
    published: bool
