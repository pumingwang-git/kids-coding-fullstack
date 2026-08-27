"""index audit event time queries

Revision ID: 0069_audit_events_created_idx
Revises: 0068_help_request_lifecycle
"""

from alembic import op

revision = "0069_audit_events_created_idx"
down_revision = "0068_help_request_lifecycle"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])


def downgrade():
    op.drop_index("ix_audit_events_created_at", table_name="audit_events")
