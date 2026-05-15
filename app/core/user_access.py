import asyncio
import inspect
from functools import wraps
from fastapi import Security

from app.core.security.jwt import get_current_user
from app.orm_models.auth import User


def require_roles(*roles: str):
    """
    Route decorator for role-based access control.

    Rewrites the function signature so FastAPI injects `current_user` as a
    Security dependency at route registration time.

    Two usage patterns:

      # Auth-only — user object not needed in the body
      @router.delete("/posts/{slug}")
      @require_roles("admin")
      def delete_post(slug: str, db: Session = Depends(get_db)):
          ...

      # User needed in the body — declare with bare annotation, no default
      @router.post("/posts")
      @require_roles("admin", "editor")
      def create_post(current_user: User, payload: ..., db: ...):
          BlogService.create_post(author=current_user, ...)
    """
    security_dep = Security(get_current_user, scopes=list(roles))

    def decorator(func):
        sig = inspect.signature(func)
        params = dict(sig.parameters)
        original_has_current_user = "current_user" in params

        if original_has_current_user:
            params["current_user"] = params["current_user"].replace(
                default=security_dep,
                annotation=User,
            )
            new_params = list(params.values())
        else:
            new_params = list(params.values()) + [
                inspect.Parameter(
                    "current_user",
                    kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=security_dep,
                    annotation=User,
                )
            ]

        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                if not original_has_current_user:
                    kwargs.pop("current_user", None)
                return await func(*args, **kwargs)
        else:
            @wraps(func)
            def wrapper(*args, **kwargs):
                if not original_has_current_user:
                    kwargs.pop("current_user", None)
                return func(*args, **kwargs)

        wrapper.__signature__ = sig.replace(parameters=new_params)
        badges = "  ".join(f"`{r}`" for r in roles) if roles else "`authenticated`"
        wrapper.__doc__ = f"**Requires:** {badges}\n\n" + (func.__doc__ or "").lstrip()

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Convenience shortcuts — use directly as decorators: @require_admin, etc.
# ---------------------------------------------------------------------------

require_user = require_roles()                        # any authenticated user
require_editor = require_roles("editor")
require_admin = require_roles("admin")
require_admin_or_editor = require_roles("admin", "editor")
