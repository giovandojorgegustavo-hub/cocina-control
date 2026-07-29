"""fabricacion de preparados

Revierte la decision del 13 jul 2026 ("sin fabricacion", requerimientos.md:26).
Diseno completo en docs/backend/diseno-fabricacion.md.

Crea el circuito de fabricacion de preparados: recetas versionadas que define el
dueno, y batches que registra el cocinero. El modelo es pesar lo que entra,
mostrar los extras escalados a ese peso, y contar lo que sale. Con eso el factor
de rinde deja de ser un estimado declarado y pasa a ser medido.

ESTE ES UN LEDGER DE AUDITORIA. El operario que registra una fabricacion es
exactamente la persona a la que despues se le audita el faltante. Cada constraint
de abajo existe porque sin ella hay una forma de inflar el stock teorico y
fabricar la coartada del propio faltante. La base es la ultima linea de defensa
cuando el codigo de aplicacion falla.

Seis tablas:

  manufacturing_recipes          IDENTIDAD del preparado — una fila para siempre
  manufacturing_recipe_versions  los parametros versionados (append-only)
  manufacturing_recipe_items     los extras — cuelgan de la IDENTIDAD, no de la
                                 version, para que versionar no los borre
  manufacturing_batches          el hecho ocurrido — inmutable
  manufacturing_batch_inputs     snapshot de lo consumido (append-only)
  manufacturing_batch_events     anulacion de un batch (append-only, owner/admin)

Por que los items cuelgan de la IDENTIDAD y no de la version: si colgaran de la
version, crear una v2 para cambiar `default_input_qty` dejaria a la v2 sin items,
y mostaza/sal/huevo/panko/harina/maicena dejarian de descontarse en silencio.
Seis productos con sobrante teorico creciente — que es la forma exacta que tiene
una fuga real de quedar enmascarada. Los items se versionan individualmente por
su propio corrects_id.

products.is_manufactured amplia ck_products_purchase_or_sale: un preparado puede
no comprarse ni venderse (quinua cocida) y aun asi existir y contarse.

NOTA: el numero 0017 tambien lo reclamaba docs/backend/diseno-modificadores-pedido.md
("0017_product_option_groups"), sin implementar. Esta aterrizo primero; la de
modificadores pasa a 0018 con down_revision = "0017_fabricacion".

Revision ID: 0017_fabricacion
Revises: 0016_po_item_removed
Create Date: 2026-07-28
"""

import os
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_fabricacion"
down_revision: str | None = "0016_po_item_removed"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Crea las 6 tablas de fabricacion, la flag en products y los guards."""

    # ------------------------------------------------------------------
    # 0. products.is_manufactured
    # ------------------------------------------------------------------
    op.add_column(
        "products",
        sa.Column(
            "is_manufactured",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.drop_constraint("ck_products_purchase_or_sale", "products", type_="check")
    op.create_check_constraint(
        "ck_products_purchase_sale_or_manufactured",
        "products",
        "is_purchase OR is_sale OR is_manufactured",
    )

    # ------------------------------------------------------------------
    # 1. manufacturing_recipes — IDENTIDAD
    # ------------------------------------------------------------------
    # Una fila por preparado, para siempre. output_product_id es UNIQUE y no se
    # versiona: sin esto, una cadena de corrects_id podia secuestrar la receta
    # hacia otro producto y dejar dos recetas vigentes para el mismo preparado.
    op.create_table(
        "manufacturing_recipes",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "output_product_id",
            sa.Uuid(),
            sa.ForeignKey(
                "products.id",
                ondelete="RESTRICT",
                name="fk_manufacturing_recipes_output_product_id",
            ),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey(
                "users.id", ondelete="RESTRICT", name="fk_manufacturing_recipes_created_by"
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("output_product_id", name="uq_manufacturing_recipes_output_product_id"),
        # Target de la FK compuesta desde batches: hace IMPOSIBLE que un batch
        # acredite produccion a un producto distinto del de su receta.
        sa.UniqueConstraint("id", "output_product_id", name="uq_manufacturing_recipes_id_output"),
    )
    op.create_index("ix_manufacturing_recipes_created_by", "manufacturing_recipes", ["created_by"])

    # ------------------------------------------------------------------
    # 2. manufacturing_recipe_versions — los parametros versionados
    # ------------------------------------------------------------------
    op.create_table(
        "manufacturing_recipe_versions",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "recipe_id",
            sa.Uuid(),
            sa.ForeignKey(
                "manufacturing_recipes.id",
                ondelete="RESTRICT",
                name="fk_manufacturing_recipe_versions_recipe_id",
            ),
            nullable=False,
        ),
        # El insumo que se pesa. Vive en la version porque puede cambiar
        # (pollo entero -> pechuga), pero entonces el rinde NO es comparable
        # entre versiones: se calibra por (recipe_id, input_product_id).
        sa.Column(
            "input_product_id",
            sa.Uuid(),
            sa.ForeignKey(
                "products.id",
                ondelete="RESTRICT",
                name="fk_manufacturing_recipe_versions_input_product_id",
            ),
            nullable=False,
        ),
        # El "por 1 kg" en el que esta expresada la receta.
        sa.Column("base_input_qty", sa.Numeric(), nullable=False),
        # Lo que la pantalla precarga. Ver measurement en batches: aceptar este
        # default sin pesar marca el batch y lo saca de la calibracion.
        sa.Column("default_input_qty", sa.Numeric(), nullable=False),
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey(
                "users.id",
                ondelete="RESTRICT",
                name="fk_manufacturing_recipe_versions_created_by",
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "corrects_id",
            sa.Uuid(),
            sa.ForeignKey(
                "manufacturing_recipe_versions.id",
                ondelete="RESTRICT",
                name="fk_manufacturing_recipe_versions_corrects_id",
            ),
            nullable=True,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
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
        # requerimientos.md:244 — toda correccion lleva motivo.
        sa.CheckConstraint(
            "corrects_id IS NULL OR reason IS NOT NULL",
            name="ck_manufacturing_recipe_versions_correction_needs_reason",
        ),
    )
    op.create_index(
        "ix_manufacturing_recipe_versions_recipe_id",
        "manufacturing_recipe_versions",
        ["recipe_id"],
    )
    op.create_index(
        "ix_manufacturing_recipe_versions_corrects_id",
        "manufacturing_recipe_versions",
        ["corrects_id"],
    )
    # Una sola version RAIZ por receta; las siguientes cuelgan por corrects_id.
    op.create_index(
        "uq_manufacturing_recipe_versions_root_per_recipe",
        "manufacturing_recipe_versions",
        ["recipe_id"],
        unique=True,
        postgresql_where=sa.text("corrects_id IS NULL"),
    )

    # ------------------------------------------------------------------
    # 3. manufacturing_recipe_items — cuelgan de la IDENTIDAD
    # ------------------------------------------------------------------
    # Los extras que escalan con el peso: apio/cebolla/sal del deshilachado,
    # mostaza/panko/huevo de la milanesa. Quinua y lentejas no tienen filas aca
    # — no son un caso especial, son el caso general con cero extras.
    rounding_enum = sa.Enum("exact", "integer", name="manufacturing_rounding", create_type=True)
    op.create_table(
        "manufacturing_recipe_items",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "recipe_id",
            sa.Uuid(),
            sa.ForeignKey(
                "manufacturing_recipes.id",
                ondelete="RESTRICT",
                name="fk_manufacturing_recipe_items_recipe_id",
            ),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.Uuid(),
            sa.ForeignKey(
                "products.id",
                ondelete="RESTRICT",
                name="fk_manufacturing_recipe_items_product_id",
            ),
            nullable=False,
        ),
        # Cantidad por base_input_qty de la version vigente. Se escala con regla
        # de tres. Expresada en la unidad natural del producto (products.unit).
        sa.Column("qty_per_base", sa.Numeric(), nullable=False),
        # 'integer' = el huevo. Se redondea Y se guarda el entero: guardar 4,96
        # cuando se pusieron 5 desfasaria el teorico en cada batch.
        sa.Column("rounding", rounding_enum, nullable=False, server_default=sa.text("'exact'")),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey(
                "users.id",
                ondelete="RESTRICT",
                name="fk_manufacturing_recipe_items_created_by",
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "corrects_id",
            sa.Uuid(),
            sa.ForeignKey(
                "manufacturing_recipe_items.id",
                ondelete="RESTRICT",
                name="fk_manufacturing_recipe_items_corrects_id",
            ),
            nullable=True,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
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
    )
    op.create_index(
        "ix_manufacturing_recipe_items_recipe_id",
        "manufacturing_recipe_items",
        ["recipe_id"],
    )
    op.create_index(
        "ix_manufacturing_recipe_items_product_id",
        "manufacturing_recipe_items",
        ["product_id"],
    )
    op.create_index(
        "ix_manufacturing_recipe_items_corrects_id",
        "manufacturing_recipe_items",
        ["corrects_id"],
    )
    # Un mismo insumo no puede aparecer dos veces como raiz en la misma receta:
    # seria consumo duplicado silencioso.
    op.create_index(
        "uq_manufacturing_recipe_items_root_per_product",
        "manufacturing_recipe_items",
        ["recipe_id", "product_id"],
        unique=True,
        postgresql_where=sa.text("corrects_id IS NULL"),
    )

    # ------------------------------------------------------------------
    # 4. manufacturing_batches — el hecho ocurrido
    # ------------------------------------------------------------------
    # INMUTABLE (sin corrects_id). Se anula por manufacturing_batch_events.
    #
    # NO tiene input_qty: el peso que entro es UN hecho y vive en UN lugar, el
    # insumo primario de manufacturing_batch_inputs. Cuando estaba duplicado se
    # podia reportar un rinde impecable (input_qty=1 -> 22/1) mientras el
    # inventario descontaba otra cosa (qty=6). Esa era la coartada.
    measurement_enum = sa.Enum(
        "measured",
        "default_input",
        "default_output",
        "both_defaults",
        name="manufacturing_measurement",
        create_type=True,
    )
    op.create_table(
        "manufacturing_batches",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("recipe_id", sa.Uuid(), nullable=False),
        sa.Column("recipe_version_id", sa.Uuid(), nullable=False),
        sa.Column("output_product_id", sa.Uuid(), nullable=False),
        # LO CONTADO. Unico campo obligatorio de la pantalla.
        sa.Column("output_qty", sa.Numeric(), nullable=False),
        # Que se midio de verdad. Solo 'measured' calibra el rinde: un default
        # aceptado a ciegas es una expectativa, no una medicion, y medir contra
        # la expectativa destruye la medicion. Aplica a los DOS lados — la
        # entrada tambien, porque pesar tiene mas friccion que contar bolsitas.
        sa.Column(
            "measurement", measurement_enum, nullable=False, server_default=sa.text("'measured'")
        ),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "validated_by",
            sa.Uuid(),
            sa.ForeignKey(
                "users.id", ondelete="RESTRICT", name="fk_manufacturing_batches_validated_by"
            ),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey(
                "users.id", ondelete="RESTRICT", name="fk_manufacturing_batches_created_by"
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # La produccion se acredita al producto de la receta. No es un campo
        # libre: la FK compuesta lo hace imposible de falsear.
        sa.ForeignKeyConstraint(
            ["recipe_id", "output_product_id"],
            ["manufacturing_recipes.id", "manufacturing_recipes.output_product_id"],
            ondelete="RESTRICT",
            name="fk_manufacturing_batches_recipe_output",
        ),
        # La version usada tiene que pertenecer a la receta declarada.
        sa.ForeignKeyConstraint(
            ["recipe_version_id", "recipe_id"],
            [
                "manufacturing_recipe_versions.id",
                "manufacturing_recipe_versions.recipe_id",
            ],
            ondelete="RESTRICT",
            name="fk_manufacturing_batches_version_recipe",
        ),
        sa.CheckConstraint("output_qty > 0", name="ck_manufacturing_batches_output_qty_positive"),
    )
    op.create_index(
        "ix_manufacturing_batches_output_product_id",
        "manufacturing_batches",
        ["output_product_id"],
    )
    op.create_index("ix_manufacturing_batches_recipe_id", "manufacturing_batches", ["recipe_id"])
    op.create_index(
        "ix_manufacturing_batches_validated_at",
        "manufacturing_batches",
        [sa.text("validated_at DESC")],
    )

    # ------------------------------------------------------------------
    # 5. manufacturing_batch_inputs — snapshot de lo consumido
    # ------------------------------------------------------------------
    op.create_table(
        "manufacturing_batch_inputs",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "batch_id",
            sa.Uuid(),
            sa.ForeignKey(
                "manufacturing_batches.id",
                ondelete="RESTRICT",
                name="fk_manufacturing_batch_inputs_batch_id",
            ),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.Uuid(),
            sa.ForeignKey(
                "products.id",
                ondelete="RESTRICT",
                name="fk_manufacturing_batch_inputs_product_id",
            ),
            nullable=False,
        ),
        sa.Column("qty", sa.Numeric(), nullable=False),
        # true = el insumo pesado; false = extra escalado por receta.
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey(
                "users.id",
                ondelete="RESTRICT",
                name="fk_manufacturing_batch_inputs_created_by",
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "corrects_id",
            sa.Uuid(),
            sa.ForeignKey(
                "manufacturing_batch_inputs.id",
                ondelete="RESTRICT",
                name="fk_manufacturing_batch_inputs_corrects_id",
            ),
            nullable=True,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
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
    )
    op.create_index(
        "ix_manufacturing_batch_inputs_batch_id", "manufacturing_batch_inputs", ["batch_id"]
    )
    op.create_index(
        "ix_manufacturing_batch_inputs_product_id", "manufacturing_batch_inputs", ["product_id"]
    )
    op.create_index(
        "ix_manufacturing_batch_inputs_corrects_id",
        "manufacturing_batch_inputs",
        ["corrects_id"],
    )
    # El mismo insumo dos veces en un batch descuenta doble del stock.
    op.create_index(
        "uq_manufacturing_batch_inputs_root_per_product",
        "manufacturing_batch_inputs",
        ["batch_id", "product_id"],
        unique=True,
        postgresql_where=sa.text("corrects_id IS NULL"),
    )

    # ------------------------------------------------------------------
    # 6. manufacturing_batch_events — anulacion
    # ------------------------------------------------------------------
    # Un batch es inmutable, pero un batch cargado por error tiene que poder
    # anularse: sin esto, un "220 bolsitas" tipeado con un cero de mas infla el
    # stock Y corre el umbral de deteccion del producto para siempre, porque el
    # umbral sale de la varianza del rinde (requerimientos.md).
    #
    # Espeja purchase_order_status_events: evento inmutable, motivo obligatorio,
    # guard de rol owner/admin. El cocinero registra; anular es del dueno.
    batch_event_enum = sa.Enum("annulled", name="manufacturing_batch_event_type", create_type=True)
    op.create_table(
        "manufacturing_batch_events",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "batch_id",
            sa.Uuid(),
            sa.ForeignKey(
                "manufacturing_batches.id",
                ondelete="RESTRICT",
                name="fk_manufacturing_batch_events_batch_id",
            ),
            nullable=False,
        ),
        sa.Column("event_type", batch_event_enum, nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey(
                "users.id",
                ondelete="RESTRICT",
                name="fk_manufacturing_batch_events_created_by",
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(btrim(reason)) > 0",
            name="ck_manufacturing_batch_events_reason_not_blank",
        ),
        # Un batch se anula una sola vez.
        sa.UniqueConstraint(
            "batch_id", "event_type", name="uq_manufacturing_batch_events_batch_type"
        ),
    )
    op.create_index(
        "ix_manufacturing_batch_events_batch_id", "manufacturing_batch_events", ["batch_id"]
    )

    # ------------------------------------------------------------------
    # 7. Guards de rol: las RECETAS son del dueno/admin
    # ------------------------------------------------------------------
    # Los BATCHES no llevan guard de rol: los registra el cocinero, que es el
    # punto de toda la feature. Anular un batch SI es owner/admin.
    for table in (
        "manufacturing_recipes",
        "manufacturing_recipe_versions",
        "manufacturing_recipe_items",
        "manufacturing_batch_events",
    ):
        op.execute(
            f"""
CREATE TRIGGER trg_{table}_admin_or_owner_creator
BEFORE INSERT ON {table}
FOR EACH ROW EXECUTE FUNCTION cocina_require_admin_or_owner_creator();
"""
        )

    # ------------------------------------------------------------------
    # 8. Append-only de verdad: prohibir UPDATE y DELETE
    # ------------------------------------------------------------------
    # El repo llamaba "append-only" a tablas que a nivel base aceptaban UPDATE y
    # DELETE fisico. Aca la inmutabilidad se declara como propiedad del diseno,
    # asi que se enforcea. Sin esto, un UPDATE reescribe la receta Y su autoria.
    op.execute(
        """
CREATE OR REPLACE FUNCTION cocina_forbid_update_delete() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'tabla append-only: % prohibido en %', TG_OP, TG_TABLE_NAME
        USING ERRCODE = 'check_violation';
END;
$$ LANGUAGE plpgsql;
"""
    )
    for table in (
        "manufacturing_recipes",
        "manufacturing_recipe_versions",
        "manufacturing_recipe_items",
        "manufacturing_batches",
        "manufacturing_batch_inputs",
        "manufacturing_batch_events",
    ):
        op.execute(
            f"""
CREATE TRIGGER trg_{table}_forbid_update_delete
BEFORE UPDATE OR DELETE ON {table}
FOR EACH ROW EXECUTE FUNCTION cocina_forbid_update_delete();
"""
        )

    # ------------------------------------------------------------------
    # 9. Integridad del batch: exactamente un insumo primario vigente,
    #    y que sea el insumo que la receta declara
    # ------------------------------------------------------------------
    # DEFERRABLE INITIALLY DEFERRED: el batch y sus inputs se insertan en la
    # misma transaccion, asi que la verificacion corre al commit.
    #
    # Sin esto: (a) un batch sin inputs crea stock de la nada; (b) corrigiendo
    # un extra con is_primary=true quedan dos primarios y el peso de referencia
    # deja de ser unico; (c) el primario podia ser lomo fino en una receta de
    # quinua — descontar el producto caro y reportar el rinde del barato.
    op.execute(
        """
CREATE OR REPLACE FUNCTION cocina_check_batch_integrity() RETURNS TRIGGER AS $$
DECLARE
    v_batch_id   uuid;
    v_count      integer;
    v_primary    uuid;
    v_expected   uuid;
BEGIN
    IF TG_TABLE_NAME = 'manufacturing_batches' THEN
        v_batch_id := NEW.id;
    ELSE
        v_batch_id := NEW.batch_id;
    END IF;

    SELECT count(*) INTO v_count
      FROM manufacturing_batch_inputs bi
     WHERE bi.batch_id = v_batch_id
       AND bi.is_primary
       AND NOT EXISTS (
             SELECT 1 FROM manufacturing_batch_inputs c WHERE c.corrects_id = bi.id
           );

    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'el batch % debe tener exactamente un insumo primario vigente (tiene %)',
            v_batch_id, v_count
            USING ERRCODE = 'check_violation';
    END IF;

    SELECT bi.product_id INTO v_primary
      FROM manufacturing_batch_inputs bi
     WHERE bi.batch_id = v_batch_id
       AND bi.is_primary
       AND NOT EXISTS (
             SELECT 1 FROM manufacturing_batch_inputs c WHERE c.corrects_id = bi.id
           );

    SELECT v.input_product_id INTO v_expected
      FROM manufacturing_batches b
      JOIN manufacturing_recipe_versions v ON v.id = b.recipe_version_id
     WHERE b.id = v_batch_id;

    IF v_primary IS DISTINCT FROM v_expected THEN
        RAISE EXCEPTION
            'el insumo primario del batch % (%) no es el que declara la receta (%)',
            v_batch_id, v_primary, v_expected
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""
    )
    op.execute(
        """
CREATE CONSTRAINT TRIGGER trg_manufacturing_batches_integrity
AFTER INSERT ON manufacturing_batches
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION cocina_check_batch_integrity();
"""
    )
    op.execute(
        """
CREATE CONSTRAINT TRIGGER trg_manufacturing_batch_inputs_integrity
AFTER INSERT ON manufacturing_batch_inputs
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION cocina_check_batch_integrity();
"""
    )

    # ------------------------------------------------------------------
    # 10. Autoria y fecha del batch
    # ------------------------------------------------------------------
    # La bandeja muestra "fabrico {validated_by_name}": esa firma no puede ser
    # un campo libre de quien registra. Y un validated_at retroactivo cambia el
    # teorico de un periodo que el dueno ya concilio y cerro.
    op.execute(
        """
CREATE OR REPLACE FUNCTION cocina_check_batch_authorship() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.created_by <> NEW.validated_by THEN
        RAISE EXCEPTION 'created_by y validated_by deben ser el mismo usuario'
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.validated_at > now() + interval '1 minute' THEN
        RAISE EXCEPTION 'validated_at no puede estar en el futuro'
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.validated_at < now() - interval '24 hours' THEN
        RAISE EXCEPTION 'validated_at no puede tener mas de 24 horas de antiguedad'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""
    )
    op.execute(
        """
CREATE TRIGGER trg_manufacturing_batches_authorship
BEFORE INSERT ON manufacturing_batches
FOR EACH ROW EXECUTE FUNCTION cocina_check_batch_authorship();
"""
    )


def downgrade() -> None:
    """Revierte la fabricacion.

    Raises RuntimeError in production to prevent accidental data loss.
    """
    app_env = os.environ.get("COCINA_APP_ENV", "dev")
    if app_env == "prod":
        raise RuntimeError(
            "Downgrade prohibited in production — restore from PostgreSQL backup instead"
        )

    bind = op.get_bind()

    # El CHECK viejo (is_purchase OR is_sale) no admite preparados puros — la
    # quinua cocida es exactamente eso. Sin este chequeo el downgrade explota
    # con un CheckViolation de Postgres que no dice que hacer.
    orphans = bind.execute(
        sa.text(
            "SELECT count(*) FROM products "
            "WHERE is_manufactured AND NOT is_purchase AND NOT is_sale"
        )
    ).scalar_one()
    if orphans:
        raise RuntimeError(
            f"Downgrade bloqueado: hay {orphans} producto(s) que solo existen como "
            "preparado (is_manufactured sin is_purchase ni is_sale). El CHECK previo a "
            "0017 no los admite. Resolvelos antes: marcalos is_purchase/is_sale, o "
            "desactivalos y borralos si no tienen movimientos."
        )

    # Triggers antes que las tablas. Las funciones COMPARTIDAS no se dropean:
    # cocina_require_admin_or_owner_creator() la usan las tablas de
    # purchase_orders desde 0013.
    for table in (
        "manufacturing_recipes",
        "manufacturing_recipe_versions",
        "manufacturing_recipe_items",
        "manufacturing_batches",
        "manufacturing_batch_inputs",
        "manufacturing_batch_events",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_forbid_update_delete ON {table};")
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_admin_or_owner_creator ON {table};")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_manufacturing_batches_authorship ON manufacturing_batches;"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_manufacturing_batches_integrity ON manufacturing_batches;"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_manufacturing_batch_inputs_integrity "
        "ON manufacturing_batch_inputs;"
    )
    op.execute("DROP FUNCTION IF EXISTS cocina_check_batch_authorship();")
    op.execute("DROP FUNCTION IF EXISTS cocina_check_batch_integrity();")
    op.execute("DROP FUNCTION IF EXISTS cocina_forbid_update_delete();")

    # Orden inverso al upgrade.
    op.drop_table("manufacturing_batch_events")
    op.drop_table("manufacturing_batch_inputs")
    op.drop_table("manufacturing_batches")
    op.drop_table("manufacturing_recipe_items")
    op.drop_table("manufacturing_recipe_versions")
    op.drop_table("manufacturing_recipes")

    sa.Enum(name="manufacturing_batch_event_type").drop(bind, checkfirst=True)
    sa.Enum(name="manufacturing_measurement").drop(bind, checkfirst=True)
    sa.Enum(name="manufacturing_rounding").drop(bind, checkfirst=True)

    op.drop_constraint("ck_products_purchase_sale_or_manufactured", "products", type_="check")
    op.create_check_constraint(
        "ck_products_purchase_or_sale",
        "products",
        "is_purchase OR is_sale",
    )
    op.drop_column("products", "is_manufactured")
