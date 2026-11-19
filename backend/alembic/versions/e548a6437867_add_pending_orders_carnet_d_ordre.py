"""add pending_orders (carnet d'ordre)

Revision ID: e548a6437867
Revises: 82c206b49bc3
Create Date: 2026-11-19 22:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e548a6437867'
down_revision: Union[str, Sequence[str], None] = '82c206b49bc3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'pending_orders',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('portfolio_id', sa.Integer(), sa.ForeignKey('portfolios.id'), nullable=False),
        sa.Column('asset_id', sa.Integer(), sa.ForeignKey('assets.id'), nullable=False),
        sa.Column('side', sa.Enum('BUY', 'SELL', name='transactionside', create_type=False), nullable=False),
        sa.Column(
            'order_type',
            sa.Enum('LIMIT', 'STOP_LOSS', 'TAKE_PROFIT', name='pendingordertype'),
            nullable=False,
        ),
        sa.Column('quantity', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('trigger_price', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column(
            'status',
            sa.Enum('PENDING', 'EXECUTED', 'CANCELLED', name='pendingorderstatus'),
            nullable=False,
            server_default='PENDING',
        ),
        sa.Column('note', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('executed_at', sa.DateTime(), nullable=True),
        sa.Column('transaction_id', sa.Integer(), sa.ForeignKey('transactions.id'), nullable=True),
    )
    op.create_index('ix_pending_orders_status', 'pending_orders', ['status'])
    op.create_index('ix_pending_orders_portfolio_id', 'pending_orders', ['portfolio_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_pending_orders_portfolio_id', table_name='pending_orders')
    op.drop_index('ix_pending_orders_status', table_name='pending_orders')
    op.drop_table('pending_orders')
    op.execute('DROP TYPE IF EXISTS pendingordertype')
    op.execute('DROP TYPE IF EXISTS pendingorderstatus')
