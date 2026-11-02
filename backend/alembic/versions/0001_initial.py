"""initial schema with pgvector columns and HNSW indexes

Revision ID: 0001
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

DIM = 384


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    role = sa.Enum("CANDIDATE", "RECRUITER", "ADMIN", name="role")
    resume_status = sa.Enum("PENDING", "PROCESSING", "DONE", "FAILED", name="resume_status")
    app_status = sa.Enum("APPLIED", "SHORTLISTED", "REJECTED", name="app_status")

    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("role", role, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "candidate_profiles",
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("headline", sa.String(255), nullable=False),
        sa.Column("skills", sa.JSON, nullable=False),
        sa.Column("years_experience", sa.Float, nullable=False),
        sa.Column("searchable", sa.Boolean, nullable=False),
    )

    op.create_table(
        "resumes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("candidate_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("path", sa.String(512), nullable=False),
        sa.Column("status", resume_status, nullable=False),
        sa.Column("error", sa.Text),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("parsed", sa.JSON, nullable=False),
        sa.Column("title_embedding", Vector(DIM)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "resume_chunks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("resume_id", sa.Integer, sa.ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idx", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("embedding", Vector(DIM), nullable=False),
    )
    op.create_index("ix_resume_chunks_resume_id", "resume_chunks", ["resume_id"])
    op.execute("CREATE INDEX ix_resume_chunks_embedding_hnsw ON resume_chunks USING hnsw (embedding vector_cosine_ops)")

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("recruiter_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("company", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("must_have", sa.JSON, nullable=False),
        sa.Column("nice_to_have", sa.JSON, nullable=False),
        sa.Column("min_years", sa.Float, nullable=False),
        sa.Column("open", sa.Boolean, nullable=False),
        sa.Column("embedding", Vector(DIM)),
        sa.Column("title_embedding", Vector(DIM)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_jobs_recruiter_id", "jobs", ["recruiter_id"])
    op.execute("CREATE INDEX ix_jobs_embedding_hnsw ON jobs USING hnsw (embedding vector_cosine_ops)")

    op.create_table(
        "applications",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("job_id", sa.Integer, sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", app_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("job_id", "candidate_id"),
    )
    op.create_index("ix_applications_job_id", "applications", ["job_id"])
    op.create_index("ix_applications_candidate_id", "applications", ["candidate_id"])


def downgrade() -> None:
    for t in ("applications", "jobs", "resume_chunks", "resumes", "candidate_profiles", "users"):
        op.drop_table(t)
    for e in ("app_status", "resume_status", "role"):
        op.execute(f"DROP TYPE IF EXISTS {e}")
