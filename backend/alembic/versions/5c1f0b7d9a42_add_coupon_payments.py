"""add coupon_payments

Revision ID: 5c1f0b7d9a42
Revises: a2aa75d43f95
Create Date: 2026-10-16 12:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5c1f0b7d9a42'
down_revision: Union[str, Sequence[str], None] = 'a2aa75d43f95'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('coupon_payments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('portfolio_id', sa.Integer(), nullable=False),
    sa.Column('position_id', sa.Integer(), nullable=False),
    sa.Column('paid_on', sa.Date(), nullable=False),
    sa.Column('amount', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['portfolio_id'], ['portfolios.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['position_id'], ['positions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('position_id', 'paid_on', name='uq_coupon_position_day')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('coupon_payments')
