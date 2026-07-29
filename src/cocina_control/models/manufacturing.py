"""Fabricacion de preparados — recetas versionadas y batches registrados.

Diseno completo en docs/backend/diseno-fabricacion.md. Mirrors migration 0017.

El modelo es: pesar lo que entra, mostrar los extras escalados a ese peso,
contar lo que sale. Con eso el factor de rinde deja de ser un estimado declarado
y pasa a ser medido.

ESTE ES UN LEDGER DE AUDITORIA. El operario que registra es la persona a la que
despues se le audita el faltante. Varias reglas de abajo NO se pueden expresar
como CHECK y viven en triggers de la migracion 0017 — estan documentadas en cada
clase para que no se pierdan de vista al leer solo el modelo.

  ManufacturingRecipe         IDENTIDAD del preparado — una fila para siempre
  ManufacturingRecipeVersion  los parametros versionados (append-only)
  ManufacturingRecipeItem     los extras — cuelgan de la IDENTIDAD
  ManufacturingBatch          el hecho ocurrido — inmutable
  ManufacturingBatchInput     snapshot de lo consumido (append-only)
  ManufacturingBatchEvent     anulacion de un batch (append-only, owner/admin)
"""

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from cocina_control.db import Base
from cocina_control.models.base import AppendOnlyMixin, TimestampMixin

# 'integer' = el huevo, la unica unidad indivisible. Se redondea Y se guarda el
# entero: guardar 4,96 cuando se pusieron 5 desfasaria el teorico en cada batch.
_ROUNDING_ENUM = sa.Enum("exact", "integer", name="manufacturing_rounding", create_type=True)

# Que se midio de verdad. Solo 'measured' calibra el rinde. Cubre los DOS lados:
# aceptar el default de entrada sin pesar es tan falso como aceptar el de salida
# sin contar — y pesar tiene MAS friccion que contar bolsitas, asi que el default
# de entrada es el mas probable de aceptarse a ciegas.
_MEASUREMENT_ENUM = sa.Enum(
    "measured",
    "default_input",
    "default_output",
    "both_defaults",
    name="manufacturing_measurement",
    create_type=True,
)

_BATCH_EVENT_ENUM = sa.Enum("annulled", name="manufacturing_batch_event_type", create_type=True)


class ManufacturingRecipe(Base, AppendOnlyMixin):
    """Identidad de un preparado. Una fila por producto fabricado, para siempre.

    `output_product_id` es UNIQUE y NO se versiona. Cuando vivia en la fila
    versionada, una cadena de corrects_id podia secuestrar la receta hacia otro
    producto y dejar dos recetas vigentes para el mismo preparado.
    """

    __tablename__ = "manufacturing_recipes"

    __table_args__ = (
        sa.UniqueConstraint("output_product_id", name="uq_manufacturing_recipes_output_product_id"),
        # Target de la FK compuesta desde batches.
        sa.UniqueConstraint("id", "output_product_id", name="uq_manufacturing_recipes_id_output"),
        sa.Index("ix_manufacturing_recipes_created_by", "created_by"),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    output_product_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)


class ManufacturingRecipeVersion(Base, AppendOnlyMixin):
    """Los parametros de la receta, versionados. Un cambio rige hacia adelante."""

    __tablename__ = "manufacturing_recipe_versions"

    __table_args__ = (
        sa.UniqueConstraint("corrects_id", name="uq_manufacturing_recipe_versions_corrects_id"),
        # Target de la FK compuesta desde batches: la version usada tiene que
        # pertenecer a la receta declarada.
        sa.UniqueConstraint("id", "recipe_id", name="uq_manufacturing_recipe_versions_id_recipe"),
        sa.CheckConstraint(
            "corrects_id IS DISTINCT FROM id",
            name="ck_manufacturing_recipe_versions_no_self_correction",
        ),
        sa.CheckConstraint(
            "base_input_qty > 0",
            name="ck_manufacturing_recipe_versions_base_input_qty_positive",
        ),
        sa.CheckConstraint(
            "default_input_qty > 0",
            name="ck_manufacturing_recipe_versions_default_input_qty_positive",
        ),
        sa.CheckConstraint(
            "corrects_id IS NULL OR reason IS NOT NULL",
            name="ck_manufacturing_recipe_versions_correction_needs_reason",
        ),
        sa.Index("ix_manufacturing_recipe_versions_recipe_id", "recipe_id"),
        sa.Index("ix_manufacturing_recipe_versions_corrects_id", "corrects_id"),
        sa.Index(
            "uq_manufacturing_recipe_versions_root_per_recipe",
            "recipe_id",
            unique=True,
            postgresql_where=sa.text("corrects_id IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    recipe_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("manufacturing_recipes.id", ondelete="RESTRICT"), nullable=False
    )
    # El insumo que se pesa. Puede cambiar entre versiones (pollo entero ->
    # pechuga) — por eso el rinde se calibra por (recipe_id, input_product_id) y
    # no por producto de salida: mezclar kg con unidades da un numero sin
    # significado.
    input_product_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    # El "por 1 kg" en el que esta expresada la receta.
    base_input_qty: Mapped[Decimal] = mapped_column(sa.Numeric, nullable=False)
    default_input_qty: Mapped[Decimal] = mapped_column(sa.Numeric, nullable=False)
    corrects_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("manufacturing_recipe_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


class ManufacturingRecipeItem(Base, AppendOnlyMixin):
    """Un extra que escala con el peso pesado.

    Cuelga de la IDENTIDAD, no de la version. Si colgara de la version, crear
    una v2 para cambiar `default_input_qty` la dejaria sin items y
    mostaza/sal/huevo/panko/harina/maicena dejarian de descontarse en silencio.

    Quinua y lentejas no tienen filas aca: no son un caso especial, son el caso
    general con cero extras.
    """

    __tablename__ = "manufacturing_recipe_items"

    __table_args__ = (
        sa.UniqueConstraint("corrects_id", name="uq_manufacturing_recipe_items_corrects_id"),
        sa.CheckConstraint(
            "corrects_id IS DISTINCT FROM id",
            name="ck_manufacturing_recipe_items_no_self_correction",
        ),
        sa.CheckConstraint("qty_per_base > 0", name="ck_manufacturing_recipe_items_qty_positive"),
        sa.CheckConstraint(
            "corrects_id IS NULL OR reason IS NOT NULL",
            name="ck_manufacturing_recipe_items_correction_needs_reason",
        ),
        sa.Index("ix_manufacturing_recipe_items_recipe_id", "recipe_id"),
        sa.Index("ix_manufacturing_recipe_items_product_id", "product_id"),
        sa.Index("ix_manufacturing_recipe_items_corrects_id", "corrects_id"),
        # El mismo insumo dos veces seria consumo duplicado silencioso.
        sa.Index(
            "uq_manufacturing_recipe_items_root_per_product",
            "recipe_id",
            "product_id",
            unique=True,
            postgresql_where=sa.text("corrects_id IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    recipe_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("manufacturing_recipes.id", ondelete="RESTRICT"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    # Cantidad por base_input_qty de la version vigente, en la unidad natural
    # del producto (products.unit). Se escala con regla de tres.
    qty_per_base: Mapped[Decimal] = mapped_column(sa.Numeric, nullable=False)
    rounding: Mapped[str] = mapped_column(_ROUNDING_ENUM, nullable=False, default="exact")
    position: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    corrects_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("manufacturing_recipe_items.id", ondelete="RESTRICT"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


class ManufacturingBatch(Base, TimestampMixin):
    """Una fabricacion ocurrida. Inmutable; se anula por ManufacturingBatchEvent.

    NO tiene `input_qty`. El peso que entro es UN hecho y vive en UN lugar: el
    insumo primario de ManufacturingBatchInput. Cuando estaba duplicado se podia
    reportar un rinde impecable (input_qty=1 -> 22/1) mientras el inventario
    descontaba otra cosa (qty=6). Esa era la coartada.

    Reglas que viven en triggers de 0017 (no expresables como CHECK):
      - exactamente un insumo primario vigente por batch (constraint trigger
        DEFERRABLE — si no, un batch sin inputs crea stock de la nada);
      - ese primario tiene que ser el `input_product_id` de la version usada;
      - `created_by = validated_by` y `validated_at` dentro de las ultimas 24 h
        y no en el futuro;
      - UPDATE y DELETE prohibidos.
    """

    __tablename__ = "manufacturing_batches"

    __table_args__ = (
        # La produccion se acredita al producto de la receta: no es un campo
        # libre, la FK compuesta lo hace imposible de falsear.
        sa.ForeignKeyConstraint(
            ["recipe_id", "output_product_id"],
            ["manufacturing_recipes.id", "manufacturing_recipes.output_product_id"],
            ondelete="RESTRICT",
            name="fk_manufacturing_batches_recipe_output",
        ),
        sa.ForeignKeyConstraint(
            ["recipe_version_id", "recipe_id"],
            ["manufacturing_recipe_versions.id", "manufacturing_recipe_versions.recipe_id"],
            ondelete="RESTRICT",
            name="fk_manufacturing_batches_version_recipe",
        ),
        sa.CheckConstraint("output_qty > 0", name="ck_manufacturing_batches_output_qty_positive"),
        sa.Index("ix_manufacturing_batches_output_product_id", "output_product_id"),
        sa.Index("ix_manufacturing_batches_recipe_id", "recipe_id"),
        sa.Index("ix_manufacturing_batches_validated_at", sa.text("validated_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    recipe_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    recipe_version_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    output_product_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    # LO CONTADO. Unico campo obligatorio de la pantalla.
    output_qty: Mapped[Decimal] = mapped_column(sa.Numeric, nullable=False)
    measurement: Mapped[str] = mapped_column(_MEASUREMENT_ENUM, nullable=False, default="measured")
    validated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    validated_by: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


class ManufacturingBatchInput(Base, AppendOnlyMixin):
    """Snapshot de lo que un batch consumio.

    Guarda cantidades, no un puntero a la receta — igual que DeliveryItem guarda
    cantidades y no referencias al catalogo. Si la receta cambia manana, los
    batches viejos no se mueven.

    Es la tabla que entra en _compute_stock_now restando consumo. La suma tiene
    que filtrar HOJAS (resolver la cadena de corrects_id) o cada correccion
    descuenta doble.
    """

    __tablename__ = "manufacturing_batch_inputs"

    __table_args__ = (
        sa.UniqueConstraint("corrects_id", name="uq_manufacturing_batch_inputs_corrects_id"),
        sa.CheckConstraint(
            "corrects_id IS DISTINCT FROM id",
            name="ck_manufacturing_batch_inputs_no_self_correction",
        ),
        sa.CheckConstraint("qty > 0", name="ck_manufacturing_batch_inputs_qty_positive"),
        sa.CheckConstraint(
            "corrects_id IS NULL OR reason IS NOT NULL",
            name="ck_manufacturing_batch_inputs_correction_needs_reason",
        ),
        sa.Index("ix_manufacturing_batch_inputs_batch_id", "batch_id"),
        sa.Index("ix_manufacturing_batch_inputs_product_id", "product_id"),
        sa.Index("ix_manufacturing_batch_inputs_corrects_id", "corrects_id"),
        # El mismo insumo dos veces en un batch descuenta doble del stock.
        sa.Index(
            "uq_manufacturing_batch_inputs_root_per_product",
            "batch_id",
            "product_id",
            unique=True,
            postgresql_where=sa.text("corrects_id IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("manufacturing_batches.id", ondelete="RESTRICT"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    qty: Mapped[Decimal] = mapped_column(sa.Numeric, nullable=False)
    # true = el insumo pesado; false = extra escalado por receta.
    is_primary: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    corrects_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("manufacturing_batch_inputs.id", ondelete="RESTRICT"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


class ManufacturingBatchEvent(Base, AppendOnlyMixin):
    """Anulacion de un batch. Espeja PurchaseOrderStatusEvent.

    Un batch cargado por error ("220 bolsitas" con un cero de mas) infla el
    stock Y corre el umbral de deteccion del producto para siempre, porque el
    umbral sale de la varianza del rinde. Sin anulacion, un error es un error
    congelado — y eso es lo contrario de trazabilidad.

    El cocinero registra fabricaciones; anular es del dueno/admin (trigger de
    rol en 0017). El motivo es obligatorio y no puede ser vacio.
    """

    __tablename__ = "manufacturing_batch_events"

    __table_args__ = (
        sa.CheckConstraint(
            "length(btrim(reason)) > 0",
            name="ck_manufacturing_batch_events_reason_not_blank",
        ),
        # Un batch se anula una sola vez.
        sa.UniqueConstraint(
            "batch_id", "event_type", name="uq_manufacturing_batch_events_batch_type"
        ),
        sa.Index("ix_manufacturing_batch_events_batch_id", "batch_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("manufacturing_batches.id", ondelete="RESTRICT"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(_BATCH_EVENT_ENUM, nullable=False)
    reason: Mapped[str] = mapped_column(sa.Text, nullable=False)
