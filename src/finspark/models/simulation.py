"""Simulation and test result models."""

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from finspark.models.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class Simulation(Base, UUIDMixin, TenantMixin, TimestampMixin):
    """Integration simulation/test run."""

    __tablename__ = "simulations"

    configuration_id: Mapped[str] = mapped_column(ForeignKey("configurations.id"), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending, running, passed, failed, error
    test_type: Mapped[str] = mapped_column(
        String(50), default="full"
    )  # full, smoke, schema_only, parallel_version
    total_tests: Mapped[int] = mapped_column(Integer, default=0)
    passed_tests: Mapped[int] = mapped_column(Integer, default=0)
    failed_tests: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    results: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON - detailed results
    error_log: Mapped[str | None] = mapped_column(Text, nullable=True)


class SimulationStep(Base, UUIDMixin, TimestampMixin):
    """Individual test step within a simulation."""

    __tablename__ = "simulation_steps"

    simulation_id: Mapped[str] = mapped_column(ForeignKey("simulations.id"), nullable=False)
    step_name: Mapped[str] = mapped_column(String(255), nullable=False)
    step_order: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    request_payload: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    expected_response: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    actual_response: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
