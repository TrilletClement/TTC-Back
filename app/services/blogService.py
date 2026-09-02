import os
import re
import secrets
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Optional

import nh3
from fastapi import UploadFile

from app.core.config import settings
from app.domain.exceptions import NotFoundError, BusinessError, ValidationError
from app.orm_models.auth import User
from app.orm_models.blog import BlogPost
from app.repositories.blog_repo import BlogRepository


def _generate_slug(title: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
    return slug


# Blog posts may embed one rich/interactive artifact via <iframe> (e.g. a
# published Claude Artifact or a self-hosted bundle export) — see the "Insérer
# un artifact" editor toolbar button. Allowed only with a locked-down sandbox
# so the embedded document can run its own JS but can never touch this site's
# DOM/cookies, navigate the parent, or open popups.
_TAGS = deepcopy(nh3.ALLOWED_TAGS)
_TAGS.add("iframe")

_ATTRIBUTES = deepcopy(nh3.ALLOWED_ATTRIBUTES)
_ATTRIBUTES["iframe"] = {"src", "width", "height", "title", "loading"}

# Forced unconditionally regardless of what the editor typed — nh3 applies
# these last, so an editor-supplied sandbox="allow-scripts allow-same-origin"
# (which would defeat the sandbox) is overwritten, not merged.
_SET_ATTRIBUTE_VALUES = {
    "iframe": {"sandbox": "allow-scripts", "referrerpolicy": "no-referrer"},
}


def _attribute_filter(tag: str, attribute: str, value: str) -> Optional[str]:
    if tag != "iframe" or attribute != "src":
        return value
    # Our own uploaded embeds (BlogEmbedStorage) are always trusted, even over
    # plain http:// in local dev where API_BASE_URL isn't https — anything
    # else (a hand-typed external embed) must be https.
    if value.startswith(settings.API_BASE_URL) or value.startswith("https://"):
        return value
    return None


def _sanitize_content(content: str) -> str:
    # The frontend renders this via bypassSecurityTrustHtml with no client-side
    # sanitization — this is the only place stripping scripts/event handlers/
    # javascript: URLs before the HTML is stored, so it must run on every
    # write, not just be trusted because only editors can call this.
    return nh3.clean(
        content,
        tags=_TAGS,
        attributes=_ATTRIBUTES,
        set_tag_attribute_values=_SET_ATTRIBUTE_VALUES,
        attribute_filter=_attribute_filter,
    )


def _is_editor(user: User) -> bool:
    return any(role.id in (1, 2) for role in user.roles)


class BlogAssetStorage:
    """Stores uploaded files served back under /static/blog-embeds — artifact
    bundles and post cover images share the directory (and StaticFiles mount
    in main.py); only the allowed extensions/size differ between the two."""

    def __init__(self, assets_dir: str, allowed_suffixes: tuple[str, ...], max_size_bytes: int):
        self.assets_dir = assets_dir
        self.allowed_suffixes = allowed_suffixes
        self.max_size_bytes = max_size_bytes

    def _safe_filename(self, original: str) -> str:
        # Never trust the client-supplied name as a path — strip any
        # directory components, keep a short readable stem, and always force
        # a fresh random suffix + the validated extension so uploads can't
        # collide or overwrite each other regardless of what two editors
        # upload.
        suffix = next(s for s in self.allowed_suffixes if (original or "").lower().endswith(s))
        stem = Path(original or "file").name[: -len(suffix)] if suffix else Path(original or "file").stem
        stem = re.sub(r"[^a-zA-Z0-9_-]+", "-", stem).strip("-").lower()[:50] or "file"
        return f"{stem}-{secrets.token_hex(4)}{suffix}"

    def save(self, file: UploadFile) -> str:
        if not (file.filename or "").lower().endswith(self.allowed_suffixes):
            raise ValidationError(f"Unsupported file type (allowed: {', '.join(self.allowed_suffixes)})")

        os.makedirs(self.assets_dir, exist_ok=True)
        filename = self._safe_filename(file.filename)
        path = os.path.join(self.assets_dir, filename)

        written = 0
        with open(path, "wb") as out:
            while chunk := file.file.read(1024 * 1024):
                written += len(chunk)
                if written > self.max_size_bytes:
                    out.close()
                    os.remove(path)
                    raise ValidationError(f"File too large (max {self.max_size_bytes // (1024 * 1024)} MB)")
                out.write(chunk)

        return filename


class BlogEmbedStorage(BlogAssetStorage):
    def __init__(self, assets_dir: str):
        super().__init__(assets_dir, (".html", ".htm"), 25 * 1024 * 1024)


class BlogCoverStorage(BlogAssetStorage):
    def __init__(self, assets_dir: str):
        super().__init__(assets_dir, (".jpg", ".jpeg", ".png", ".webp", ".gif"), 8 * 1024 * 1024)


class BlogService:
    def __init__(
        self,
        repo: BlogRepository,
        embed_storage: Optional[BlogEmbedStorage] = None,
        cover_storage: Optional[BlogCoverStorage] = None,
    ):
        self.repo = repo
        self.embed_storage = embed_storage
        self.cover_storage = cover_storage

    def list_posts(self, published_only: bool = True) -> list[BlogPost]:
        return self.repo.list_all(published_only)

    def upload_embed(self, file: UploadFile, author: User) -> dict:
        if not _is_editor(author):
            raise BusinessError("Only editors can upload artifact embeds")
        if not self.embed_storage:
            raise BusinessError("Embed storage is not configured")

        filename = self.embed_storage.save(file)
        return {"url": f"{settings.API_BASE_URL}/static/blog-embeds/{filename}"}

    def upload_cover(self, file: UploadFile, author: User) -> dict:
        if not _is_editor(author):
            raise BusinessError("Only editors can upload cover images")
        if not self.cover_storage:
            raise BusinessError("Cover storage is not configured")

        filename = self.cover_storage.save(file)
        return {"url": f"{settings.API_BASE_URL}/static/blog-embeds/{filename}"}

    def get_post(self, slug: str, published_only: bool = True) -> BlogPost:
        post = self.repo.get_by_slug(slug, published_only)
        if not post:
            raise NotFoundError("Article", slug)
        return post

    def create_post(
        self,
        title: str,
        description: str,
        content: str,
        author: User,
        published: bool = False,
        cover_image_url: Optional[str] = None,
    ) -> BlogPost:
        if not _is_editor(author):
            raise BusinessError("Only editors can create blog posts")

        slug = _generate_slug(title)
        if self.repo.slug_exists(slug):
            slug = f"{slug}-{int(datetime.utcnow().timestamp())}"

        post = BlogPost(
            slug=slug,
            title=title,
            description=description,
            content=_sanitize_content(content),
            author_id=author.id,
            published=published,
            cover_image_url=cover_image_url or None,
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
        cover_image_url: Optional[str] = None,
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
            post.content = _sanitize_content(content)
        if published is not None:
            post.published = published
        if cover_image_url is not None:
            post.cover_image_url = cover_image_url or None

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