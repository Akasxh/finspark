"""Simple event system for decoupled communication between services."""

import inspect
import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

EventHandler = Callable[[dict[str, Any]], None]

_handlers: dict[str, list[EventHandler]] = defaultdict(list)


def on(event_type: str, handler: EventHandler) -> None:
    """Register an event handler."""
    _handlers[event_type].append(handler)


async def emit(event_type: str, data: dict[str, Any]) -> None:
    """Emit an event to all registered handlers."""
    for handler in _handlers.get(event_type, []):
        try:
            result = handler(data)
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.exception("Event handler failed for %s", event_type)


def clear() -> None:
    """Clear all handlers (for testing)."""
    _handlers.clear()


# Standard event types
CONFIG_CREATED = "config.created"
CONFIG_UPDATED = "config.updated"
CONFIG_DEPLOYED = "config.deployed"
CONFIG_ROLLED_BACK = "config.rolled_back"
SIMULATION_STARTED = "simulation.started"
SIMULATION_COMPLETED = "simulation.completed"
DOCUMENT_PARSED = "document.parsed"
ADAPTER_DEPRECATED = "adapter.deprecated"
