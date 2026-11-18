"""add model_keys fields

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-18 14:03:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "model_keys" not in inspector.get_table_names():
        return
    cols = {c["name"]: c for c in inspector.get_columns("model_keys")}

    if "cloud_name" not in cols:
        op.add_column("model_keys", sa.Column("cloud_name", sa.String(length=120), nullable=True))
    if "model" not in cols:
        op.add_column("model_keys", sa.Column("model", sa.String(length=100), nullable=True))
    if "is_active" not in cols:
        op.add_column("model_keys", sa.Column("is_active", sa.Boolean(), server_default=sa.text("0"), nullable=True))

    # Self-healing migration for databases where created_at/updated_at might be DATETIME
    if "created_at" in cols and "DATETIME" in str(cols["created_at"]["type"]).upper():
        op.alter_column("model_keys", "created_at", type_=sa.TIMESTAMP(), existing_nullable=True, server_default=sa.text("CURRENT_TIMESTAMP"))
    if "updated_at" in cols and "DATETIME" in str(cols["updated_at"]["type"]).upper():
        op.alter_column("model_keys", "updated_at", type_=sa.TIMESTAMP(), existing_nullable=True, server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "model_keys" not in inspector.get_table_names():
        return
    cols = [c["name"] for c in inspector.get_columns("model_keys")]

    if "is_active" in cols:
        op.drop_column("model_keys", "is_active")
    if "model" in cols:
        op.drop_column("model_keys", "model")
    if "cloud_name" in cols:
        op.drop_column("model_keys", "cloud_name")
