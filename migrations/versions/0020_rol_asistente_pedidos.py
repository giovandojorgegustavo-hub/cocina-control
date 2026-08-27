"""rol asistente_pedidos: el bot toma pedidos sin llegar al dinero

deps.py cierra ACT_AS_ALLOWED_ROLES en {"cocinero"} a proposito, y su comentario
dice por que: un service token filtrado no debe alcanzar el lado del dinero, y
ensanchar ese conjunto es un cambio de codigo revisado, no una edicion de base a
las 2 de la manana. Este es ese cambio revisado.

El asistente de WhatsApp necesita escribir pedidos con importes, que es
exactamente lo que cocinero no puede hacer. Habia dos salidas y una es mala:

- Dejar al asistente como cocinero y permitirle crear pedidos. Eso ensancha
  cocinero, o sea que TODOS los cocineros humanos ganan acceso a los importes de
  venta de golpe. El permiso se le da al que menos hace falta.
- Un rol propio, con exactamente lo que el asistente necesita y nada mas.

Va el segundo. asistente_pedidos puede registrar cliente, direccion, pedido,
lineas y un pago en estado pending. No puede verificar un pago, no puede ver
costos y no puede tocar inventario ni compras. La imposibilidad de verificar no
depende de este rol: la sostiene ck_payments_verified_needs_human en la base.

Postgres no soporta ALTER TYPE ... DROP VALUE, asi que el downgrade recrea el
tipo. Cualquier usuario que haya quedado con el rol nuevo se degrada a cocinero
antes, igual que hizo 0013 con admin.

Revision ID: 0020_rol_asistente
Revises: 0019_pedidos_venta
Create Date: 2026-08-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0020_rol_asistente"
down_revision: str | None = "0019_pedidos_venta"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # Postgres 12+ acepta ADD VALUE dentro de una transaccion; lo que no permite
    # es USAR el valor nuevo en esa misma transaccion. Esta migracion solo lo
    # agrega, asi que no hay problema.
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'asistente_pedidos'")


def downgrade() -> None:
    # Nadie puede quedar con un rol que esta por dejar de existir.
    op.execute("UPDATE users SET role = 'cocinero' WHERE role = 'asistente_pedidos'")

    op.execute("CREATE TYPE user_role_v19 AS ENUM ('cocinero', 'owner', 'admin')")
    op.execute(
        """
        ALTER TABLE users
        ALTER COLUMN role TYPE user_role_v19
        USING role::text::user_role_v19
        """
    )
    op.execute("DROP TYPE user_role")
    op.execute("ALTER TYPE user_role_v19 RENAME TO user_role")
