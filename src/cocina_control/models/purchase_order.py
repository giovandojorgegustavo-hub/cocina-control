"""Purchase order models — v0.3 partidas + costos.

Four append-only tables:
  - PurchaseOrder          : owner-created order to a supplier
  - PurchaseOrderItem      : expected product + qty per order line
  - PurchaseOrderItemCost  : unit cost history per item (owner-only)
  - PurchaseOrderStatusEvent: immutable event log (closed/reopened/annulled)
"""

import uuid
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from cocina_control.db import Base
from cocina_control.models.base import AppendOnlyMixin

__all__ = [
    "PurchaseOrder",
    "PurchaseOrderItem",
    "PurchaseOrderItemCost",
    "PurchaseOrderStatusEvent",
]

_PURCHASE_ORDER_STATUS_EVENT_TYPE_ENUM = sa.Enum(
    "closed_auto", "closed_manual", "reopened", "annulled",
    name="purchase_order_status_event_type",
    create_type=True,
)


class PurchaseOrder(Base, AppendOnlyMixin):
    """An order placed with a supplier.

    The existence of this row is the implicit 'open' event — no status column.
    Lifecycle transitions are tracked in PurchaseOrderStatusEvent.
    Corrections use the standard append-only pattern (corrects_id chain).
    """

    __tablename__ = "purchase_orders"

    __table_args__ = (
        sa.Index("ix_purchase_orders_created_by", "created_by"),
        sa.Index("ix_purchase_orders_corrects_id", "corrects_id"),
        sa.UniqueConstraint("corrects_id", name="uq_purchase_orders_corrects_id"),
        sa.CheckConstraint(
            "corrects_id IS DISTINCT FROM id",
            name="ck_purchase_orders_no_self_correction",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    # Free-text for now; a 'suppliers' table with FK is deferred to a future backend.
    supplier_name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    corrects_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("purchase_orders.id", ondelete="RESTRICT"),
        nullable=True,
    )
    reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


class PurchaseOrderItem(Base, AppendOnlyMixin):
    """One product line in a purchase order (expected qty).

    The partial unique index uq_purchase_order_items_root_per_product prevents
    two ROOTS (corrects_id IS NULL) for the same product in the same order,
    which combined with UNIQUE(corrects_id) globally guarantees a single linear
    correction chain per product.

    Note: this index identifies the ROOT of the chain, NOT the leaf. To get the
    current active item (leaf), query with:
        NOT EXISTS (SELECT 1 FROM purchase_order_items x WHERE x.corrects_id = t.id)
    """

    __tablename__ = "purchase_order_items"

    __table_args__ = (
        sa.Index("ix_purchase_order_items_order_id", "purchase_order_id"),
        sa.Index("ix_purchase_order_items_product_id", "product_id"),
        sa.Index("ix_purchase_order_items_corrects_id", "corrects_id"),
        # Partial unique: one ROOT item (corrects_id IS NULL) per product per order.
        sa.Index(
            "uq_purchase_order_items_root_per_product",
            "purchase_order_id",
            "product_id",
            unique=True,
            postgresql_where=sa.text("corrects_id IS NULL"),
        ),
        sa.UniqueConstraint("corrects_id", name="uq_purchase_order_items_corrects_id"),
        sa.CheckConstraint(
            "corrects_id IS DISTINCT FROM id",
            name="ck_purchase_order_items_no_self_correction",
        ),
        sa.CheckConstraint(
            "expected_qty > 0",
            name="ck_purchase_order_items_expected_qty_positive",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("purchase_orders.id", ondelete="RESTRICT"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    expected_qty: Mapped[Decimal] = mapped_column(sa.Numeric, nullable=False)
    # issue #101: una correccion con removed=true quita la linea de la orden
    removed: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    corrects_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("purchase_order_items.id", ondelete="RESTRICT"),
        nullable=True,
    )
    reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


class PurchaseOrderItemCost(Base, AppendOnlyMixin):
    """Unit cost for a purchase order item.

    Owner-only at the app layer. Each change creates a new row (corrects_id
    chain). The weighted-average price (PMP) is derived from the chain, not
    stored directly — Backend #3 responsibility.
    """

    __tablename__ = "purchase_order_item_costs"

    __table_args__ = (
        sa.Index("ix_purchase_order_item_costs_item_id", "purchase_order_item_id"),
        sa.Index("ix_purchase_order_item_costs_corrects_id", "corrects_id"),
        sa.UniqueConstraint("corrects_id", name="uq_purchase_order_item_costs_corrects_id"),
        sa.CheckConstraint(
            "corrects_id IS DISTINCT FROM id",
            name="ck_purchase_order_item_costs_no_self_correction",
        ),
        sa.CheckConstraint(
            "unit_cost > 0",
            name="ck_purchase_order_item_costs_positive",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    purchase_order_item_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("purchase_order_items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    unit_cost: Mapped[Decimal] = mapped_column(sa.Numeric, nullable=False)
    corrects_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("purchase_order_item_costs.id", ondelete="RESTRICT"),
        nullable=True,
    )
    reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


class PurchaseOrderStatusEvent(Base, AppendOnlyMixin):
    """Immutable event log for purchase order lifecycle transitions.

    The 'open' event is implicit (the purchase_orders row existing).
    'partially_received' is derived from item saldo, not persisted.
    Only explicit operator/owner actions produce rows here.

    No corrects_id — events are immutable by design.
    """

    __tablename__ = "purchase_order_status_events"

    __table_args__ = (
        # DESC index to fetch the latest event quickly without a full scan.
        sa.Index(
            "ix_purchase_order_status_events_order_created",
            "purchase_order_id",
            sa.text("created_at DESC"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("purchase_orders.id", ondelete="RESTRICT"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(
        _PURCHASE_ORDER_STATUS_EVENT_TYPE_ENUM,
        nullable=False,
    )
    # reason is optional for 'closed', mandatory at app-layer for 'annulled'/'reopened'.
    reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
