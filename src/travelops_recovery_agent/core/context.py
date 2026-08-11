"""Context local to one application request."""

from contextvars import ContextVar

current_request_id: ContextVar[str | None] = ContextVar(
    "current_request_id",
    default=None,
)
