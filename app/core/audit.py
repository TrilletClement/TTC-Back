"""
Minimal audit trail for sensitive admin actions (role changes, order/device
mutations). Uses its own logger + handler so entries are emitted regardless
of whatever logging config (or lack of one) the rest of the app has —
these are the lines you'd need to trace a compromised admin token.
"""
import logging

from app.orm_models.auth import User

_audit_log = logging.getLogger("audit")
_audit_log.setLevel(logging.INFO)
_audit_log.propagate = False
if not _audit_log.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s AUDIT %(message)s"))
    _audit_log.addHandler(_handler)


def record(actor: User, action: str, target: str, detail: str = "") -> None:
    _audit_log.info(
        "actor=%s(%s) action=%s target=%s%s",
        actor.email, actor.id, action, target,
        f" detail={detail}" if detail else "",
    )
