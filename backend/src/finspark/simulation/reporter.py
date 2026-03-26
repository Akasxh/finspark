"""
Test result reporting.

Produces structured SimulationReport summaries in multiple formats:
- `text_report(report)`    — human-readable terminal output
- `json_report(report)`    — JSON string for API / log ingestion
- `junit_xml(report)`      — JUnit-compatible XML for CI systems
- `print_report(report)`   — writes text_report to stdout

No external deps (xml.etree is stdlib).
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

from finspark.simulation.types import SimulationReport, StepResult, StepStatus


# ---------------------------------------------------------------------------
# ANSI colour helpers (degrade gracefully in non-TTY environments)
# ---------------------------------------------------------------------------

_ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "green": "\033[32m",
    "red": "\033[31m",
    "yellow": "\033[33m",
    "cyan": "\033[36m",
    "grey": "\033[90m",
}


def _c(text: str, *styles: str) -> str:
    prefix = "".join(_ANSI.get(s, "") for s in styles)
    return f"{prefix}{text}{_ANSI['reset']}" if prefix else text


_STATUS_COLOUR: dict[StepStatus, str] = {
    StepStatus.PASS: "green",
    StepStatus.FAIL: "red",
    StepStatus.ERROR: "red",
    StepStatus.SKIP: "yellow",
}


def _status_str(status: StepStatus) -> str:
    label = f"[{status.value.upper():5}]"
    return _c(label, _STATUS_COLOUR.get(status, "reset"), "bold")


# ---------------------------------------------------------------------------
# Text report
# ---------------------------------------------------------------------------


def text_report(report: SimulationReport, *, colour: bool = True) -> str:
    c = _c if colour else (lambda t, *_: t)

    lines: list[str] = []
    lines.append(c("=" * 72, "bold"))
    lines.append(c("  FinSpark Integration Simulation Report", "bold", "cyan"))
    lines.append(c("=" * 72, "bold"))

    lines.append(f"  Run ID      : {report.run_id}")
    lines.append(f"  Tenant      : {report.tenant_id}")
    lines.append(f"  Adapter     : {report.adapter_id}  v{report.adapter_version}")
    started = report.started_at.strftime("%Y-%m-%d %H:%M:%S UTC")
    lines.append(f"  Started     : {started}")
    duration = f"{report.total_duration_ms:.1f} ms"
    lines.append(f"  Duration    : {duration}")
    lines.append(f"  Sandbox     : {report.sandbox_id or 'n/a'}")
    lines.append("")

    # step table
    lines.append(c(f"  {'STEP':<36} {'STATUS':<10} {'MS':>8} {'ACCURACY':>10} VIOLATIONS", "bold"))
    lines.append(c("  " + "-" * 70, "grey"))
    for step in report.steps:
        acc = f"{step.field_accuracy_score * 100:.0f}%"
        viol = len(step.contract_violations)
        viol_str = c(f"{viol} violation{'s' if viol != 1 else ''}", "red") if viol else c("clean", "green")
        status_label = _status_str(step.status) if colour else f"[{step.status.value.upper():5}]"
        lines.append(
            f"  {step.step_name:<36} {status_label}   {step.duration_ms:>6.1f}    {acc:>8}  {viol_str}"
        )
        if step.error:
            lines.append(c(f"    ERROR: {step.error}", "red"))
        for cv in step.contract_violations:
            lines.append(c(f"    CONTRACT: {cv}", "yellow"))

    lines.append(c("  " + "-" * 70, "grey"))

    # summary line
    overall_label = _status_str(report.overall_status) if colour else f"[{report.overall_status.value.upper()}]"
    lines.append(
        f"\n  Overall   {overall_label}   "
        f"pass={report.pass_count}  fail={report.fail_count}  error={report.error_count}  "
        f"avg_accuracy={report.field_accuracy_avg * 100:.1f}%"
    )

    if report.rollback_triggered:
        lines.append(c(f"\n  ROLLBACK triggered: {report.rollback_reason}", "red", "bold"))

    lines.append(c("=" * 72, "bold"))
    return "\n".join(lines)


def print_report(report: SimulationReport) -> None:
    print(text_report(report))


# ---------------------------------------------------------------------------
# JSON report
# ---------------------------------------------------------------------------


def json_report(report: SimulationReport, *, indent: int = 2) -> str:
    """Serialise the full SimulationReport to a JSON string."""
    def _default(obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Not serialisable: {type(obj)}")

    return json.dumps(report.model_dump(), indent=indent, default=_default)


# ---------------------------------------------------------------------------
# JUnit XML
# ---------------------------------------------------------------------------


def junit_xml(report: SimulationReport) -> str:
    """
    Produce a JUnit-compatible XML string suitable for CI artefact upload.
    One <testsuite> per report, one <testcase> per step.
    """
    suite = ET.Element(
        "testsuite",
        name=f"{report.adapter_id}/{report.adapter_version}",
        tests=str(len(report.steps)),
        failures=str(report.fail_count),
        errors=str(report.error_count),
        time=f"{report.total_duration_ms / 1000:.3f}",
        timestamp=report.started_at.isoformat(),
        id=report.run_id,
    )

    # suite-level properties
    props = ET.SubElement(suite, "properties")
    for key, val in [
        ("tenant_id", report.tenant_id),
        ("adapter_id", report.adapter_id),
        ("adapter_version", report.adapter_version),
        ("sandbox_id", report.sandbox_id or ""),
        ("rollback_triggered", str(report.rollback_triggered)),
    ]:
        p = ET.SubElement(props, "property", name=key)
        p.set("value", val)

    for step in report.steps:
        tc = ET.SubElement(
            suite,
            "testcase",
            name=step.step_name,
            classname=f"{report.adapter_id}.{report.adapter_version}",
            time=f"{step.duration_ms / 1000:.3f}",
        )
        if step.status in (StepStatus.FAIL, StepStatus.ERROR):
            tag = "failure" if step.status == StepStatus.FAIL else "error"
            msg = step.error or "; ".join(step.contract_violations) or "unknown"
            failure = ET.SubElement(tc, tag, message=msg[:200])
            failure.text = _step_detail(step)
        elif step.status == StepStatus.SKIP:
            ET.SubElement(tc, "skipped")

        # system-out: full response for debugging
        sys_out = ET.SubElement(tc, "system-out")
        sys_out.text = json.dumps(
            {
                "status_code": step.status_code,
                "response": step.response_payload,
                "field_accuracies": [fa.model_dump() for fa in step.field_accuracies],
            },
            indent=2,
            default=str,
        )

    ET.indent(suite, space="  ")
    return ET.tostring(suite, encoding="unicode", xml_declaration=False)


def _step_detail(step: StepResult) -> str:
    parts = []
    if step.error:
        parts.append(f"Error: {step.error}")
    for cv in step.contract_violations:
        parts.append(f"Contract: {cv}")
    for fa in step.field_accuracies:
        if not fa.matched:
            parts.append(f"Field mismatch [{fa.field}]: expected={fa.expected!r} actual={fa.actual!r}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Version comparison report
# ---------------------------------------------------------------------------


def version_comparison_text(result: Any, *, colour: bool = True) -> str:
    """Format a VersionComparisonResult as readable text."""
    from finspark.simulation.types import VersionComparisonResult

    if not isinstance(result, VersionComparisonResult):
        raise TypeError("Expected VersionComparisonResult")

    c = _c if colour else (lambda t, *_: t)
    lines: list[str] = []
    lines.append(c("─" * 72, "grey"))
    lines.append(c("  Version Comparison Result", "bold", "cyan"))
    compat = c("COMPATIBLE", "green", "bold") if result.compatible else c("BREAKING", "red", "bold")
    lines.append(f"  Compatibility: {compat}")
    lines.append(f"  Latency delta: {result.latency_delta_ms:+.1f} ms (v2 - v1)")

    v1s = _status_str(result.v1_step.status) if colour else f"[{result.v1_step.status.value.upper()}]"
    v2s = _status_str(result.v2_step.status) if colour else f"[{result.v2_step.status.value.upper()}]"
    lines.append(f"  v1 status : {v1s}  ({result.v1_step.duration_ms:.1f} ms)")
    lines.append(f"  v2 status : {v2s}  ({result.v2_step.duration_ms:.1f} ms)")

    if result.fields_diverged:
        lines.append(c(f"\n  Diverged fields ({len(result.fields_diverged)}):", "yellow", "bold"))
        for f in result.fields_diverged:
            lines.append(c(f"    - {f}", "yellow"))

    for note in result.notes:
        lines.append(c(f"  NOTE: {note}", "grey"))

    lines.append(c("─" * 72, "grey"))
    return "\n".join(lines)
