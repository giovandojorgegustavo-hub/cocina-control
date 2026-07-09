"""initial_schema

Revision ID: 85ec14b1dea9
Revises:
Create Date: 2026-07-09 11:26:01.732742

"""
import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '85ec14b1dea9'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('users',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('email', sa.Text(), nullable=False),
    sa.Column('password_hash', sa.Text(), nullable=False),
    sa.Column('role', sa.Enum('operator', 'owner', name='user_role'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    # Case-insensitive unique index on email — enforces uniqueness regardless of case.
    # The application layer normalizes email to lowercase before persisting.
    op.create_index(
        'ix_users_email_lower',
        'users',
        [sa.text('lower(email)')],
        unique=True,
    )
    op.create_table('deliveries',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('supplier_name', sa.Text(), nullable=False),
    sa.Column('status', sa.Enum('no_leida', 'en_verificacion', 'validada', name='delivery_status'), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('validated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('validated_by', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['validated_by'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_deliveries_status', 'deliveries', ['status'], unique=False)
    op.create_table('delivery_orders',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('status', sa.Enum('pending', 'completed', name='delivery_order_status'), nullable=False),
    sa.Column('photo_url', sa.Text(), nullable=True),
    sa.Column('photo_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('photo_by', sa.Uuid(), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_by', sa.Uuid(), nullable=True),
    sa.Column('platform', sa.Text(), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('corrects_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('corrects_id IS DISTINCT FROM id', name='ck_delivery_orders_no_self_correction'),
    sa.CheckConstraint('(photo_at IS NULL) = (photo_by IS NULL)', name='ck_delivery_orders_photo_parity'),
    sa.CheckConstraint('(completed_at IS NULL) = (completed_by IS NULL)', name='ck_delivery_orders_completed_parity'),
    sa.ForeignKeyConstraint(['completed_by'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['corrects_id'], ['delivery_orders.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['photo_by'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_delivery_orders_status', 'delivery_orders', ['status'], unique=False)
    op.create_index('ix_delivery_orders_corrects_id', 'delivery_orders', ['corrects_id'], unique=False)
    op.create_table('inventory_counts',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('status', sa.Enum('in_progress', 'completed', name='inventory_count_status'), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('started_by', sa.Uuid(), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_by', sa.Uuid(), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['completed_by'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['started_by'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_inventory_counts_status', 'inventory_counts', ['status'], unique=False)
    op.create_table('products',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('unit', sa.Enum('kg', 'un', 'lt', name='product_unit'), nullable=False),
    sa.Column('low_stock_threshold', sa.Numeric(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint(
        'low_stock_threshold IS NULL OR low_stock_threshold > 0',
        name='ck_products_low_stock_threshold_positive',
    ),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_products_name_active', 'products', ['name'], unique=False, postgresql_where=sa.text('is_active = true'))
    op.create_table('delivery_items',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('delivery_id', sa.Uuid(), nullable=False),
    sa.Column('product_id', sa.Uuid(), nullable=False),
    sa.Column('announced_qty', sa.Numeric(), nullable=False),
    sa.Column('received_qty', sa.Numeric(), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('corrects_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('corrects_id IS DISTINCT FROM id', name='ck_delivery_items_no_self_correction'),
    sa.CheckConstraint('announced_qty > 0', name='ck_delivery_items_announced_qty_positive'),
    sa.CheckConstraint('received_qty IS NULL OR received_qty >= 0', name='ck_delivery_items_received_qty_nonneg'),
    sa.ForeignKeyConstraint(['corrects_id'], ['delivery_items.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['delivery_id'], ['deliveries.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_delivery_items_delivery_id', 'delivery_items', ['delivery_id'], unique=False)
    op.create_index('ix_delivery_items_product_id', 'delivery_items', ['product_id'], unique=False)
    op.create_index('ix_delivery_items_corrects_id', 'delivery_items', ['corrects_id'], unique=False)
    op.create_table('delivery_order_items',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('delivery_order_id', sa.Uuid(), nullable=False),
    sa.Column('product_id', sa.Uuid(), nullable=False),
    sa.Column('quantity', sa.Numeric(), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('corrects_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('corrects_id IS DISTINCT FROM id', name='ck_delivery_order_items_no_self_correction'),
    sa.CheckConstraint('quantity > 0', name='ck_delivery_order_items_quantity_positive'),
    sa.ForeignKeyConstraint(['corrects_id'], ['delivery_order_items.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['delivery_order_id'], ['delivery_orders.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_delivery_order_items_order_id', 'delivery_order_items', ['delivery_order_id'], unique=False)
    op.create_index('ix_delivery_order_items_product_id', 'delivery_order_items', ['product_id'], unique=False)
    op.create_index('ix_delivery_order_items_corrects_id', 'delivery_order_items', ['corrects_id'], unique=False)
    op.create_table('inventory_count_items',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('inventory_count_id', sa.Uuid(), nullable=False),
    sa.Column('product_id', sa.Uuid(), nullable=False),
    sa.Column('quantity', sa.Numeric(), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('corrects_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('corrects_id IS DISTINCT FROM id', name='ck_inventory_count_items_no_self_correction'),
    sa.CheckConstraint('quantity >= 0', name='ck_inventory_count_items_quantity_nonneg'),
    sa.ForeignKeyConstraint(['corrects_id'], ['inventory_count_items.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['inventory_count_id'], ['inventory_counts.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_inventory_count_items_count_id', 'inventory_count_items', ['inventory_count_id'], unique=False)
    op.create_index('ix_inventory_count_items_product_id', 'inventory_count_items', ['product_id'], unique=False)
    op.create_index('ix_inventory_count_items_corrects_id', 'inventory_count_items', ['corrects_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema.

    Raises RuntimeError in production to prevent accidental data loss.
    Restore from a PostgreSQL backup instead of running downgrade in prod.
    """
    app_env = os.environ.get("COCINA_APP_ENV", "dev")
    if app_env == "prod":
        raise RuntimeError(
            "Downgrade prohibited in production — restore from PostgreSQL backup instead"
        )

    op.drop_index('ix_inventory_count_items_corrects_id', table_name='inventory_count_items')
    op.drop_index('ix_inventory_count_items_product_id', table_name='inventory_count_items')
    op.drop_index('ix_inventory_count_items_count_id', table_name='inventory_count_items')
    op.drop_table('inventory_count_items')
    op.drop_index('ix_delivery_order_items_corrects_id', table_name='delivery_order_items')
    op.drop_index('ix_delivery_order_items_product_id', table_name='delivery_order_items')
    op.drop_index('ix_delivery_order_items_order_id', table_name='delivery_order_items')
    op.drop_table('delivery_order_items')
    op.drop_index('ix_delivery_items_corrects_id', table_name='delivery_items')
    op.drop_index('ix_delivery_items_product_id', table_name='delivery_items')
    op.drop_index('ix_delivery_items_delivery_id', table_name='delivery_items')
    op.drop_table('delivery_items')
    op.drop_index('ix_products_name_active', table_name='products', postgresql_where=sa.text('is_active = true'))
    op.drop_table('products')
    op.drop_index('ix_inventory_counts_status', table_name='inventory_counts')
    op.drop_table('inventory_counts')
    op.drop_index('ix_delivery_orders_corrects_id', table_name='delivery_orders')
    op.drop_index('ix_delivery_orders_status', table_name='delivery_orders')
    op.drop_table('delivery_orders')
    op.drop_index('ix_deliveries_status', table_name='deliveries')
    op.drop_table('deliveries')
    op.drop_index('ix_users_email_lower', table_name='users')
    op.drop_table('users')
    # Drop PostgreSQL ENUM types explicitly — autogenerate does not include these.
    sa.Enum(name='inventory_count_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='delivery_order_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='delivery_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='product_unit').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='user_role').drop(op.get_bind(), checkfirst=True)
