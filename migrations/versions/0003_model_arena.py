"""Add persistent OpenRouter model Arena runs and interaction transcripts."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("model_arena_runs"):
        op.create_table(
            "model_arena_runs",
            sa.Column("run_id", sa.String(), primary_key=True),
            sa.Column(
                "session_id",
                sa.String(),
                sa.ForeignKey("sessions.session_id"),
                nullable=False,
                unique=True,
            ),
            sa.Column("model_id", sa.String(), nullable=False),
            sa.Column("provider", sa.String(), nullable=False),
            sa.Column(
                "case_id",
                sa.String(),
                sa.ForeignKey("cases.case_id"),
                nullable=False,
            ),
            sa.Column("dataset_name", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("max_questions", sa.Integer(), nullable=False),
            sa.Column("forced_final", sa.Boolean(), nullable=False, default=False),
            sa.Column("last_error", sa.Text()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True)),
        )
        op.create_index(
            "ix_model_arena_runs_session_id", "model_arena_runs", ["session_id"]
        )
        op.create_index(
            "ix_model_arena_runs_model_id", "model_arena_runs", ["model_id"]
        )
        op.create_index(
            "ix_model_arena_runs_provider", "model_arena_runs", ["provider"]
        )
        op.create_index(
            "ix_model_arena_runs_case_id", "model_arena_runs", ["case_id"]
        )
        op.create_index(
            "ix_model_arena_runs_dataset_name",
            "model_arena_runs",
            ["dataset_name"],
        )

    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("model_interactions"):
        op.create_table(
            "model_interactions",
            sa.Column("interaction_id", sa.String(), primary_key=True),
            sa.Column(
                "run_id",
                sa.String(),
                sa.ForeignKey("model_arena_runs.run_id"),
                nullable=False,
            ),
            sa.Column("step", sa.Integer(), nullable=False),
            sa.Column("request_payload", sa.JSON(), nullable=False),
            sa.Column("response_payload", sa.JSON()),
            sa.Column("assistant_content", sa.Text()),
            sa.Column("parsed_decision", sa.JSON()),
            sa.Column("application_result", sa.JSON()),
            sa.Column("error", sa.Text()),
            sa.Column("latency_ms", sa.Integer()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("run_id", "step"),
        )
        op.create_index(
            "ix_model_interactions_run_id", "model_interactions", ["run_id"]
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("model_interactions"):
        op.drop_index(
            "ix_model_interactions_run_id", table_name="model_interactions"
        )
        op.drop_table("model_interactions")
    if inspector.has_table("model_arena_runs"):
        for name in (
            "ix_model_arena_runs_dataset_name",
            "ix_model_arena_runs_case_id",
            "ix_model_arena_runs_provider",
            "ix_model_arena_runs_model_id",
            "ix_model_arena_runs_session_id",
        ):
            op.drop_index(name, table_name="model_arena_runs")
        op.drop_table("model_arena_runs")
