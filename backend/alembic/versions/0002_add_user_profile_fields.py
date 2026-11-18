"""add user profile fields

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-18 14:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "users" not in inspector.get_table_names():
        return
    cols = [c["name"] for c in inspector.get_columns("users")]

    if "profile_photo" not in cols:
        op.add_column("users", sa.Column("profile_photo", sa.String(length=500), nullable=True))
    if "username_changed_at" not in cols:
        op.add_column("users", sa.Column("username_changed_at", sa.TIMESTAMP(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "users" not in inspector.get_table_names():
        return
    cols = [c["name"] for c in inspector.get_columns("users")]

    if "username_changed_at" in cols:
        op.drop_column("users", "username_changed_at")
    if "profile_photo" in cols:
        op.drop_column("users", "profile_photo")
