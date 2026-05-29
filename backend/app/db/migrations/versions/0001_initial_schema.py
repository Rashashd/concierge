"""initial schema — all tables with RLS policies.

Revision ID: 0001
Revises:
Create Date: 2026-05-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # tenants
    op.create_table(
        "tenants",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), unique=True, nullable=False),
        sa.Column(
            "is_active", sa.Boolean, nullable=False, server_default=sa.text("true")
        ),
        sa.Column("llm_persona", sa.Text, nullable=False, server_default=sa.text("''")),
        sa.Column(
            "guardrail_config",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "allowed_origins",
            postgresql.ARRAY(sa.Text),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_tenants_slug", "tenants", ["slug"])

    # users
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.String(320), unique=True, nullable=False),
        sa.Column("hashed_password", sa.Text, nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=True,
        ),
        sa.Column(
            "is_active", sa.Boolean, nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])

    # content_items
    op.create_table(
        "content_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("content_type", sa.String(50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_content_items_tenant_id", "content_items", ["tenant_id"])
    op.execute("""
        ALTER TABLE content_items ENABLE ROW LEVEL SECURITY;
        ALTER TABLE content_items FORCE ROW LEVEL SECURITY;
        CREATE POLICY tenant_isolation ON content_items
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
    """)

    # chunks
    op.create_table(
        "chunks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column(
            "content_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("content_items.id"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column(
            "embedding", sa.Text, nullable=False
        ),  # cast to vector(1536) below after extension loads
        sa.Column(
            "metadata", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.execute(
        "ALTER TABLE chunks ALTER COLUMN embedding TYPE vector(1536) USING embedding::vector(1536)"
    )
    op.create_index("ix_chunks_tenant_id", "chunks", ["tenant_id"])
    op.create_index("ix_chunks_content_item_id", "chunks", ["content_item_id"])
    # HNSW index for ANN search
    op.execute("""
        CREATE INDEX ix_chunks_embedding_hnsw ON chunks
            USING hnsw (embedding vector_cosine_ops);
    """)
    op.execute("""
        ALTER TABLE chunks ENABLE ROW LEVEL SECURITY;
        ALTER TABLE chunks FORCE ROW LEVEL SECURITY;
        CREATE POLICY tenant_isolation ON chunks
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
    """)

    # leads
    op.create_table(
        "leads",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column("session_id", sa.String(255), nullable=False),
        sa.Column("visitor_name", sa.String(255), nullable=True),
        sa.Column("contact", sa.String(320), nullable=False),
        sa.Column("intent", sa.Text, nullable=False),
        sa.Column(
            "status", sa.String(50), nullable=False, server_default=sa.text("'new'")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_leads_tenant_id", "leads", ["tenant_id"])
    op.create_index("ix_leads_session_id", "leads", ["session_id"])
    op.execute("""
        ALTER TABLE leads ENABLE ROW LEVEL SECURITY;
        ALTER TABLE leads FORCE ROW LEVEL SECURITY;
        CREATE POLICY tenant_isolation ON leads
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
    """)

    # widget_configs
    op.create_table(
        "widget_configs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column(
            "widget_id",
            postgresql.UUID(as_uuid=True),
            unique=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "greeting",
            sa.Text,
            nullable=False,
            server_default=sa.text("'Hi, how can I help you?'"),
        ),
        sa.Column(
            "theme_color",
            sa.String(7),
            nullable=False,
            server_default=sa.text("'#0066CC'"),
        ),
        sa.Column(
            "enabled_tools",
            postgresql.ARRAY(sa.Text),
            nullable=False,
            server_default=sa.text("'{rag_search,capture_lead,escalate}'"),
        ),
        sa.Column(
            "is_active", sa.Boolean, nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_widget_configs_tenant_id", "widget_configs", ["tenant_id"])
    op.create_index("ix_widget_configs_widget_id", "widget_configs", ["widget_id"])
    op.execute("""
        ALTER TABLE widget_configs ENABLE ROW LEVEL SECURITY;
        ALTER TABLE widget_configs FORCE ROW LEVEL SECURITY;
        CREATE POLICY tenant_isolation ON widget_configs
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
    """)

    # audit_logs
    op.create_table(
        "audit_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_role", sa.String(50), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column(
            "payload", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_audit_logs_tenant_id", "audit_logs", ["tenant_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("widget_configs")
    op.drop_table("leads")
    op.drop_table("chunks")
    op.drop_table("content_items")
    op.drop_table("users")
    op.drop_table("tenants")
    op.execute("DROP EXTENSION IF EXISTS pgvector")
