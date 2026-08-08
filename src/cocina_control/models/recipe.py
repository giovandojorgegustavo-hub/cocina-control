"""Composicion de platos — el puente entre lo que se vende y lo que se consume.

ProductRecipe es la plantilla del plato fijo. DeliveryOrderItemIngredient es lo
que realmente llevo una linea de pedido concreta, que es la unica verdad
disponible para los armables. Ver el docstring de la migracion
0018_composicion_platos para el porque de la separacion.
"""

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from cocina_control.db import Base
from cocina_control.models.base import AppendOnlyMixin, TimestampMixin

_INGREDIENT_STATUS_ENUM = sa.Enum(
    "included",
    "out_of_stock",
    name="delivery_order_ingredient_status",
    create_type=True,
)


class ProductRecipe(Base, TimestampMixin):
    """Que insumo lleva un plato de receta fija, y cuanto si ya se midio."""

    __tablename__ = "product_recipe"

    __table_args__ = (
        sa.Index(
            "ix_product_recipe_product_ingredient_unique",
            "product_id",
            "ingredient_id",
            unique=True,
        ),
        sa.Index("ix_product_recipe_ingredient_id", "ingredient_id"),
        sa.CheckConstraint(
            "product_id <> ingredient_id",
            name="ck_product_recipe_no_self_reference",
        ),
        sa.CheckConstraint(
            "quantity IS NULL OR quantity > 0",
            name="ck_product_recipe_quantity_positive",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    # NULL mientras la cocina no haya medido el gramaje. Un ingrediente sin
    # cantidad ya dice que insumo toca el plato; inventar el numero no.
    quantity: Mapped[Decimal | None] = mapped_column(sa.Numeric, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )


class DeliveryOrderItemIngredient(Base, AppendOnlyMixin):
    """Que llevo de verdad esta linea de pedido — o que falto por quiebre."""

    __tablename__ = "delivery_order_item_ingredients"

    __table_args__ = (
        sa.Index(
            "ix_doi_ingredients_item_ingredient_unique",
            "delivery_order_item_id",
            "ingredient_id",
            unique=True,
        ),
        sa.Index("ix_doi_ingredients_ingredient_id", "ingredient_id"),
        sa.CheckConstraint(
            "quantity IS NULL OR quantity > 0",
            name="ck_doi_ingredients_quantity_positive",
        ),
        sa.CheckConstraint(
            "status <> 'out_of_stock' OR quantity IS NULL",
            name="ck_doi_ingredients_out_of_stock_has_no_quantity",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    delivery_order_item_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("delivery_order_items.id", ondelete="RESTRICT"), nullable=False
    )
    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[Decimal | None] = mapped_column(sa.Numeric, nullable=True)
    # out_of_stock = el pedido lo pedia y no habia. Es la senal de quiebre que
    # la cocina genera sin trabajo extra; borrarla la perderia para compras.
    status: Mapped[str] = mapped_column(_INGREDIENT_STATUS_ENUM, nullable=False, default="included")
