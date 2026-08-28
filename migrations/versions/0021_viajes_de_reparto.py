"""viajes de reparto: un viaje de inDrive lleva uno o varios pedidos

El reparto no lo hace Bonabowl: se pide un inDrive y el motorizado lleva la
comida. Rara vez, pero pasa, un mismo viaje lleva mas de un pedido — por eso la
relacion es viaje 1 : N pedidos y no una columna suelta en sales_orders.

QUE NO SE GUARDA, Y POR QUE
---------------------------
No hay costo por pedido. El cliente paga la tarifa que se le cotizo
(sales_orders.delivery_fee, la tabla de delivery_zones); lo que cuesta el
inDrive lo paga Bonabowl. Repartir el costo del viaje entre los pedidos seria
inventar un dato que nadie cobra ni usa.

Lo que si queda medible, y hoy no existe: la diferencia entre lo COBRADO (suma
de delivery_fee de los pedidos del viaje) y lo PAGADO (trip_cost). Ese es el
margen del reparto, y hasta ahora nadie lo veia.

SE LLAMA delivery_trips Y NO deliveries
----------------------------------------
`deliveries` ya existe en esta base con 54 filas y significa otra cosa: el
registro de cocina con foto de lo que se despacho. Es la misma coleccion de
nombres que obligo a llamar sales_orders a los pedidos para no chocar con
delivery_orders. Dos tablas que suenan igual y guardan cosas distintas es como
nacen los bugs que nadie encuentra.

EL LINK ES LA CREDENCIAL
------------------------
Un link de sharetrip.indrive.com se lee como JSON sin token ni cookie
insertando /proxy/share/api/v2/share antes del path. De ahi salen el costo y el
estado real del viaje. Por eso `tracking_url` es UNICO: dos filas con el mismo
link serian el mismo viaje contado dos veces, y el margen saldria mal.

Ojo con el estado: el ETA en minutos que devuelve inDrive SE CONGELA y no sirve
para saber si llego. La senal buena es `status`, con vocabulario observado
on_delivery -> reached_destination_point -> done. Por eso la columna guarda
texto libre y no un enum: es vocabulario de un tercero que no controlamos y que
puede sumar valores sin avisarnos.

Revision ID: 0021_viajes_reparto
Revises: 0020_rol_asistente
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_viajes_reparto"
down_revision: str | None = "0020_rol_asistente"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "delivery_trips",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tracking_url", sa.Text(), nullable=False),
        sa.Column(
            "provider",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'indrive'"),
        ),
        # Lo que costo el viaje, que lo paga Bonabowl. NULL mientras no se haya
        # podido leer del link: es preferible el pedido despachado sin costo
        # conocido a bloquear el despacho por un dato que se puede completar.
        sa.Column("trip_cost", sa.Numeric(10, 2), nullable=True),
        # Texto libre a proposito: es vocabulario de inDrive, no nuestro.
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("status_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "trip_cost IS NULL OR trip_cost >= 0",
            name="ck_delivery_trips_cost_not_negative",
        ),
        # Un link mal escrito no es un viaje. Se exige que sea de sharetrip:
        # es lo unico que sabemos leer, y aceptar cualquier texto convertiria
        # la columna en un cajon de notas.
        sa.CheckConstraint(
            "tracking_url ~ '^https://sharetrip\\.indrive\\.com/'",
            name="ck_delivery_trips_url_es_sharetrip",
        ),
    )
    # El mismo link contado dos veces seria el mismo viaje duplicado, y el
    # margen del reparto saldria mal sin que nada lo delate.
    op.create_index(
        "ix_delivery_trips_url_unique", "delivery_trips", ["tracking_url"], unique=True
    )
    op.create_index("ix_delivery_trips_created_at", "delivery_trips", ["created_at"])

    op.add_column(
        "sales_orders",
        sa.Column("delivery_trip_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "sales_orders_delivery_trip_id_fkey",
        "sales_orders",
        "delivery_trips",
        ["delivery_trip_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_sales_orders_delivery_trip_id", "sales_orders", ["delivery_trip_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_sales_orders_delivery_trip_id", table_name="sales_orders")
    op.drop_constraint(
        "sales_orders_delivery_trip_id_fkey", "sales_orders", type_="foreignkey"
    )
    op.drop_column("sales_orders", "delivery_trip_id")
    op.drop_table("delivery_trips")
