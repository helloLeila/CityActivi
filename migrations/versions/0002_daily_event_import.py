"""Add supplementary data, source aliases and import receipts without changing old rows."""
from alembic import op
import sqlalchemy as sa

revision = "0002_daily_event_import"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("event_supplements", sa.Column("event_key", sa.String(100), primary_key=True),
                    sa.Column("document", sa.JSON(), nullable=False))
    op.create_table("event_source_aliases", sa.Column("url_hash", sa.String(64), primary_key=True),
                    sa.Column("normalized_url", sa.Text(), nullable=False),
                    sa.Column("event_key", sa.String(100), nullable=False))
    op.create_index("ix_event_source_aliases_event_key", "event_source_aliases", ["event_key"])
    op.create_table("event_import_batches", sa.Column("digest", sa.String(64), primary_key=True),
                    sa.Column("report", sa.JSON(), nullable=False),
                    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table("event_import_batches")
    op.drop_index("ix_event_source_aliases_event_key", table_name="event_source_aliases")
    op.drop_table("event_source_aliases")
    op.drop_table("event_supplements")
