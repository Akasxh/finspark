"""Unit tests for the API chaining executor."""

from __future__ import annotations

import pytest

from finspark.services.chain_executor import (
    ChainExecutionError,
    apply_inject,
    execute_chain,
    extract_from_response,
    substitute_template,
    topological_sort,
)

# ---------------------------------------------------------------------------
# topological_sort
# ---------------------------------------------------------------------------


class TestTopologicalSort:
    def test_topological_sort_simple(self) -> None:
        """A -> B -> C produces [A, B, C]."""
        endpoints = [
            {"id": "C", "path": "/c", "depends_on": "B"},
            {"id": "A", "path": "/a"},
            {"id": "B", "path": "/b", "depends_on": "A"},
        ]
        result = topological_sort(endpoints)
        ids = [ep["id"] for ep in result]
        assert ids.index("A") < ids.index("B") < ids.index("C")

    def test_topological_sort_diamond(self) -> None:
        """A -> B,C -> D (diamond)."""
        endpoints = [
            {"id": "A", "path": "/a"},
            {"id": "B", "path": "/b", "depends_on": "A"},
            {"id": "C", "path": "/c", "depends_on": "A"},
            {"id": "D", "path": "/d", "depends_on": ["B", "C"]},
        ]
        result = topological_sort(endpoints)
        ids = [ep["id"] for ep in result]
        assert ids.index("A") < ids.index("B")
        assert ids.index("A") < ids.index("C")
        assert ids.index("B") < ids.index("D")
        assert ids.index("C") < ids.index("D")

    def test_topological_sort_cycle_raises(self) -> None:
        endpoints = [
            {"id": "A", "path": "/a", "depends_on": "B"},
            {"id": "B", "path": "/b", "depends_on": "A"},
        ]
        with pytest.raises(ChainExecutionError, match="Cycle detected"):
            topological_sort(endpoints)

    def test_topological_sort_unknown_dep_raises(self) -> None:
        endpoints = [
            {"id": "A", "path": "/a", "depends_on": "Z"},
        ]
        with pytest.raises(ChainExecutionError, match="unknown id"):
            topological_sort(endpoints)


# ---------------------------------------------------------------------------
# substitute_template
# ---------------------------------------------------------------------------


class TestSubstituteTemplate:
    def test_substitute_template_simple(self) -> None:
        ctx = {"a": {"token": "xyz"}}
        assert substitute_template("{{a.token}}", ctx) == "xyz"

    def test_substitute_template_nested(self) -> None:
        ctx = {"a": {"data": {"access_token": "tok123"}}}
        assert substitute_template("{{a.data.access_token}}", ctx) == "tok123"

    def test_substitute_template_missing_step_raises(self) -> None:
        with pytest.raises(ChainExecutionError, match="unknown step"):
            substitute_template("{{missing.field}}", {})

    def test_substitute_template_missing_field_raises(self) -> None:
        ctx = {"a": {"token": "xyz"}}
        with pytest.raises(ChainExecutionError, match="not found"):
            substitute_template("{{a.nonexistent}}", ctx)


# ---------------------------------------------------------------------------
# apply_inject
# ---------------------------------------------------------------------------


class TestApplyInject:
    def test_apply_inject_headers(self) -> None:
        tpl: dict = {"headers": {}, "body": {}}
        rules = {"headers.Authorization": "Bearer {{auth.token}}"}
        ctx = {"auth": {"token": "abc123"}}
        result = apply_inject(tpl, rules, ctx)
        assert result["headers"]["Authorization"] == "Bearer abc123"
        # Original not mutated
        assert tpl["headers"] == {}

    def test_apply_inject_nested_body_path(self) -> None:
        tpl: dict = {"body": {"payment": {}}}
        rules = {"body.payment.parent_txn_id": "{{initiate.txn_id}}"}
        ctx = {"initiate": {"txn_id": "TXN-001"}}
        result = apply_inject(tpl, rules, ctx)
        assert result["body"]["payment"]["parent_txn_id"] == "TXN-001"


# ---------------------------------------------------------------------------
# extract_from_response
# ---------------------------------------------------------------------------


class TestExtractFromResponse:
    def test_extract_from_response_simple_path(self) -> None:
        resp = {"data": {"access_token": "tok", "expires_in": 3600}}
        rules = {"access_token": "$.data.access_token"}
        assert extract_from_response(resp, rules) == {"access_token": "tok"}

    def test_extract_from_response_array_index(self) -> None:
        resp = {"items": [{"id": "first"}, {"id": "second"}]}
        rules = {"first_id": "$.items[0].id"}
        assert extract_from_response(resp, rules) == {"first_id": "first"}

    def test_extract_from_response_missing_field_silent(self) -> None:
        resp = {"data": {"x": 1}}
        rules = {"missing": "$.data.nonexistent"}
        result = extract_from_response(resp, rules)
        assert result == {}


# ---------------------------------------------------------------------------
# execute_chain
# ---------------------------------------------------------------------------


class TestExecuteChain:
    @pytest.mark.asyncio
    async def test_execute_chain_passes_context(self) -> None:
        """Step A returns a token; step B injects it via template."""
        endpoints = [
            {
                "id": "auth",
                "path": "/oauth/token",
                "method": "POST",
                "extract": {"token": "$.access_token"},
            },
            {
                "id": "payment",
                "path": "/v1/payment",
                "method": "POST",
                "depends_on": "auth",
                "inject": {"headers.Authorization": "Bearer {{auth.token}}"},
                "headers": {},
                "body": {"amount": 100},
            },
        ]

        async def fake_call(
            endpoint: dict, prepared_request: dict
        ) -> dict:
            if endpoint["id"] == "auth":
                return {"access_token": "abc", "status": "success"}
            return {
                "status": "success",
                "received_auth": prepared_request.get("headers", {}).get(
                    "Authorization", ""
                ),
            }

        results = await execute_chain(endpoints, fake_call)
        assert len(results) == 2

        auth_result = results[0]
        assert auth_result["endpoint_id"] == "auth"
        assert auth_result["extracted"] == {"token": "abc"}

        payment_result = results[1]
        assert payment_result["endpoint_id"] == "payment"
        assert payment_result["request"]["headers"]["Authorization"] == "Bearer abc"
