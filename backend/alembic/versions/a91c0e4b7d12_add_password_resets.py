"""add password_resets

Revision ID: a91c0e4b7d12
Revises: 0296c4bac95a
Create Date: 2026-11-12 19:45:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a91c0e4b7d12"
down_revision: Union[str, Sequence[str], None] = "0296c4bac95a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "password_resets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_password_resets_user_id"), "password_resets", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_password_resets_user_id"), table_name="password_resets")
    op.drop_table("password_resets")
