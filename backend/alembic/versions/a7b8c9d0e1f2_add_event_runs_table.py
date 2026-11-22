"""add event_runs table

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
Create Date: 2026-11-22 19:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'event_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('event_key', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('day_index', sa.Integer(), nullable=False),
        sa.Column('cash', sa.Float(), nullable=False),
        sa.Column('positions', sa.JSON(), nullable=False),
        sa.Column('equity_curve', sa.JSON(), nullable=False),
        sa.Column('score', sa.Float(), nullable=True),
        sa.Column('return_pct', sa.Float(), nullable=True),
        sa.Column('max_drawdown_pct', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_event_runs_user_id'), 'event_runs', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_event_runs_user_id'), table_name='event_runs')
    op.drop_table('event_runs')
