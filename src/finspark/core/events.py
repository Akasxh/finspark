"""Simple event system for decoupled communication between services."""

from collections import defaultdict
from collections.abc import Callable
from typing import Any

EventHandler = Callable[[dict[str, Any]], None]

_handlers: dict[str, list[EventHandler]] = defaultdict(list)


def on(event_type: str, handler: EventHandler) -> None:
    """Register an event handler."""
    _handlers[event_type].append(handler)


def emit(event_type: str, data: dict[str, Any]) -> None:
    """Emit an event to all registered handlers."""
    for handler in _handlers.get(event_type, []):
        try:
            handler(data)
        except Exception:
            pass  # Don't let handler failures propagate


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
