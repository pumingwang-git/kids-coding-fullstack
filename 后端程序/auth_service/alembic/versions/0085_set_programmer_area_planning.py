"""mark the programmer area as planning

The source catalog has always declared this area as planning. Existing databases
may retain an older active value because the catalog bootstrap intentionally does
not overwrite administrator-managed records.
"""

from alembic import op
import sqlalchemy as sa


revision = "0085_programmer_planning"
down_revision = "0084_help_message_recall"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        sa.text("UPDATE learning_areas SET status = 'planning' WHERE key = 'programmer'")
    )


def downgrade():
    # Do not guess whether an administrator intentionally changed this status later.
    pass
