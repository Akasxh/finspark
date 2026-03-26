"""
ORM model registry — import everything here so Alembic autogenerate
can discover all tables via Base.metadata.
"""
from app.db.models.base import Base, TimestampMixin, SoftDeleteMixin  # noqa: F401
from app.db.models.tenant import Tenant  # noqa: F401
from app.db.models.adapter import Adapter, AdapterVersion  # noqa: F401
from app.db.models.integration import Integration  # noqa: F401
from app.db.models.configuration import Configuration, ConfigurationVersion  # noqa: F401
from app.db.models.hook import Hook  # noqa: F401
from app.db.models.mapping import FieldMapping  # noqa: F401
from app.db.models.audit_log import AuditLog  # noqa: F401
from app.db.models.test_result import TestResult  # noqa: F401

__all__ = [
    "Base",
    "TimestampMixin",
    "SoftDeleteMixin",
    "Tenant",
    "Adapter",
    "AdapterVersion",
    "Integration",
    "Configuration",
    "ConfigurationVersion",
    "Hook",
    "FieldMapping",
    "AuditLog",
    "TestResult",
]
