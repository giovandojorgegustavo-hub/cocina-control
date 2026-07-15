import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from cocina_control.db import Base
from cocina_control.models.base import TimestampMixin

_ROLE_ENUM = sa.Enum("cocinero", "owner", "admin", name="user_role", create_type=True)


class User(Base, TimestampMixin):
    """Application user (cocinero, owner, or admin).

    Roles:
    - cocinero: capture role (deliveries, inventory counts, delivery orders).
                Never sees cost data.
    - admin: administrative role with cost access. Cannot view the dashboard.
    - owner: full access including the dashboard.

    Email uniqueness is enforced via a case-insensitive functional index
    (ix_users_email_lower) on lower(email).  The application layer MUST
    normalize email to lowercase before persisting so that lookups and
    the unique constraint are consistent.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    # No unique=True here — uniqueness is enforced by ix_users_email_lower (see migration).
    email: Mapped[str] = mapped_column(sa.Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(sa.Text, nullable=False)
    role: Mapped[str] = mapped_column(_ROLE_ENUM, nullable=False)
