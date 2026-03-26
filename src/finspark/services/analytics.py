"""Analytics service - provides integration metrics and insights."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from finspark.models.audit import AuditLog
from finspark.models.configuration import Configuration
from finspark.models.document import Document
from finspark.models.simulation import Simulation


class AnalyticsService:
    """Provides dashboard metrics and analytics for tenant integrations."""

    def __init__(self, db: AsyncSession, tenant_id: str) -> None:
        self.db = db
        self.tenant_id = tenant_id

    async def get_dashboard_metrics(self) -> dict[str, Any]:
        """Get overview metrics for the tenant dashboard."""
        configs = await self._config_stats()
        simulations = await self._simulation_stats()
        documents = await self._document_stats()
        audit_count = await self._audit_count()

        return {
            "configurations": configs,
            "simulations": simulations,
            "documents": documents,
            "audit_entries": audit_count,
            "health_score": self._calculate_health_score(configs, simulations),
        }

    async def _config_stats(self) -> dict[str, Any]:
        stmt = (
            select(Configuration.status, func.count())
            .where(Configuration.tenant_id == self.tenant_id)
            .group_by(Configuration.status)
        )
        result = await self.db.execute(stmt)
        by_status = dict(result.all())

        total = sum(by_status.values())
        return {
            "total": total,
            "by_status": by_status,
            "active": by_status.get("active", 0) + by_status.get("testing", 0),
            "draft": by_status.get("draft", 0) + by_status.get("configured", 0),
        }

    async def _simulation_stats(self) -> dict[str, Any]:
        stmt = (
            select(Simulation.status, func.count())
            .where(Simulation.tenant_id == self.tenant_id)
            .group_by(Simulation.status)
        )
        result = await self.db.execute(stmt)
        by_status = dict(result.all())

        total = sum(by_status.values())
        passed = by_status.get("passed", 0)

        stmt_avg = select(func.avg(Simulation.duration_ms)).where(
            Simulation.tenant_id == self.tenant_id,
            Simulation.duration_ms.isnot(None),
        )
        avg_result = await self.db.execute(stmt_avg)
        avg_duration = avg_result.scalar() or 0

        return {
            "total": total,
            "passed": passed,
            "failed": by_status.get("failed", 0),
            "pass_rate": round(passed / total, 2) if total > 0 else 0.0,
            "avg_duration_ms": round(avg_duration, 0),
        }

    async def _document_stats(self) -> dict[str, Any]:
        stmt = (
            select(Document.status, func.count())
            .where(Document.tenant_id == self.tenant_id)
            .group_by(Document.status)
        )
        result = await self.db.execute(stmt)
        by_status = dict(result.all())
        return {"total": sum(by_status.values()), "by_status": by_status}

    async def _audit_count(self) -> int:
        stmt = (
            select(func.count()).select_from(AuditLog).where(AuditLog.tenant_id == self.tenant_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    @staticmethod
    def _calculate_health_score(configs: dict[str, Any], simulations: dict[str, Any]) -> float:
        """Calculate overall integration health score (0-100)."""
        score = 50.0  # base score

        # Config activity bonus
        if configs["total"] > 0:
            score += 10

        # Active configs bonus
        if configs["active"] > 0:
            score += 15

        # Simulation pass rate bonus
        pass_rate = simulations.get("pass_rate", 0)
        score += pass_rate * 25

        return min(100.0, round(score, 1))
