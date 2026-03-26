"""Abstract base for external integration adapters."""

from abc import ABC, abstractmethod
from typing import Any


class BaseAdapter(ABC):
    """All third-party integration adapters must implement this interface."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the upstream service is reachable."""
        ...

    @abstractmethod
    async def fetch(self, resource: str, **kwargs: Any) -> Any:
        """Fetch a resource from the upstream service."""
        ...
