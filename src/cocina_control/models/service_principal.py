import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from cocina_control.db import Base
from cocina_control.models.base import TimestampMixin


class ServicePrincipal(Base, TimestampMixin):
    """A non-human client authorized to act on behalf of a real user.

    Motivating case: the WhatsApp assistant (bonabowlinterno) registers
    deliveries and inventory counts dictated by kitchen staff.  Every
    append-only table in this schema carries created_by/updated_by with
    ON DELETE RESTRICT, which encodes a deliberate invariant: each row is
    attributable to the person responsible for it.  Giving the assistant its
    own user row would satisfy the foreign key while destroying that
    invariant — every count would read "bonabowlinterno" and the owner could
    no longer tell who miscounted.

    So the assistant holds a service token instead, and names the acting user
    per request via the X-Act-As header.  The row records the human; the
    server log records the service that carried the request.

    Revocation is immediate: flip is_active to false.  This is the reason the
    credential lives in the database rather than being a long-lived JWT — a
    signed token cannot be withdrawn before it expires without a blocklist.
    """

    __tablename__ = "service_principals"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    # SHA-256 hex of the plaintext token.  The plaintext is shown once, at
    # creation, and never stored.
    token_hash: Mapped[str] = mapped_column(sa.Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.text("true"),
        default=True,
    )
