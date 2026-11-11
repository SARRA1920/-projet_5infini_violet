"""add actuarial tables (actuarial_runs, bond_terms)

Migration additive du module Actuariat : deux nouvelles tables, aucune table
existante modifiée.

Revision ID: 7b1e4a2c9d10
Revises: dc8d3b346bca
Create Date: 2026-11-11 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7b1e4a2c9d10'
down_revision: Union[str, Sequence[str], None] = 'dc8d3b346bca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'actuarial_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('portfolio_id', sa.Integer(), nullable=True),
        sa.Column('model', sa.String(length=40), nullable=False),
        sa.Column('params', sa.JSON(), nullable=False),
        sa.Column('seed', sa.Integer(), nullable=True),
        sa.Column('data_source', sa.String(length=30), nullable=False),
        sa.Column('summary', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['portfolio_id'], ['portfolios.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_actuarial_runs_user_id'), 'actuarial_runs', ['user_id'], unique=False)
    op.create_table(
        'bond_terms',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('face_value', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('coupon_rate', sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column('coupon_frequency', sa.Integer(), nullable=False),
        sa.Column('issue_date', sa.Date(), nullable=True),
        sa.Column('maturity_date', sa.Date(), nullable=False),
        sa.Column('day_count', sa.String(length=20), nullable=False),
        sa.Column('source', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('asset_id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('bond_terms')
    op.drop_index(op.f('ix_actuarial_runs_user_id'), table_name='actuarial_runs')
    op.drop_table('actuarial_runs')
