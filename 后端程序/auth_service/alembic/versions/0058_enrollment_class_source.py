"""record the source class for class enrollment grants

Revision ID: 0058_enrollment_class_source
Revises: 0057_enrollment_history
"""
import sqlalchemy as sa

from alembic import op

revision = "0058_enrollment_class_source"
down_revision = "0057_enrollment_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite requires table rebuilds when adding a foreign key.
    with op.batch_alter_table("enrollments") as batch:
        batch.add_column(
            sa.Column(
                "class_id",
                sa.Integer(),
                nullable=True,
            )
        )
        batch.create_foreign_key(
            "fk_enrollments_class_id_class_groups",
            "class_groups",
            ["class_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_index("ix_enrollments_class_id", ["class_id"])


def downgrade() -> None:
    with op.batch_alter_table("enrollments") as batch:
        batch.drop_index("ix_enrollments_class_id")
        batch.drop_constraint("fk_enrollments_class_id_class_groups", type_="foreignkey")
        batch.drop_column("class_id")
