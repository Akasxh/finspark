"""Custom logging filter that masks PII before log records are emitted."""

from __future__ import annotations

import logging

from finspark.core.security import mask_pii


class PIIMaskingFilter(logging.Filter):
    """Applies PII masking to log messages so sensitive data never reaches log sinks."""

    def filter(self, record: logging.LogRecord) -> bool:
        if hasattr(record, "msg") and isinstance(record.msg, str):
            record.msg = mask_pii(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: mask_pii(str(v)) if isinstance(v, str) else v for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    mask_pii(str(a)) if isinstance(a, str) else a for a in record.args
                )
        return True
