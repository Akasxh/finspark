"""API chaining executor for AdaptConfig endpoint dependency graphs.

Provides topological sorting of endpoints by ``depends_on``, template
substitution (``{{step.field}}``), dotted-path injection into request
dicts, and a simplified JSONPath extractor for response values.
"""

from __future__ import annotations

import copy
import logging
import re
from collections import defaultdict, deque
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


class ChainExecutionError(Exception):
    """Raised on cycle detection, unknown dependencies, or missing template values."""


# ---------------------------------------------------------------------------
# Topological sort
# ---------------------------------------------------------------------------

def topological_sort(endpoints: list[dict]) -> list[dict]:
    """Sort endpoints by ``depends_on``.  Raises on cycles or unknown deps."""
    id_map: dict[str, dict] = {}
    for ep in endpoints:
        ep_id = ep.get("id")
        if ep_id is None:
            raise ChainExecutionError(
                f"Endpoint missing 'id': {ep.get('path', '<unknown>')}"
            )
        if ep_id in id_map:
            raise ChainExecutionError(f"Duplicate endpoint id: {ep_id!r}")
        id_map[ep_id] = ep

    # Build adjacency list and in-degree map (Kahn's algorithm)
    in_degree: dict[str, int] = {eid: 0 for eid in id_map}
    dependents: dict[str, list[str]] = defaultdict(list)

    for ep in endpoints:
        deps = ep.get("depends_on") or []
        if isinstance(deps, str):
            deps = [deps]
        for dep in deps:
            if dep not in id_map:
                raise ChainExecutionError(
                    f"Endpoint {ep['id']!r} depends on unknown id {dep!r}"
                )
            dependents[dep].append(ep["id"])
            in_degree[ep["id"]] += 1

    queue: deque[str] = deque(eid for eid, deg in in_degree.items() if deg == 0)
    ordered: list[str] = []

    while queue:
        current = queue.popleft()
        ordered.append(current)
        for nxt in dependents[current]:
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                queue.append(nxt)

    if len(ordered) != len(id_map):
        remaining = set(id_map) - set(ordered)
        raise ChainExecutionError(
            f"Cycle detected among endpoints: {remaining}"
        )

    return [id_map[eid] for eid in ordered]


# ---------------------------------------------------------------------------
# Template substitution
# ---------------------------------------------------------------------------

_TEMPLATE_RE = re.compile(r"\{\{([\w]+(?:\.[\w]+)*)\}\}")


def substitute_template(template: str, context: dict[str, dict]) -> str:
    """Replace ``{{step_id.field}}`` tokens with values from *context*.

    Supports nested paths: ``{{auth.data.token}}`` resolves to
    ``context['auth']['data']['token']``.

    Raises :class:`ChainExecutionError` if a referenced step or field is
    missing.
    """

    def _replacer(match: re.Match) -> str:
        parts = match.group(1).split(".")
        step_id = parts[0]
        if step_id not in context:
            raise ChainExecutionError(
                f"Template references unknown step {step_id!r}"
            )
        value: Any = context[step_id]
        for part in parts[1:]:
            if isinstance(value, dict):
                if part not in value:
                    raise ChainExecutionError(
                        f"Field {'.'.join(parts)} not found in step {step_id!r} context"
                    )
                value = value[part]
            else:
                raise ChainExecutionError(
                    f"Field {'.'.join(parts)} not found in step {step_id!r} context"
                )
        return str(value)

    return _TEMPLATE_RE.sub(_replacer, template)


# ---------------------------------------------------------------------------
# Inject rules
# ---------------------------------------------------------------------------

def apply_inject(
    request_template: dict,
    inject_rules: dict[str, str],
    context: dict,
) -> dict:
    """Apply *inject_rules* to a copy of *request_template*.

    Each key in *inject_rules* is a dotted path into the request dict
    (e.g. ``headers.Authorization``, ``body.parent_txn_id``).  The value
    is a template string processed by :func:`substitute_template`.

    Returns a **new** dict -- does not mutate *request_template*.
    """
    result = copy.deepcopy(request_template)

    for dotted_path, tpl in inject_rules.items():
        value = substitute_template(tpl, context)
        parts = dotted_path.split(".")
        target = result
        for part in parts[:-1]:
            if part not in target:
                target[part] = {}
            target = target[part]
        target[parts[-1]] = value

    return result


# ---------------------------------------------------------------------------
# JSONPath-subset extractor
# ---------------------------------------------------------------------------

_BRACKET_RE = re.compile(r"^(\w+)\[(\d+)\]$")


def _resolve_path(data: Any, path_parts: list[str]) -> Any:
    """Walk *data* following dot/bracket segments.  Returns ``_MISSING``
    sentinel on failure."""
    current = data
    for part in path_parts:
        m = _BRACKET_RE.match(part)
        if m:
            field, idx = m.group(1), int(m.group(2))
            if not isinstance(current, dict) or field not in current:
                return _MISSING
            arr = current[field]
            if not isinstance(arr, list) or idx >= len(arr):
                return _MISSING
            current = arr[idx]
        else:
            if not isinstance(current, dict) or part not in current:
                return _MISSING
            current = current[part]
    return current


class _MissingSentinel:
    """Internal sentinel for missing JSONPath resolutions."""
_MISSING = _MissingSentinel()


def extract_from_response(
    response: dict,
    extract_rules: dict[str, str],
) -> dict:
    """Extract values from *response* using simplified JSONPath rules.

    Supported patterns:
      - ``$.field``
      - ``$.nested.field``
      - ``$.field[0]`` / ``$.field[0].sub``

    Missing fields are silently omitted (logged as warning).
    """
    extracted: dict[str, Any] = {}

    for key, jsonpath in extract_rules.items():
        path = jsonpath.lstrip("$").lstrip(".")
        if not path:
            logger.warning("Empty JSONPath for key %r -- skipping", key)
            continue
        parts = path.split(".")
        value = _resolve_path(response, parts)
        if isinstance(value, _MissingSentinel):
            logger.warning(
                "JSONPath %r resolved nothing in response -- skipping key %r",
                jsonpath,
                key,
            )
            continue
        extracted[key] = value

    return extracted


# ---------------------------------------------------------------------------
# Chain executor
# ---------------------------------------------------------------------------

async def execute_chain(
    endpoints: list[dict],
    call_fn: Callable[..., Awaitable[dict]],
) -> list[dict]:
    """Run endpoints in dependency order.

    *call_fn(endpoint, prepared_request) -> response* is injected so tests
    can provide a fake and the simulator can supply mock responses.

    Maintains a context dict keyed by endpoint ``id``.  Returns a list of
    ``{endpoint_id, request, response, extracted}`` dicts.
    """
    sorted_eps = topological_sort(endpoints)
    context: dict[str, dict] = {}
    results: list[dict] = []

    for ep in sorted_eps:
        ep_id = ep["id"]
        inject_rules = ep.get("inject") or {}
        extract_rules = ep.get("extract") or {}

        # Build request template from the endpoint (body/headers/path_params/query_params)
        request_template: dict[str, Any] = {}
        for section in ("body", "headers", "path_params", "query_params"):
            if section in ep:
                request_template[section] = copy.deepcopy(ep[section])

        # Apply inject rules
        prepared_request = (
            apply_inject(request_template, inject_rules, context)
            if inject_rules
            else copy.deepcopy(request_template)
        )

        response = await call_fn(ep, prepared_request)

        extracted = (
            extract_from_response(response, extract_rules) if extract_rules else {}
        )

        # Store extracted values (plus the full response) in context
        context[ep_id] = {**extracted, "_response": response}

        results.append(
            {
                "endpoint_id": ep_id,
                "request": prepared_request,
                "response": response,
                "extracted": extracted,
            }
        )

    return results
