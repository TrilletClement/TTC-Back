import re
from datetime import datetime
from typing import Optional

from app.domain.exceptions import NotFoundError, BusinessError
from app.orm_models.auth import User
from app.orm_models.blog import BlogPost
from app.repositories.blog_repo import BlogRepository


def _generate_slug(title: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
    return slug


def _is_editor(user: User) -> bool:
    return any(role.id in (1, 2) for role in user.roles)


class BlogService:
    def __init__(self, repo: BlogRepository):
        self.repo = repo

    def list_posts(self, published_only: bool = True) -> list[BlogPost]:
        return self.repo.list_all(published_only)

    def get_post(self, slug: str, published_only: bool = True) -> BlogPost:
        post = self.repo.get_by_slug(slug, published_only)
        if not post:
            raise NotFoundError("Article", slug)
        return post

    def create_post(self, title: str, description: str, content: str, author: User, published: bool = False) -> BlogPost:
        if not _is_editor(author):
            raise BusinessError("Only editors can create blog posts")

        slug = _generate_slug(title)
        if self.repo.slug_exists(slug):
            slug = f"{slug}-{int(datetime.utcnow().timestamp())}"

        post = BlogPost(
            slug=slug,
            title=title,
            description=description,
            content=content,
            author_id=author.id,
            published=published,
        )
        return self.repo.save(post)

    def update_post(
        self,
        slug: str,
        author: User,
        title: Optional[str] = None,
        description: Optional[str] = None,
        content: Optional[str] = None,
        published: Optional[bool] = None,
    ) -> BlogPost:
        post = self.repo.get_by_slug(slug, published_only=False)
        if not post:
            raise NotFoundError("Article", slug)
        if not (_is_editor(author) or post.author_id == author.id):
            raise BusinessError("You don't have permission to edit this post")

        if title:
            post.title = title
            post.slug  = _generate_slug(title)
        if description:
            post.description = description
        if content:
            post.content = content
        if published is not None:
            post.published = published

        post.updated_at = datetime.utcnow()
        return self.repo.save(post)

    def delete_post(self, slug: str, author: User) -> dict:
        post = self.repo.get_by_slug(slug, published_only=False)
        if not post:
            raise NotFoundError("Article", slug)
        if not (_is_editor(author) or post.author_id == author.id):
            raise BusinessError("You don't have permission to delete this post")
        self.repo.delete(post)
        return {"message": "Article deleted successfully"}