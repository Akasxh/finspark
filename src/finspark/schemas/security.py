"""Schemas for API security inspection reports."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SecurityFinding(BaseModel):
    """A single security finding from the inspector."""

    category: str  # e.g. "API2_Broken_Authentication"
    severity: Literal["critical", "high", "medium", "low", "info"]
    title: str
    description: str
    recommendation: str
    location: str = ""  # JSONPath or endpoint path where the issue lives
    source: Literal["rule_based", "llm"] = "rule_based"


class SecurityReport(BaseModel):
    """Full security inspection report."""

    findings: list[SecurityFinding] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)  # severity -> count
    overall_risk: Literal["critical", "high", "medium", "low", "minimal"] = "minimal"
    scanned_at: datetime
    inspector_version: str = "1.0"
    llm_augmented: bool = False
    notes: list[str] = Field(default_factory=list)
