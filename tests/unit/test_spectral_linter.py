"""Unit tests for the Spectral linter module."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from finspark.services.lint.spectral_linter import (
    _is_api_spec,
    _parse_spectral_output,
    lint_openapi_spec,
)


class TestIsApiSpec:
    def test_openapi_detected(self) -> None:
        assert _is_api_spec('openapi: "3.0.3"\ninfo:\n  title: Test')

    def test_swagger_detected(self) -> None:
        assert _is_api_spec('swagger: "2.0"\ninfo:\n  title: Test')

    def test_asyncapi_detected(self) -> None:
        assert _is_api_spec('asyncapi: "2.6.0"\ninfo:\n  title: Test')

    def test_random_yaml_not_detected(self) -> None:
        assert not _is_api_spec("name: my-config\nversion: 1.0")

    def test_empty_string(self) -> None:
        assert not _is_api_spec("")

    def test_json_format_openapi(self) -> None:
        assert _is_api_spec('{"openapi": "3.0.0", "info": {}}')

    def test_quoted_keys(self) -> None:
        assert _is_api_spec('"openapi": "3.0.3"')


class TestParseSpectralOutput:
    def test_empty_output(self) -> None:
        assert _parse_spectral_output("") == []
        assert _parse_spectral_output("not json") == []

    def test_single_error(self) -> None:
        output = json.dumps([{
            "code": "oas3-schema",
            "message": "Object must have required property",
            "severity": 0,
            "path": ["paths", "/test", "get"],
            "range": {"start": {"line": 5, "character": 2}, "end": {"line": 5, "character": 10}},
        }])
        findings = _parse_spectral_output(output)
        assert len(findings) == 1
        assert findings[0].code == "oas3-schema"
        assert findings[0].severity == "error"
        assert findings[0].path == "paths./test.get"
        assert findings[0].range == "5:2-5:10"

    def test_multi_severity(self) -> None:
        output = json.dumps([
            {"code": "err1", "message": "error", "severity": 0, "path": [], "range": {}},
            {"code": "warn1", "message": "warning", "severity": 1, "path": [], "range": {}},
            {"code": "info1", "message": "info", "severity": 2, "path": [], "range": {}},
            {"code": "hint1", "message": "hint", "severity": 3, "path": [], "range": {}},
        ])
        findings = _parse_spectral_output(output)
        assert len(findings) == 4
        assert findings[0].severity == "error"
        assert findings[1].severity == "warning"
        assert findings[2].severity == "info"
        assert findings[3].severity == "hint"

    def test_empty_array(self) -> None:
        assert _parse_spectral_output("[]") == []


class TestLintOpenapiSpec:
    @pytest.mark.asyncio
    async def test_not_an_api_spec(self) -> None:
        report = await lint_openapi_spec("name: test\nversion: 1")
        assert report.spectral_available is True
        assert len(report.findings) == 0

    @pytest.mark.asyncio
    async def test_spectral_not_installed(self) -> None:
        with patch(
            "finspark.services.lint.spectral_linter._check_spectral_available",
            new_callable=AsyncMock,
            return_value=False,
        ):
            report = await lint_openapi_spec('openapi: "3.0.3"\ninfo:\n  title: T')
        assert report.spectral_available is False
        assert len(report.findings) == 1
        assert report.findings[0].code == "spectral-unavailable"
        assert report.info_count == 1

    @pytest.mark.asyncio
    async def test_successful_lint_with_findings(self) -> None:
        spectral_output = json.dumps([
            {"code": "info-contact", "message": "Info object must have contact.", "severity": 1, "path": ["info"], "range": {"start": {"line": 1, "character": 0}, "end": {"line": 2, "character": 0}}},
            {"code": "oas3-api-servers", "message": "Must have servers.", "severity": 0, "path": [], "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}}},
        ])

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(spectral_output.encode(), b""))
        mock_proc.returncode = 1  # Spectral returns non-zero when findings exist

        with (
            patch(
                "finspark.services.lint.spectral_linter._check_spectral_available",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc),
        ):
            report = await lint_openapi_spec('openapi: "3.0.3"\ninfo:\n  title: Test')

        assert report.spectral_available is True
        assert len(report.findings) == 2
        assert report.error_count == 1
        assert report.warning_count == 1
        assert report.info_count == 0

    @pytest.mark.asyncio
    async def test_no_findings_clean_spec(self) -> None:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"[]", b""))
        mock_proc.returncode = 0

        with (
            patch(
                "finspark.services.lint.spectral_linter._check_spectral_available",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc),
        ):
            report = await lint_openapi_spec('openapi: "3.0.3"\ninfo:\n  title: Test')

        assert report.spectral_available is True
        assert len(report.findings) == 0
        assert report.error_count == 0

    @pytest.mark.asyncio
    async def test_json_format_param(self) -> None:
        """Verify that format='json' produces a .json temp file."""
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"[]", b""))
        mock_proc.returncode = 0

        with (
            patch(
                "finspark.services.lint.spectral_linter._check_spectral_available",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "finspark.services.lint.spectral_linter.asyncio.create_subprocess_exec",
                new_callable=AsyncMock,
                return_value=mock_proc,
            ) as mock_exec,
        ):
            await lint_openapi_spec('{"openapi": "3.0.0", "info": {}}', format="json")

        # The temp file path should end in .json
        call_args = mock_exec.call_args[0]
        assert call_args[2].endswith(".json")
