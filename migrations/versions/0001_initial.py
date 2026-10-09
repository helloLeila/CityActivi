"""Create CityActivi v1 tables."""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("configuration_versions", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("revision", sa.Integer(), nullable=False, unique=True), sa.Column("document", sa.JSON(), nullable=False), sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("event_fact_versions", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("event_key", sa.String(100), nullable=False), sa.Column("title", sa.String(300), nullable=False), sa.Column("start_at", sa.DateTime(timezone=True), nullable=False), sa.Column("end_at", sa.DateTime(timezone=True)), sa.Column("timezone", sa.String(64), nullable=False), sa.Column("city", sa.String(64), nullable=False), sa.Column("venue", sa.String(300), nullable=False), sa.Column("organizer", sa.String(200), nullable=False), sa.Column("canonical_url", sa.Text(), nullable=False), sa.Column("technical_signal", sa.Text(), nullable=False), sa.Column("cover_url", sa.Text()), sa.Column("evidence", sa.JSON(), nullable=False))
    op.create_table("event_enrichment_versions", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("event_key", sa.String(100), nullable=False), sa.Column("summary", sa.Text(), nullable=False), sa.Column("calendar_summary", sa.Text(), nullable=False), sa.Column("why_worth", sa.Text(), nullable=False), sa.Column("takeaways", sa.JSON(), nullable=False), sa.Column("prerequisites", sa.JSON(), nullable=False), sa.Column("topic", sa.String(150), nullable=False), sa.Column("kind", sa.String(64), nullable=False), sa.Column("relevance", sa.String(32), nullable=False), sa.Column("commute_minutes", sa.Integer()), sa.Column("community", sa.String(150)), sa.Column("source_name", sa.String(100), nullable=False))
    op.create_table("events", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("event_key", sa.String(100), nullable=False, unique=True), sa.Column("status", sa.String(32), nullable=False), sa.Column("current_fact_version_id", sa.Integer(), nullable=False), sa.Column("current_enrichment_version_id", sa.Integer(), nullable=False), sa.Column("published_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("event_versions", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("event_key", sa.String(100), nullable=False), sa.Column("fact_version_id", sa.Integer(), nullable=False), sa.Column("enrichment_version_id", sa.Integer(), nullable=False), sa.Column("published_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("event_status_changes", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("event_key", sa.String(100), nullable=False), sa.Column("old_status", sa.String(32)), sa.Column("new_status", sa.String(32), nullable=False), sa.Column("trigger_source", sa.String(64), nullable=False), sa.Column("evidence", sa.JSON(), nullable=False), sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("job_runs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("job_type", sa.String(64), nullable=False), sa.Column("status", sa.String(32), nullable=False), sa.Column("delivery_key", sa.String(200), nullable=False, unique=True), sa.Column("progress", sa.Integer(), nullable=False), sa.Column("message", sa.Text(), nullable=False), sa.Column("error_code", sa.String(120)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("raw_documents", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("source_name", sa.String(100), nullable=False), sa.Column("source_url", sa.Text(), nullable=False), sa.Column("content_hash", sa.String(64), nullable=False), sa.Column("status_code", sa.Integer(), nullable=False), sa.Column("parser_name", sa.String(100), nullable=False), sa.Column("body_preview", sa.Text(), nullable=False), sa.Column("etag", sa.String(200)), sa.Column("last_modified", sa.String(200)), sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False))


def downgrade() -> None:
    for table in ("raw_documents", "job_runs", "event_status_changes", "event_versions", "events", "event_enrichment_versions", "event_fact_versions", "configuration_versions"):
        op.drop_table(table)
