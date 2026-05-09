"""Contract test run model for live API testing."""

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from finspark.models.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class ContractTestRun(Base, UUIDMixin, TenantMixin, TimestampMixin):
    """Persisted result of a contract test run against a live/sandbox API."""

    __tablename__ = "contract_test_runs"

    configuration_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    adapter_name: Mapped[str] = mapped_column(String(255), nullable=False)
    adapter_version: Mapped[str] = mapped_column(String(50), nullable=False)
    total_endpoints: Mapped[int] = mapped_column(Integer, nullable=False)
    passed: Mapped[int] = mapped_column(Integer, nullable=False)
    failed: Mapped[int] = mapped_column(Integer, nullable=False)
    results: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON-serialised results
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # passed | failed | error
