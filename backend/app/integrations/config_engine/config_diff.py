"""
ConfigDiffEngine — structural diff between two integration configs.

Produces a ConfigDiff containing:
  - additions    : keys present in new but not old
  - deletions    : keys present in old but not new
  - modifications: keys present in both but with changed values
  - unchanged    : keys with identical values (optional, off by default)

Nested dicts are recursively diffed.  Lists are compared element-wise;
structural list changes (reorder, insert, delete) are reported as a
single modification with a human-readable summary.

Usage::

    engine = ConfigDiffEngine()
    diff = engine.diff(old_config, new_config)
    print(diff.summary())
    print(diff.to_json())
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enums / Data classes
# ---------------------------------------------------------------------------

class DiffOp(str, Enum):
    ADDED = "added"
    DELETED = "deleted"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"


@dataclass
class DiffEntry:
    """Single diff record for one key path."""

    path: str           # dot-separated key path, e.g. "address.city"
    op: DiffOp
    old_value: Any = None
    new_value: Any = None
    # Human-readable description for complex changes (list diffs, type changes)
    description: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "op": self.op.value,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "description": self.description,
        }


@dataclass
class ConfigDiff:
    """Aggregated diff result."""

    additions: list[DiffEntry] = field(default_factory=list)
    deletions: list[DiffEntry] = field(default_factory=list)
    modifications: list[DiffEntry] = field(default_factory=list)
    unchanged: list[DiffEntry] = field(default_factory=list)

    @property
    def all_entries(self) -> list[DiffEntry]:
        return self.additions + self.deletions + self.modifications + self.unchanged

    @property
    def has_changes(self) -> bool:
        return bool(self.additions or self.deletions or self.modifications)

    def summary(self) -> str:
        lines = [
            f"Config diff: +{len(self.additions)} added, "
            f"-{len(self.deletions)} deleted, "
            f"~{len(self.modifications)} modified, "
            f"={len(self.unchanged)} unchanged",
        ]
        if self.additions:
            lines.append("\nADDED:")
            for e in self.additions:
                lines.append(f"  + {e.path} = {_fmt(e.new_value)}")
        if self.deletions:
            lines.append("\nDELETED:")
            for e in self.deletions:
                lines.append(f"  - {e.path} (was {_fmt(e.old_value)})")
        if self.modifications:
            lines.append("\nMODIFIED:")
            for e in self.modifications:
                desc = f"  ~ {e.path}: {_fmt(e.old_value)} → {_fmt(e.new_value)}"
                if e.description:
                    desc += f"  [{e.description}]"
                lines.append(desc)
        return "\n".join(lines)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(
            {
                "has_changes": self.has_changes,
                "summary": {
                    "added": len(self.additions),
                    "deleted": len(self.deletions),
                    "modified": len(self.modifications),
                    "unchanged": len(self.unchanged),
                },
                "additions": [e.as_dict() for e in self.additions],
                "deletions": [e.as_dict() for e in self.deletions],
                "modifications": [e.as_dict() for e in self.modifications],
                "unchanged": [e.as_dict() for e in self.unchanged],
            },
            indent=indent,
            ensure_ascii=False,
            default=str,
        )

    def as_patch(self) -> dict[str, Any]:
        """
        Return a JSON-Patch-inspired dict (RFC 6902 inspired, simplified).
        Suitable for audit logs / change records.
        """
        ops: list[dict[str, Any]] = []
        for e in self.additions:
            ops.append({"op": "add", "path": f"/{e.path.replace('.', '/')}", "value": e.new_value})
        for e in self.deletions:
            ops.append({"op": "remove", "path": f"/{e.path.replace('.', '/')}"})
        for e in self.modifications:
            ops.append({
                "op": "replace",
                "path": f"/{e.path.replace('.', '/')}",
                "from": e.old_value,
                "value": e.new_value,
            })
        return {"patch": ops, "patch_count": len(ops)}


# ---------------------------------------------------------------------------
# ConfigDiffEngine
# ---------------------------------------------------------------------------

class ConfigDiffEngine:
    """
    Compare two config dicts recursively and emit a ConfigDiff.

    Parameters
    ----------
    include_unchanged:
        Include unchanged keys in the diff output (default False).
    sensitive_fields:
        Field paths whose values are masked in the diff output
        (e.g. api_key, client_secret) — values replaced with "***".
    """

    def __init__(
        self,
        include_unchanged: bool = False,
        sensitive_fields: set[str] | None = None,
    ) -> None:
        self._include_unchanged = include_unchanged
        self._sensitive = sensitive_fields or {
            "api_key", "client_secret", "key_secret", "webhook_secret",
            "gstn_password", "app_key", "gstn_password",
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def diff(
        self,
        old: dict[str, Any],
        new: dict[str, Any],
    ) -> ConfigDiff:
        """Recursively diff two config dicts."""
        result = ConfigDiff()
        self._diff_recursive(old, new, prefix="", result=result)
        return result

    def diff_generated(
        self,
        old_json: str,
        new_json: str,
    ) -> ConfigDiff:
        """Convenience: accept JSON strings and diff their config_data sections."""
        old_obj = json.loads(old_json)
        new_obj = json.loads(new_json)
        old_data = old_obj.get("config_data", old_obj)
        new_data = new_obj.get("config_data", new_obj)
        return self.diff(old_data, new_data)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _diff_recursive(
        self,
        old: Any,
        new: Any,
        prefix: str,
        result: ConfigDiff,
    ) -> None:
        if isinstance(old, dict) and isinstance(new, dict):
            all_keys = set(old) | set(new)
            for key in sorted(all_keys):
                path = f"{prefix}.{key}" if prefix else key
                if key not in old:
                    result.additions.append(DiffEntry(
                        path=path,
                        op=DiffOp.ADDED,
                        new_value=self._mask(path, new[key]),
                    ))
                elif key not in new:
                    result.deletions.append(DiffEntry(
                        path=path,
                        op=DiffOp.DELETED,
                        old_value=self._mask(path, old[key]),
                    ))
                else:
                    self._diff_recursive(old[key], new[key], path, result)
        elif isinstance(old, list) and isinstance(new, list):
            self._diff_lists(old, new, prefix, result)
        else:
            if old == new:
                if self._include_unchanged:
                    result.unchanged.append(DiffEntry(
                        path=prefix,
                        op=DiffOp.UNCHANGED,
                        old_value=self._mask(prefix, old),
                        new_value=self._mask(prefix, new),
                    ))
            else:
                type_note = ""
                if type(old) is not type(new):
                    type_note = f"type changed {type(old).__name__}→{type(new).__name__}"
                result.modifications.append(DiffEntry(
                    path=prefix,
                    op=DiffOp.MODIFIED,
                    old_value=self._mask(prefix, old),
                    new_value=self._mask(prefix, new),
                    description=type_note,
                ))

    def _diff_lists(
        self,
        old: list[Any],
        new: list[Any],
        path: str,
        result: ConfigDiff,
    ) -> None:
        if old == new:
            if self._include_unchanged:
                result.unchanged.append(DiffEntry(
                    path=path,
                    op=DiffOp.UNCHANGED,
                    old_value=old,
                    new_value=new,
                ))
            return

        len_old, len_new = len(old), len(new)
        if len_old != len_new:
            desc = f"list length {len_old}→{len_new}"
        else:
            changed_indices = [i for i, (a, b) in enumerate(zip(old, new)) if a != b]
            desc = f"elements changed at indices: {changed_indices}"

        result.modifications.append(DiffEntry(
            path=path,
            op=DiffOp.MODIFIED,
            old_value=old,
            new_value=new,
            description=desc,
        ))

    def _mask(self, path: str, value: Any) -> Any:
        # Check leaf key name
        leaf = path.split(".")[-1]
        if leaf in self._sensitive:
            return "***"
        return value


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, str) and len(value) > 60:
        return f"{value[:57]}..."
    return repr(value)
