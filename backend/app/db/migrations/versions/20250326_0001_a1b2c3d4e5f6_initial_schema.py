"""Initial schema — all core tables.

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2025-03-26 00:01:00.000000 UTC

Notes:
- Compatible with both SQLite (demo) and PostgreSQL (production).
- JSONB columns are rendered as JSON on SQLite, JSONB on PostgreSQL.
- Partial indexes and GIN indexes for PostgreSQL are in the next migration
  (b2c3d4e5f6a7_postgres_indexes).
- render_as_batch=True in env.py handles SQLite ALTER TABLE limits.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # tenants
    # ------------------------------------------------------------------ #
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("plan", sa.String(50), nullable=False, server_default="standard"),
        sa.Column("settings", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("vault_key_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(now())")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(now())")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_tenants_slug"),
        sa.CheckConstraint("plan IN ('standard','enterprise','trial')", name="ck_tenants_plan"),
    )
    op.create_index("ix_tenants_slug", "tenants", ["slug"])
    op.create_index("ix_tenants_is_deleted", "tenants", ["is_deleted"])
    op.create_index("ix_tenants_active_slug", "tenants", ["slug", "is_deleted"])

    # ------------------------------------------------------------------ #
    # adapters
    # ------------------------------------------------------------------ #
    op.create_table(
        "adapters",
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(now())")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(now())")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_adapters_slug"),
        sa.CheckConstraint(
            "category IN ('bureau','kyc','payment','fraud','open_banking','gst','other')",
            name="ck_adapters_category",
        ),
    )
    op.create_index("ix_adapters_slug", "adapters", ["slug"])
    op.create_index("ix_adapters_category", "adapters", ["category"])

    # ------------------------------------------------------------------ #
    # adapter_versions
    # ------------------------------------------------------------------ #
    op.create_table(
        "adapter_versions",
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("adapter_id", sa.String(32), nullable=False),
        sa.Column("semver", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("input_schema", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("output_schema", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("default_config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("is_breaking", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("changelog", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(now())")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(now())")),
        sa.ForeignKeyConstraint(["adapter_id"], ["adapters.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("adapter_id", "semver", name="uq_adapter_versions_adapter_semver"),
        sa.CheckConstraint(
            "status IN ('draft','published','deprecated','retired')",
            name="ck_adapter_versions_status",
        ),
    )
    op.create_index("ix_adapter_versions_adapter_id", "adapter_versions", ["adapter_id"])
    op.create_index("ix_adapter_versions_status", "adapter_versions", ["status"])
    op.create_index("ix_adapter_versions_adapter_status", "adapter_versions", ["adapter_id", "status"])

    # ------------------------------------------------------------------ #
    # integrations
    # ------------------------------------------------------------------ #
    op.create_table(
        "integrations",
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("tenant_id", sa.String(32), nullable=False),
        sa.Column("adapter_version_id", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="provisioning"),
        sa.Column("environment", sa.String(20), nullable=False, server_default="sandbox"),
        sa.Column("runtime_overrides", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(now())")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(now())")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["adapter_version_id"], ["adapter_versions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('provisioning','active','paused','decommissioned')",
            name="ck_integrations_status",
        ),
        sa.CheckConstraint(
            "environment IN ('sandbox','uat','production')",
            name="ck_integrations_environment",
        ),
    )
    op.create_index("ix_integrations_tenant_id", "integrations", ["tenant_id"])
    op.create_index("ix_integrations_adapter_version_id", "integrations", ["adapter_version_id"])
    op.create_index("ix_integrations_status", "integrations", ["status"])
    op.create_index("ix_integrations_tenant_status", "integrations", ["tenant_id", "status", "is_deleted"])
    op.create_index("ix_integrations_tenant_env", "integrations", ["tenant_id", "environment"])

    # ------------------------------------------------------------------ #
    # configurations (created before configuration_versions due to circular FK)
    # ------------------------------------------------------------------ #
    op.create_table(
        "configurations",
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("integration_id", sa.String(32), nullable=False),
        sa.Column("current_version_id", sa.String(32), nullable=True),
        sa.Column("current_version_num", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(30), nullable=False, server_default="manual"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(now())")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(now())")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.ForeignKeyConstraint(["integration_id"], ["integrations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "source IN ('manual','ai_generated','imported','rollback')",
            name="ck_configurations_source",
        ),
        sa.CheckConstraint(
            "status IN ('draft','active','archived')",
            name="ck_configurations_status",
        ),
    )
    op.create_index("ix_configurations_integration_id", "configurations", ["integration_id"])
    op.create_index("ix_configurations_status", "configurations", ["status"])

    # ------------------------------------------------------------------ #
    # configuration_versions
    # ------------------------------------------------------------------ #
    op.create_table(
        "configuration_versions",
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("configuration_id", sa.String(32), nullable=False),
        sa.Column("integration_id", sa.String(32), nullable=False),
        sa.Column("version_num", sa.Integer(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("diff_patch", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("change_source", sa.String(30), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(now())")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(now())")),
        sa.ForeignKeyConstraint(["configuration_id"], ["configurations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["integration_id"], ["integrations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("configuration_id", "version_num", name="uq_config_versions_config_version_num"),
        sa.CheckConstraint(
            "change_source IN ('manual','ai_generated','imported','rollback')",
            name="ck_config_versions_change_source",
        ),
    )
    op.create_index("ix_config_versions_configuration_id", "configuration_versions", ["configuration_id"])
    op.create_index("ix_config_versions_integration_id", "configuration_versions", ["integration_id"])
    op.create_index("ix_config_versions_integration_version", "configuration_versions", ["integration_id", "version_num"])

    # Add deferred FK from configurations.current_version_id → configuration_versions.id
    with op.batch_alter_table("configurations") as batch_op:
        batch_op.create_foreign_key(
            "fk_configs_current_version",
            "configuration_versions",
            ["current_version_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # ------------------------------------------------------------------ #
    # hooks
    # ------------------------------------------------------------------ #
    op.create_table(
        "hooks",
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("adapter_id", sa.String(32), nullable=True),
        sa.Column("integration_id", sa.String(32), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("lifecycle_event", sa.String(50), nullable=False),
        sa.Column("hook_type", sa.String(20), nullable=False),
        sa.Column("handler_config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(now())")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(now())")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.ForeignKeyConstraint(["adapter_id"], ["adapters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["integration_id"], ["integrations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "hook_type IN ('webhook','script','lambda')",
            name="ck_hooks_hook_type",
        ),
        sa.CheckConstraint(
            "(adapter_id IS NOT NULL AND integration_id IS NULL) OR "
            "(adapter_id IS NULL AND integration_id IS NOT NULL)",
            name="ck_hooks_scope_xor",
        ),
    )
    op.create_index("ix_hooks_adapter_id", "hooks", ["adapter_id"])
    op.create_index("ix_hooks_integration_id", "hooks", ["integration_id"])
    op.create_index("ix_hooks_lifecycle_event", "hooks", ["lifecycle_event"])
    op.create_index("ix_hooks_integration_event_enabled", "hooks", ["integration_id", "lifecycle_event", "is_enabled"])

    # ------------------------------------------------------------------ #
    # field_mappings
    # ------------------------------------------------------------------ #
    op.create_table(
        "field_mappings",
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("integration_id", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("mapping_type", sa.String(20), nullable=False, server_default="direct"),
        sa.Column("source_path", sa.String(500), nullable=True),
        sa.Column("target_path", sa.String(500), nullable=False),
        sa.Column("transform_expr", sa.Text(), nullable=True),
        sa.Column("default_value", sa.JSON(), nullable=True),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("ai_confidence", sa.Float(), nullable=True),
        sa.Column("ai_reasoning", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(now())")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(now())")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.ForeignKeyConstraint(["integration_id"], ["integrations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("integration_id", "target_path", name="uq_field_mappings_integration_target"),
        sa.CheckConstraint(
            "mapping_type IN ('direct','transform','computed','constant')",
            name="ck_field_mappings_mapping_type",
        ),
        sa.CheckConstraint(
            "ai_confidence IS NULL OR (ai_confidence >= 0.0 AND ai_confidence <= 1.0)",
            name="ck_field_mappings_ai_confidence_range",
        ),
    )
    op.create_index("ix_field_mappings_integration_id", "field_mappings", ["integration_id"])
    op.create_index("ix_field_mappings_target_path", "field_mappings", ["target_path"])
    op.create_index("ix_field_mappings_integration_enabled", "field_mappings", ["integration_id", "is_enabled"])

    # ------------------------------------------------------------------ #
    # audit_logs
    # ------------------------------------------------------------------ #
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("tenant_id", sa.String(32), nullable=True),
        sa.Column("integration_id", sa.String(32), nullable=True),
        sa.Column("actor_id", sa.String(255), nullable=True),
        sa.Column("actor_type", sa.String(30), nullable=False, server_default="user"),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_id", sa.String(32), nullable=True),
        sa.Column("before_state", sa.JSON(), nullable=True),
        sa.Column("after_state", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("outcome", sa.String(20), nullable=False, server_default="success"),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(now())")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(now())")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["integration_id"], ["integrations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "actor_type IN ('user','service','system','ai_agent')",
            name="ck_audit_logs_actor_type",
        ),
        sa.CheckConstraint(
            "outcome IN ('success','failure','partial')",
            name="ck_audit_logs_outcome",
        ),
    )
    op.create_index("ix_audit_logs_tenant_id", "audit_logs", ["tenant_id"])
    op.create_index("ix_audit_logs_integration_id", "audit_logs", ["integration_id"])
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_entity", "audit_logs", ["entity_type", "entity_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index("ix_audit_logs_tenant_created", "audit_logs", ["tenant_id", "created_at"])
    op.create_index("ix_audit_logs_request_id", "audit_logs", ["request_id"])

    # ------------------------------------------------------------------ #
    # test_results
    # ------------------------------------------------------------------ #
    op.create_table(
        "test_results",
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("integration_id", sa.String(32), nullable=False),
        sa.Column("config_version_id", sa.String(32), nullable=True),
        sa.Column("adapter_version_id", sa.String(32), nullable=True),
        sa.Column("test_suite", sa.String(100), nullable=False, server_default="default"),
        sa.Column("triggered_by", sa.String(30), nullable=False, server_default="manual"),
        sa.Column("environment", sa.String(20), nullable=False, server_default="sandbox"),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("total_assertions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("passed_assertions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_assertions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("request_payload", sa.JSON(), nullable=True),
        sa.Column("response_payload", sa.JSON(), nullable=True),
        sa.Column("assertions", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("external_run_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(now())")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(now())")),
        sa.ForeignKeyConstraint(["integration_id"], ["integrations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["config_version_id"], ["configuration_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["adapter_version_id"], ["adapter_versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('running','passed','failed','error','skipped')",
            name="ck_test_results_status",
        ),
        sa.CheckConstraint(
            "triggered_by IN ('manual','ci','schedule','canary')",
            name="ck_test_results_triggered_by",
        ),
        sa.CheckConstraint(
            "environment IN ('sandbox','uat','production')",
            name="ck_test_results_environment",
        ),
    )
    op.create_index("ix_test_results_integration_id", "test_results", ["integration_id"])
    op.create_index("ix_test_results_config_version_id", "test_results", ["config_version_id"])
    op.create_index("ix_test_results_status", "test_results", ["status"])
    op.create_index("ix_test_results_created_at", "test_results", ["created_at"])
    op.create_index("ix_test_results_integration_created", "test_results", ["integration_id", "created_at"])
    op.create_index("ix_test_results_integration_suite_status", "test_results", ["integration_id", "test_suite", "status"])


def downgrade() -> None:
    op.drop_table("test_results")
    op.drop_table("audit_logs")
    op.drop_table("field_mappings")
    op.drop_table("hooks")

    with op.batch_alter_table("configurations") as batch_op:
        batch_op.drop_constraint("fk_configs_current_version", type_="foreignkey")

    op.drop_table("configuration_versions")
    op.drop_table("configurations")
    op.drop_table("integrations")
    op.drop_table("adapter_versions")
    op.drop_table("adapters")
    op.drop_table("tenants")
