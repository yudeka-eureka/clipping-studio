"""create model_keys table

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-18 14:02:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if "model_keys" not in tables:
        op.create_table(
            "model_keys",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("type", sa.String(length=30), nullable=False),
            sa.Column("provider", sa.String(length=50), nullable=False),
            sa.Column("key", sa.Text(), nullable=False),
            sa.Column("secret_key", sa.Text(), nullable=True),
            sa.Column("r2_account_id", sa.Text(), nullable=True),
            sa.Column("r2_bucket", sa.String(length=255), nullable=True),
            sa.Column("r2_bucket_url", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "type", "provider", name="uq_user_type_provider"),
            mysql_charset="utf8mb4",
        )
        op.create_index("idx_user_type", "model_keys", ["user_id", "type"])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    if "model_keys" in tables:
        op.drop_table("model_keys")
