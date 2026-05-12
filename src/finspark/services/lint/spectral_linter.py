"""Spectral-based OpenAPI/AsyncAPI linter.

Shells out to @stoplight/spectral-cli for canonical rule enforcement.
Falls back gracefully when Spectral is not installed.
"""

import asyncio
import json
import logging
import re
import tempfile
from pathlib import Path

from finspark.schemas.documents import LintFinding, LintReport

logger = logging.getLogger(__name__)

_OPENAPI_PATTERN = re.compile(r'["\']?(openapi|swagger)["\']?\s*:', re.MULTILINE | re.IGNORECASE)
_ASYNCAPI_PATTERN = re.compile(r'["\']?asyncapi["\']?\s*:', re.MULTILINE | re.IGNORECASE)


def _is_api_spec(text: str) -> bool:
    """Return True if the text looks like an OpenAPI or AsyncAPI spec."""
    return bool(_OPENAPI_PATTERN.search(text[:2000]) or _ASYNCAPI_PATTERN.search(text[:2000]))


async def _check_spectral_available() -> bool:
    """Return True if the spectral CLI is available on PATH."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "spectral", "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=10)
        return proc.returncode == 0
    except (FileNotFoundError, OSError, asyncio.TimeoutError):
        return False


def _parse_spectral_output(raw: str) -> list[LintFinding]:
    """Parse JSON output from spectral lint --format json."""
    try:
        items = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []

    findings: list[LintFinding] = []
    for item in items:
        severity_map = {0: "error", 1: "warning", 2: "info", 3: "hint"}
        severity = severity_map.get(item.get("severity", 2), "info")

        source_range = item.get("range", {})
        start = source_range.get("start", {})
        end = source_range.get("end", {})
        range_str = ""
        if start:
            range_str = f"{start.get('line', 0)}:{start.get('character', 0)}"
            if end:
                range_str += f"-{end.get('line', 0)}:{end.get('character', 0)}"

        path_parts = item.get("path", [])
        json_path = ".".join(str(p) for p in path_parts) if path_parts else ""

        findings.append(
            LintFinding(
                code=item.get("code", "unknown"),
                message=item.get("message", ""),
                severity=severity,
                path=json_path,
                range=range_str,
            )
        )
    return findings


async def lint_openapi_spec(spec_text: str, format: str = "yaml") -> LintReport:
    """Lint an OpenAPI/AsyncAPI spec using Spectral CLI.

    Args:
        spec_text: The raw spec content.
        format: File format hint ("yaml" or "json").

    Returns:
        A LintReport with findings, or a report indicating Spectral
        is unavailable / the input is not an API spec.
    """
    if not _is_api_spec(spec_text):
        return LintReport(
            findings=[],
            error_count=0,
            warning_count=0,
            info_count=0,
            spectral_available=True,
        )

    available = await _check_spectral_available()
    if not available:
        return LintReport(
            findings=[
                LintFinding(
                    code="spectral-unavailable",
                    message="Spectral linter not installed on this server",
                    severity="info",
                    path="",
                    range="",
                ),
            ],
            error_count=0,
            warning_count=0,
            info_count=1,
            spectral_available=False,
        )

    ext = ".json" if format == "json" else ".yaml"
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=ext, delete=False, prefix="spectral_"
        ) as tmp:
            tmp.write(spec_text)
            tmp_path = Path(tmp.name)

        proc = await asyncio.create_subprocess_exec(
            "spectral", "lint", str(tmp_path), "--format", "json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

        raw_output = stdout.decode("utf-8", errors="replace")
        findings = _parse_spectral_output(raw_output)

        error_count = sum(1 for f in findings if f.severity == "error")
        warning_count = sum(1 for f in findings if f.severity == "warning")
        info_count = sum(1 for f in findings if f.severity in ("info", "hint"))

        return LintReport(
            findings=findings,
            error_count=error_count,
            warning_count=warning_count,
            info_count=info_count,
            spectral_available=True,
        )
    except asyncio.TimeoutError:
        logger.warning("Spectral lint timed out")
        return LintReport(
            findings=[
                LintFinding(
                    code="spectral-timeout",
                    message="Spectral linting timed out after 30 seconds",
                    severity="warning",
                    path="",
                    range="",
                ),
            ],
            error_count=0,
            warning_count=1,
            info_count=0,
            spectral_available=True,
        )
    except Exception:
        logger.exception("Unexpected error during Spectral linting")
        return LintReport(
            findings=[],
            error_count=0,
            warning_count=0,
            info_count=0,
            spectral_available=True,
        )
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
