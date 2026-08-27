"""Pago de un pedido, con su comprobante y su firma.

Tabla aparte y no columnas en sales_orders porque un pedido puede pagarse en dos
actos: la mitad por Yape al confirmar y el resto en efectivo al recibir.

ck_payments_verified_needs_human es el limite de seguridad de todo el diseno del
asistente de WhatsApp. En deps.py, ACT_AS_ALLOWED_ROLES esta cerrado a proposito
para que un service token filtrado no llegue al lado del dinero. El asistente
necesita registrar pagos, asi que el acto se parte en dos: REGISTRAR (captura,
queda pending, lo hace el asistente) y VERIFICAR (la firma, exige un humano).

La regla no vive en la capa de servicio, donde se olvida en el proximo refactor:
vive en la base. Un token del asistente filtrado puede ensuciar la bandeja con
pedidos falsos; nunca puede darse por pagado a si mismo.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from cocina_control.db import Base
from cocina_control.models.base import TimestampMixin

_PAYMENT_METHOD_ENUM = sa.Enum(
    "yape", "plin", "cash", "bank_transfer", "card",
    name="payment_method",
    create_type=True,
)

_PAYMENT_STATUS_ENUM = sa.Enum(
    "pending", "verified", "rejected",
    name="payment_status",
    create_type=True,
)


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"

    __table_args__ = (
        sa.Index("ix_payments_sales_order_id", "sales_order_id"),
        sa.Index("ix_payments_status", "status"),
        sa.CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
        sa.CheckConstraint(
            "(verified_at IS NULL) = (verified_by IS NULL)",
            name="ck_payments_verified_parity",
        ),
        # EL CANDADO. Ver el docstring del modulo.
        sa.CheckConstraint(
            "status <> 'verified' OR verified_by IS NOT NULL",
            name="ck_payments_verified_needs_human",
        ),
        sa.CheckConstraint(
            "status <> 'rejected' OR rejected_reason IS NOT NULL",
            name="ck_payments_rejected_needs_reason",
        ),
        sa.CheckConstraint(
            "(proof_at IS NULL) = (proof_url IS NULL)",
            name="ck_payments_proof_parity",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    sales_order_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("sales_orders.id", ondelete="RESTRICT"), nullable=False
    )
    method: Mapped[str] = mapped_column(_PAYMENT_METHOD_ENUM, nullable=False)
    amount: Mapped[Decimal] = mapped_column(sa.Numeric(10, 2), nullable=False)
    status: Mapped[str] = mapped_column(
        _PAYMENT_STATUS_ENUM, nullable=False, default="pending"
    )
    proof_url: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    proof_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    # Lo que el OCR creyo leer, crudo. Se guarda como PROPUESTA, nunca como
    # veredicto: el ERP ya resolvio esto mismo mandando a cola humana el
    # comprobante que el OCR no pudo leer, en vez de aprobarlo. Sin aduanero no
    # hay firma.
    ocr_raw: Mapped[dict[str, Any] | None] = mapped_column(sa.JSON, nullable=True)
    ocr_confidence: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(4, 3), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    rejected_reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
