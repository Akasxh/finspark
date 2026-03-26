"""
TestResult model.

Captures the outcome of a simulation run against a specific
Integration configuration.  Used by the Simulation & Testing Framework.

A test run can be triggered:
  - manually by a user before activating a config
  - automatically by the CI pipeline on config change
  - as a canary check during version rollout

request_payload / response_payload stored as JSONB for assertion queries
(e.g., "find all test runs where response contained error_code=AUTH_FAIL").
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, JSONBType, TimestampMixin, uuid_pk

if TYPE_CHECKING:
    from app.db.models.integration import Integration
    from app.db.models.configuration import ConfigurationVersion


class TestResult(TimestampMixin, Base):
    """
    Immutable test execution record.  Never updated after INSERT.
    """

    __tablename__ = "test_results"

    id: Mapped[str] = uuid_pk()
    integration_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Pin to the exact config version being tested
    config_version_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("configuration_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Which adapter version was active during the test
    adapter_version_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("adapter_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    test_suite: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="default",
        comment="Named group: smoke, regression, contract, canary",
    )
    triggered_by: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="manual",
        comment="manual | ci | schedule | canary",
    )
    environment: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="sandbox",
        comment="sandbox | uat | production",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="running | passed | failed | error | skipped",
    )
    # Aggregate counts
    total_assertions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    passed_assertions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_assertions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Timing
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Full request/response for inspection; scrubbed of PII before storage
    request_payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSONBType(), nullable=True
    )
    response_payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSONBType(), nullable=True
    )
    # Structured assertion results
    assertions: Mapped[dict[str, Any]] = mapped_column(
        JSONBType(),
        nullable=False,
        default=dict,
        server_default="{}",
        comment="[{name, status, expected, actual, message}]",
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Correlation back to external CI run or job ID
    external_run_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relationships
    integration: Mapped["Integration"] = relationship(
        "Integration",
        back_populates="test_results",
        lazy="noload",
    )
    config_version: Mapped["ConfigurationVersion | None"] = relationship(
        "ConfigurationVersion",
        foreign_keys=[config_version_id],
        lazy="noload",
    )

    __table_args__ = (
        Index("ix_test_results_integration_id", "integration_id"),
        Index("ix_test_results_config_version_id", "config_version_id"),
        Index("ix_test_results_status", "status"),
        Index("ix_test_results_created_at", "created_at"),
        # "Latest N test runs for an integration"
        Index(
            "ix_test_results_integration_created",
            "integration_id",
            "created_at",
        ),
        # "All failures for an integration in a test suite"
        Index(
            "ix_test_results_integration_suite_status",
            "integration_id",
            "test_suite",
            "status",
        ),
        CheckConstraint(
            "status IN ('running','passed','failed','error','skipped')",
            name="ck_test_results_status",
        ),
        CheckConstraint(
            "triggered_by IN ('manual','ci','schedule','canary')",
            name="ck_test_results_triggered_by",
        ),
        CheckConstraint(
            "environment IN ('sandbox','uat','production')",
            name="ck_test_results_environment",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<TestResult id={self.id} integration={self.integration_id} "
            f"suite={self.test_suite} status={self.status}>"
        )
