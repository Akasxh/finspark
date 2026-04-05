"""Structlog integration with PII masking processor."""

from __future__ import annotations

from typing import Any


def pii_masking_processor(
    logger: Any,  # noqa: ANN401
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Structlog processor that applies mask_pii to all string values in the event dict."""
    from finspark.core.security import mask_pii

    for key, value in event_dict.items():
        if isinstance(value, str):
            event_dict[key] = mask_pii(value)
    return event_dict


def configure_logging() -> None:
    """Configure structlog with PII masking if structlog is available.

    Falls back silently when structlog is not installed; stdlib logging
    is already protected by PIIMaskingFilter in main.py.
    """
    try:
        import structlog

        structlog.configure(
            processors=[
                pii_masking_processor,
                structlog.stdlib.add_log_level,
                structlog.stdlib.add_logger_name,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.dev.ConsoleRenderer(),
            ],
            wrapper_class=structlog.BoundLogger,
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
        )
    except ImportError:
        pass
