"""
Integration Adapter Registry — plugin-based system for enterprise lending integrations.

Public surface:
    AdapterRegistry   — singleton registry; use get_registry() to access
    register_adapter  — decorator for registering adapter classes
    get_registry      — returns the global AdapterRegistry instance
    BaseAdapter       — abstract base all adapters must subclass

Concrete adapters (importable directly):
    CIBILAdapterV1 / V2
    KYCAdapterV1 / V2
    GSTAdapterV1
    PaymentGatewayAdapterV1
    SMSGatewayAdapterV1
"""

from app.integrations.registry.registry import AdapterRegistry, get_registry, register_adapter
from app.integrations.base import BaseAdapter

__all__ = [
    "AdapterRegistry",
    "BaseAdapter",
    "get_registry",
    "register_adapter",
]
