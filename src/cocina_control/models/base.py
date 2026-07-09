"""Reusable mixins for all models."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    """Adds created_at.

    server_default=func.now() lets PostgreSQL stamp the row on INSERT.
    default=_utcnow is a Python-side fallback for objects constructed outside
    of an active DB session (e.g. unit tests that never flush).
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=_utcnow,
        nullable=False,
    )


class AppendOnlyMixin(TimestampMixin):
    """Shared columns for append-only tables.

    Provides created_by (FK to users) and created_at (via TimestampMixin).
    Each concrete model must declare its own corrects_id self-FK because
    SQLAlchemy requires the FK target to name the concrete table.
    """

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
