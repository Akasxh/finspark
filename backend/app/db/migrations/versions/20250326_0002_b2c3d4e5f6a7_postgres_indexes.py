"""PostgreSQL-specific indexes: GIN on JSONB, partial indexes for soft-delete.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2025-03-26 00:02:00.000000 UTC

This migration is a NO-OP on SQLite (guards via dialect check).
Apply in production after switching DATABASE_URL to postgresql+asyncpg.

Indexes added:
1. GIN index on configurations.data           — JSONB key/value queries
2. GIN index on audit_logs.before/after_state — compliance diff searches
3. GIN index on adapters.metadata             — metadata tag filtering
4. Partial index on integrations (is_deleted=false) — active-only scans
5. Partial index on tenants (is_deleted=false)
6. Partial index on configurations (status='active')

These are advisory for the hackathon demo and critical for production
performance at scale.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
import sqlalchemy as sa

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_postgresql() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgresql():
        return  # SQLite: skip all PostgreSQL-specific DDL

    # ------------------------------------------------------------------ #
    # Upgrade JSON columns to JSONB on PostgreSQL
    # ------------------------------------------------------------------ #
    jsonb_upgrades = [
        ("tenants", "settings"),
        ("adapters", "metadata"),
        ("adapter_versions", "input_schema"),
        ("adapter_versions", "output_schema"),
        ("adapter_versions", "default_config"),
        ("integrations", "runtime_overrides"),
        ("configurations", "current_version_id"),  # not JSON, skip
        ("configuration_versions", "data"),
        ("configuration_versions", "diff_patch"),
        ("hooks", "handler_config"),
        ("field_mappings", "default_value"),
        ("audit_logs", "before_state"),
        ("audit_logs", "after_state"),
        ("audit_logs", "metadata"),
        ("test_results", "request_payload"),
        ("test_results", "response_payload"),
        ("test_results", "assertions"),
    ]
    _json_columns = [
        ("tenants", "settings"),
        ("adapters", "metadata"),
        ("adapter_versions", "input_schema"),
        ("adapter_versions", "output_schema"),
        ("adapter_versions", "default_config"),
        ("integrations", "runtime_overrides"),
        ("configuration_versions", "data"),
        ("configuration_versions", "diff_patch"),
        ("hooks", "handler_config"),
        ("field_mappings", "default_value"),
        ("audit_logs", "before_state"),
        ("audit_logs", "after_state"),
        ("audit_logs", "metadata"),
        ("test_results", "request_payload"),
        ("test_results", "response_payload"),
        ("test_results", "assertions"),
    ]
    for table, column in _json_columns:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} TYPE JSONB "
            f"USING {column}::JSONB"
        )

    # ------------------------------------------------------------------ #
    # GIN indexes for JSONB containment queries (@>, ?, ?|, ?&)
    # ------------------------------------------------------------------ #
    op.execute(
        "CREATE INDEX ix_gin_config_versions_data "
        "ON configuration_versions USING gin (data jsonb_path_ops)"
    )
    op.execute(
        "CREATE INDEX ix_gin_audit_logs_before_state "
        "ON audit_logs USING gin (before_state jsonb_path_ops)"
    )
    op.execute(
        "CREATE INDEX ix_gin_audit_logs_after_state "
        "ON audit_logs USING gin (after_state jsonb_path_ops)"
    )
    op.execute(
        "CREATE INDEX ix_gin_adapters_metadata "
        "ON adapters USING gin (metadata jsonb_path_ops)"
    )
    op.execute(
        "CREATE INDEX ix_gin_test_results_assertions "
        "ON test_results USING gin (assertions jsonb_path_ops)"
    )

    # ------------------------------------------------------------------ #
    # Partial indexes — only index live (non-deleted) rows
    # ------------------------------------------------------------------ #
    op.execute(
        "CREATE INDEX ix_tenants_active "
        "ON tenants (slug, created_at) "
        "WHERE is_deleted = false"
    )
    op.execute(
        "CREATE INDEX ix_integrations_active_tenant "
        "ON integrations (tenant_id, status, environment) "
        "WHERE is_deleted = false"
    )
    op.execute(
        "CREATE INDEX ix_configurations_active "
        "ON configurations (integration_id) "
        "WHERE status = 'active' AND is_deleted = false"
    )
    op.execute(
        "CREATE INDEX ix_hooks_active_integration "
        "ON hooks (integration_id, lifecycle_event) "
        "WHERE is_enabled = true AND is_deleted = false"
    )
    op.execute(
        "CREATE INDEX ix_field_mappings_active "
        "ON field_mappings (integration_id, target_path) "
        "WHERE is_enabled = true AND is_deleted = false"
    )

    # ------------------------------------------------------------------ #
    # BRIN index on audit_logs.created_at for time-range scans
    # (much smaller than B-tree for append-only tables)
    # ------------------------------------------------------------------ #
    op.execute(
        "CREATE INDEX ix_brin_audit_logs_created_at "
        "ON audit_logs USING brin (created_at)"
    )
    op.execute(
        "CREATE INDEX ix_brin_test_results_created_at "
        "ON test_results USING brin (created_at)"
    )


def downgrade() -> None:
    if not _is_postgresql():
        return

    drop_indexes = [
        "ix_brin_test_results_created_at",
        "ix_brin_audit_logs_created_at",
        "ix_field_mappings_active",
        "ix_hooks_active_integration",
        "ix_configurations_active",
        "ix_integrations_active_tenant",
        "ix_tenants_active",
        "ix_gin_test_results_assertions",
        "ix_gin_adapters_metadata",
        "ix_gin_audit_logs_after_state",
        "ix_gin_audit_logs_before_state",
        "ix_gin_config_versions_data",
    ]
    for idx in drop_indexes:
        op.execute(f"DROP INDEX IF EXISTS {idx}")

    # Downgrade JSONB back to JSON
    _json_columns = [
        ("tenants", "settings"),
        ("adapters", "metadata"),
        ("adapter_versions", "input_schema"),
        ("adapter_versions", "output_schema"),
        ("adapter_versions", "default_config"),
        ("integrations", "runtime_overrides"),
        ("configuration_versions", "data"),
        ("configuration_versions", "diff_patch"),
        ("hooks", "handler_config"),
        ("field_mappings", "default_value"),
        ("audit_logs", "before_state"),
        ("audit_logs", "after_state"),
        ("audit_logs", "metadata"),
        ("test_results", "request_payload"),
        ("test_results", "response_payload"),
        ("test_results", "assertions"),
    ]
    for table, column in _json_columns:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} TYPE JSON "
            f"USING {column}::JSON"
        )
