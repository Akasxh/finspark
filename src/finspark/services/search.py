"""Natural language search service for integrations."""

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from finspark.models.adapter import Adapter
from finspark.models.configuration import Configuration
from finspark.models.simulation import Simulation

# Keyword -> category/status mappings for NL resolution
_CATEGORY_KEYWORDS: dict[str, str] = {
    "kyc": "kyc",
    "ekyc": "kyc",
    "identity": "kyc",
    "verification": "kyc",
    "bureau": "bureau",
    "credit": "bureau",
    "cibil": "bureau",
    "gst": "gst",
    "tax": "gst",
    "gstin": "gst",
    "payment": "payment",
    "pay": "payment",
    "razorpay": "payment",
    "disbursement": "payment",
    "fraud": "fraud",
    "risk": "fraud",
    "notification": "notification",
    "sms": "notification",
    "alert": "notification",
}

_STATUS_KEYWORDS: dict[str, str] = {
    "active": "active",
    "draft": "draft",
    "configured": "configured",
    "testing": "testing",
    "deprecated": "deprecated",
    "rollback": "rollback",
    "validating": "validating",
}

_SIM_STATUS_KEYWORDS: dict[str, str] = {
    "passed": "passed",
    "failed": "failed",
    "error": "error",
    "pending": "pending",
    "running": "running",
}

_AUTH_KEYWORDS: dict[str, str] = {
    "oauth": "oauth2",
    "oauth2": "oauth2",
    "api_key": "api_key",
    "apikey": "api_key",
    "certificate": "certificate",
    "cert": "certificate",
}


@dataclass
class SearchResult:
    """Single search result with relevance score."""

    type: str  # "adapter", "configuration", "simulation"
    id: str
    name: str
    score: float
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResponse:
    """Grouped search results."""

    query: str
    adapters: list[SearchResult] = field(default_factory=list)
    configurations: list[SearchResult] = field(default_factory=list)
    simulations: list[SearchResult] = field(default_factory=list)
    total: int = 0


@dataclass
class _ParsedQuery:
    """Parsed intent from a natural language query."""

    raw: str
    tokens: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)
    sim_statuses: list[str] = field(default_factory=list)
    auth_types: list[str] = field(default_factory=list)


class IntegrationSearch:
    """Keyword-based natural language search over integrations."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def _parse_query(self, query: str) -> _ParsedQuery:
        """Extract structured filters from natural language query."""
        normalized = query.lower().strip()
        # Split on whitespace and common punctuation
        tokens = re.findall(r"[a-z0-9_]+", normalized)

        parsed = _ParsedQuery(raw=normalized, tokens=tokens)

        for token in tokens:
            if token in _CATEGORY_KEYWORDS:
                cat = _CATEGORY_KEYWORDS[token]
                if cat not in parsed.categories:
                    parsed.categories.append(cat)
            if token in _STATUS_KEYWORDS:
                st = _STATUS_KEYWORDS[token]
                if st not in parsed.statuses:
                    parsed.statuses.append(st)
            if token in _SIM_STATUS_KEYWORDS:
                ss = _SIM_STATUS_KEYWORDS[token]
                if ss not in parsed.sim_statuses:
                    parsed.sim_statuses.append(ss)
            if token in _AUTH_KEYWORDS:
                at = _AUTH_KEYWORDS[token]
                if at not in parsed.auth_types:
                    parsed.auth_types.append(at)

        return parsed

    def _score_adapter(self, adapter: Adapter, parsed: _ParsedQuery) -> float:
        """Score an adapter against the parsed query."""
        score = 0.0
        name_lower = adapter.name.lower()
        desc_lower = (adapter.description or "").lower()
        cat_lower = adapter.category.lower()

        # Category match (high weight)
        if parsed.categories and cat_lower in parsed.categories:
            score += 10.0

        # Token matches in name/description
        for token in parsed.tokens:
            if token in name_lower:
                score += 3.0
            if token in desc_lower:
                score += 1.0

        # Auth type match on versions
        if parsed.auth_types:
            for version in adapter.versions:
                if version.auth_type in parsed.auth_types:
                    score += 5.0
                    break

        return score

    def _score_configuration(self, config: Configuration, parsed: _ParsedQuery) -> float:
        """Score a configuration against the parsed query."""
        score = 0.0
        name_lower = config.name.lower()

        # Status match
        if parsed.statuses and config.status in parsed.statuses:
            score += 10.0

        # Token matches in name
        for token in parsed.tokens:
            if token in name_lower:
                score += 3.0

        return score

    def _score_simulation(self, simulation: Simulation, parsed: _ParsedQuery) -> float:
        """Score a simulation against the parsed query."""
        score = 0.0

        # Simulation status match
        if parsed.sim_statuses and simulation.status in parsed.sim_statuses:
            score += 10.0

        # Generic "simulation" keyword boost
        if "simulation" in parsed.tokens or "simulations" in parsed.tokens:
            score += 5.0

        # Test type match
        if simulation.test_type:
            for token in parsed.tokens:
                if token in simulation.test_type:
                    score += 2.0

        return score

    async def search(self, query: str, tenant_id: str) -> SearchResponse:
        """Search integrations using natural language query."""
        parsed = self._parse_query(query)
        response = SearchResponse(query=query)

        # Search adapters (not tenant-scoped) — include category in filter.
        # Skip ILIKE pre-filter when auth_type signals are present: auth_type lives on
        # AdapterVersion (a joined table) and cannot be filtered here without a subquery,
        # so we fall back to loading all adapters and letting the scorer handle it.
        terms = parsed.tokens
        stmt = select(Adapter).options(selectinload(Adapter.versions))
        if terms and not parsed.auth_types:
            term_filter = or_(
                *[Adapter.name.ilike(f"%{term}%") for term in terms],
                *[Adapter.description.ilike(f"%{term}%") for term in terms],
                *[Adapter.category.ilike(f"%{term}%") for term in terms],
            )
            stmt = stmt.where(term_filter)
        stmt = stmt.limit(50)
        result = await self.db.execute(stmt)
        adapters = list(result.scalars().all())

        for adapter in adapters:
            score = self._score_adapter(adapter, parsed)
            if score > 0:
                auth_types = list({v.auth_type for v in adapter.versions})
                response.adapters.append(
                    SearchResult(
                        type="adapter",
                        id=adapter.id,
                        name=adapter.name,
                        score=score,
                        details={
                            "category": adapter.category,
                            "description": adapter.description,
                            "is_active": adapter.is_active,
                            "auth_types": auth_types,
                        },
                    )
                )

        # Search configurations (tenant-scoped)
        stmt = select(Configuration).where(Configuration.tenant_id == tenant_id)
        if terms:
            term_filter = or_(
                *[Configuration.name.ilike(f"%{term}%") for term in terms],
                *[Configuration.status.ilike(f"%{term}%") for term in terms],
            )
            stmt = stmt.where(term_filter)
        stmt = stmt.limit(50)
        result = await self.db.execute(stmt)
        configurations = list(result.scalars().all())

        for config in configurations:
            score = self._score_configuration(config, parsed)
            if score > 0:
                response.configurations.append(
                    SearchResult(
                        type="configuration",
                        id=config.id,
                        name=config.name,
                        score=score,
                        details={
                            "status": config.status,
                            "version": config.version,
                        },
                    )
                )

        # Search simulations (tenant-scoped)
        stmt = select(Simulation).where(Simulation.tenant_id == tenant_id)
        if terms:
            term_filter = or_(
                *[Simulation.status.ilike(f"%{term}%") for term in terms],
                *[Simulation.test_type.ilike(f"%{term}%") for term in terms],
            )
            stmt = stmt.where(term_filter)
        stmt = stmt.limit(50)
        result = await self.db.execute(stmt)
        simulations = list(result.scalars().all())

        for sim in simulations:
            score = self._score_simulation(sim, parsed)
            if score > 0:
                response.simulations.append(
                    SearchResult(
                        type="simulation",
                        id=sim.id,
                        name=f"Simulation {sim.id[:8]}",
                        score=score,
                        details={
                            "status": sim.status,
                            "test_type": sim.test_type,
                            "total_tests": sim.total_tests,
                            "passed_tests": sim.passed_tests,
                            "failed_tests": sim.failed_tests,
                        },
                    )
                )

        # Sort each group by score descending
        response.adapters.sort(key=lambda r: r.score, reverse=True)
        response.configurations.sort(key=lambda r: r.score, reverse=True)
        response.simulations.sort(key=lambda r: r.score, reverse=True)
        response.total = (
            len(response.adapters) + len(response.configurations) + len(response.simulations)
        )

        return response
