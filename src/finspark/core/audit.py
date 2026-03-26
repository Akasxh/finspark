"""Audit logging service."""

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from finspark.models.audit import AuditLog


class AuditService:
    """Creates immutable audit log entries for all configuration changes."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def log(
        self,
        tenant_id: str,
        actor: str,
        action: str,
        resource_type: str,
        resource_id: str,
        details: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuditLog:
        """Create an audit log entry."""
        entry = AuditLog(
            tenant_id=tenant_id,
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=json.dumps(details) if details else None,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(entry)
        await self.db.flush()
        return entry
