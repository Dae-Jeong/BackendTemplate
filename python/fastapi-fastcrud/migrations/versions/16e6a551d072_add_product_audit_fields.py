"""add product audit fields

Revision ID: 16e6a551d072
Revises: 7372e3cacca4
Create Date: 2026-09-15 17:24:07.332143

"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "16e6a551d072"
down_revision: str | Sequence[str] | None = "7372e3cacca4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    audit_started_at = datetime.now(UTC)
    op.add_column(
        "products", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "products", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("products", sa.Column("is_deleted", sa.Boolean(), nullable=True))
    op.add_column(
        "products", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute(
        sa.update(
            sa.table(
                "products",
                sa.column("created_at"),
                sa.column("updated_at"),
                sa.column("is_deleted"),
            )
        ).values(
            created_at=audit_started_at,
            updated_at=audit_started_at,
            is_deleted=False,
        )
    )
    with op.batch_alter_table("products", recreate="always") as batch_op:
        batch_op.alter_column("created_at", existing_type=sa.DateTime(), nullable=False)
        batch_op.alter_column("updated_at", existing_type=sa.DateTime(), nullable=False)
        batch_op.alter_column("is_deleted", existing_type=sa.Boolean(), nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("products", recreate="always") as batch_op:
        batch_op.drop_column("deleted_at")
        batch_op.drop_column("is_deleted")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("created_at")
