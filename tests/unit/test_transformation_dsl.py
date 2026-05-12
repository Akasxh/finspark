"""Unit tests for the safe pipe-chained transformation DSL.

Covers each allow-listed callable, chaining, invalid input, and injection
attempts. The DSL must reject anything not on the closed allow-list.
"""

from __future__ import annotations

import pytest

from finspark.services.transformation.dsl import (
    ALLOWED_CALLS,
    DSLError,
    apply_transformation,
    parse_expression,
    validate_expression,
)


# ---------------------------------------------------------------------------
# Empty / None expressions
# ---------------------------------------------------------------------------


class TestEmptyExpressions:
    def test_none_returns_value(self) -> None:
        assert apply_transformation("hello", None) == "hello"

    def test_empty_string_returns_value(self) -> None:
        assert apply_transformation(42, "") == 42

    def test_whitespace_returns_value(self) -> None:
        assert apply_transformation(3.14, "   \t\n") == 3.14

    def test_validate_none_ok(self) -> None:
        ok, err = validate_expression(None)
        assert ok and err is None

    def test_validate_empty_ok(self) -> None:
        ok, err = validate_expression("")
        assert ok and err is None


# ---------------------------------------------------------------------------
# Individual allow-listed calls
# ---------------------------------------------------------------------------


class TestIntCall:
    def test_int_from_string(self) -> None:
        assert apply_transformation("42", "int") == 42

    def test_int_from_float_string(self) -> None:
        assert apply_transformation("3.7", "int") == 3

    def test_int_from_int(self) -> None:
        assert apply_transformation(7, "int") == 7

    def test_int_from_bool(self) -> None:
        assert apply_transformation(True, "int") == 1
        assert apply_transformation(False, "int") == 0

    def test_int_failure(self) -> None:
        with pytest.raises(DSLError):
            apply_transformation("not_a_number", "int")


class TestFloatCall:
    def test_float_from_string(self) -> None:
        assert apply_transformation("3.14", "float") == 3.14

    def test_float_from_int(self) -> None:
        assert apply_transformation(5, "float") == 5.0

    def test_float_failure(self) -> None:
        with pytest.raises(DSLError):
            apply_transformation("xyz", "float")


class TestStrCall:
    def test_str_from_int(self) -> None:
        assert apply_transformation(42, "str") == "42"

    def test_str_from_float(self) -> None:
        assert apply_transformation(3.14, "str") == "3.14"

    def test_str_from_bool(self) -> None:
        assert apply_transformation(True, "str") == "True"


class TestUpperLower:
    def test_upper(self) -> None:
        assert apply_transformation("hello", "upper") == "HELLO"

    def test_lower(self) -> None:
        assert apply_transformation("HELLO", "lower") == "hello"

    def test_upper_on_int_coerces_to_str(self) -> None:
        assert apply_transformation(42, "upper") == "42"


class TestStripCall:
    def test_strip_default_whitespace(self) -> None:
        assert apply_transformation("  hello  ", "strip") == "hello"

    def test_strip_default_whitespace_with_empty_args(self) -> None:
        assert apply_transformation("  hello  ", "strip()") == "hello"

    def test_strip_with_chars(self) -> None:
        assert apply_transformation("000123000", 'strip("0")') == "123"

    def test_strip_with_chars_single_quoted(self) -> None:
        assert apply_transformation("xxhelloxx", "strip('x')") == "hello"

    def test_strip_with_empty_chars_falls_back_to_whitespace(self) -> None:
        # An empty literal should be treated as default-whitespace strip.
        assert apply_transformation("  hi  ", 'strip("")') == "hi"


class TestClampCall:
    def test_clamp_in_range(self) -> None:
        assert apply_transformation(50, "clamp(0, 100)") == 50

    def test_clamp_below(self) -> None:
        assert apply_transformation(-5, "clamp(0, 100)") == 0

    def test_clamp_above(self) -> None:
        assert apply_transformation(500, "clamp(0, 100)") == 100

    def test_clamp_float(self) -> None:
        assert apply_transformation(1.5, "clamp(0, 1.0)") == 1.0

    def test_clamp_requires_numeric_value(self) -> None:
        with pytest.raises(DSLError, match="numeric"):
            apply_transformation("not_a_number", "clamp(0, 100)")

    def test_clamp_inverted_bounds_rejected(self) -> None:
        with pytest.raises(DSLError, match="lo <= hi"):
            apply_transformation(5, "clamp(10, 1)")

    def test_clamp_wrong_arity(self) -> None:
        with pytest.raises(DSLError):
            apply_transformation(5, "clamp(10)")

    def test_clamp_requires_numeric_args(self) -> None:
        with pytest.raises(DSLError):
            apply_transformation(5, 'clamp("a", 10)')


class TestParseDateCall:
    def test_parse_date_dd_mm_yyyy(self) -> None:
        assert apply_transformation(
            "15/05/1990", 'parse_date("%d/%m/%Y")'
        ) == "1990-05-15"

    def test_parse_date_iso(self) -> None:
        assert apply_transformation(
            "1990-05-15", 'parse_date("%Y-%m-%d")'
        ) == "1990-05-15"

    def test_parse_date_requires_arg(self) -> None:
        with pytest.raises(DSLError):
            apply_transformation("1990-05-15", "parse_date")

    def test_parse_date_failure(self) -> None:
        with pytest.raises(DSLError, match="unable to parse"):
            apply_transformation("not-a-date", 'parse_date("%Y-%m-%d")')


class TestParseBoolCall:
    @pytest.mark.parametrize("v", ["true", "1", "yes", "on", "T", "Y", "TRUE"])
    def test_truthy(self, v: str) -> None:
        assert apply_transformation(v, "parse_bool") is True

    @pytest.mark.parametrize("v", ["false", "0", "no", "off", "F", "N", "FALSE"])
    def test_falsy(self, v: str) -> None:
        assert apply_transformation(v, "parse_bool") is False

    def test_bool_passthrough(self) -> None:
        assert apply_transformation(True, "parse_bool") is True
        assert apply_transformation(False, "parse_bool") is False

    def test_int_zero_is_false(self) -> None:
        assert apply_transformation(0, "parse_bool") is False

    def test_int_one_is_true(self) -> None:
        assert apply_transformation(1, "parse_bool") is True

    def test_parse_bool_failure(self) -> None:
        with pytest.raises(DSLError, match="cannot parse"):
            apply_transformation("maybe", "parse_bool")


# ---------------------------------------------------------------------------
# Pipe chaining
# ---------------------------------------------------------------------------


class TestPipeChaining:
    def test_str_pipe_upper(self) -> None:
        assert apply_transformation(123, "str | upper") == "123"

    def test_int_pipe_clamp(self) -> None:
        assert apply_transformation("5000", "int | clamp(0, 1000)") == 1000

    def test_int_pipe_clamp_high_bound(self) -> None:
        assert apply_transformation("5000", "int | clamp(0, 1000000)") == 5000

    def test_strip_pipe_int(self) -> None:
        assert apply_transformation("  42  ", "strip | int") == 42

    def test_strip_chars_pipe_int(self) -> None:
        assert apply_transformation("00042", 'strip("0") | int') == 42

    def test_upper_pipe_lower(self) -> None:
        assert apply_transformation("Hello", "upper | lower") == "hello"

    def test_long_chain(self) -> None:
        result = apply_transformation("  3.7  ", "strip | float | int | clamp(0, 5)")
        assert result == 3

    def test_extra_whitespace_around_pipes(self) -> None:
        assert apply_transformation("hi", "  upper   |   lower  ") == "hi"


# ---------------------------------------------------------------------------
# Rejection: injection attempts and unknown identifiers
# ---------------------------------------------------------------------------


class TestRejection:
    def test_reject_dunder_import(self) -> None:
        with pytest.raises(DSLError, match="Unknown transformation"):
            apply_transformation("x", "__import__('os')")

    def test_reject_eval(self) -> None:
        with pytest.raises(DSLError, match="Unknown transformation"):
            apply_transformation("x", "eval('1+1')")

    def test_reject_exec(self) -> None:
        with pytest.raises(DSLError, match="Unknown transformation"):
            apply_transformation("x", "exec('pass')")

    def test_reject_compile(self) -> None:
        with pytest.raises(DSLError, match="Unknown transformation"):
            apply_transformation("x", "compile('x', '', 'exec')")

    def test_reject_os_system(self) -> None:
        # Contains a '.' which is not in the DSL alphabet at all.
        with pytest.raises(DSLError):
            apply_transformation("x", "os.system('rm -rf /')")

    def test_reject_attribute_access(self) -> None:
        with pytest.raises(DSLError):
            apply_transformation("x", "value.__class__")

    def test_reject_method_call_on_value(self) -> None:
        with pytest.raises(DSLError):
            apply_transformation("x", "value.upper()")

    def test_reject_getattr(self) -> None:
        # Rejected for any of: unknown identifier, illegal arg type, illegal chain.
        with pytest.raises(DSLError):
            apply_transformation("x", "getattr(value, 'upper')()")

    def test_reject_lambda(self) -> None:
        with pytest.raises(DSLError):
            apply_transformation("x", "lambda x: x")

    def test_reject_arithmetic(self) -> None:
        with pytest.raises(DSLError):
            apply_transformation(1, "1 + 1")

    def test_reject_list_literal(self) -> None:
        with pytest.raises(DSLError):
            apply_transformation("x", "[1, 2, 3]")

    def test_reject_dict_literal(self) -> None:
        with pytest.raises(DSLError):
            apply_transformation("x", "{'a': 1}")

    def test_reject_string_concat(self) -> None:
        with pytest.raises(DSLError):
            apply_transformation("x", "'a' + 'b'")

    def test_reject_unknown_identifier(self) -> None:
        with pytest.raises(DSLError, match="Unknown transformation"):
            apply_transformation("x", "foo()")

    def test_reject_unknown_identifier_no_parens(self) -> None:
        with pytest.raises(DSLError, match="Unknown transformation"):
            apply_transformation("x", "foo")

    def test_reject_trailing_pipe(self) -> None:
        with pytest.raises(DSLError):
            apply_transformation("x", "upper |")

    def test_reject_leading_pipe(self) -> None:
        with pytest.raises(DSLError):
            apply_transformation("x", "| upper")

    def test_reject_double_pipe(self) -> None:
        with pytest.raises(DSLError):
            apply_transformation("x", "upper || lower")

    def test_reject_unterminated_string(self) -> None:
        with pytest.raises(DSLError, match="Unterminated"):
            apply_transformation("x", 'strip("abc')

    def test_reject_unbalanced_paren(self) -> None:
        with pytest.raises(DSLError):
            apply_transformation("x", "clamp(0, 100")


# ---------------------------------------------------------------------------
# parse_expression / validate_expression public surface
# ---------------------------------------------------------------------------


class TestParsePublicAPI:
    def test_parse_returns_calls(self) -> None:
        calls = parse_expression("int | clamp(0, 100)")
        assert len(calls) == 2
        assert calls[0].name == "int"
        assert calls[0].args == ()
        assert calls[1].name == "clamp"
        assert calls[1].args == (0, 100)

    def test_validate_ok(self) -> None:
        ok, err = validate_expression("str | upper")
        assert ok and err is None

    def test_validate_fail(self) -> None:
        ok, err = validate_expression("eval('1+1')")
        assert not ok
        assert err is not None and "Unknown transformation" in err


# ---------------------------------------------------------------------------
# Allow-list invariants
# ---------------------------------------------------------------------------


class TestAllowListInvariants:
    def test_allow_list_exact(self) -> None:
        expected = {
            "int", "float", "str", "upper", "lower",
            "strip", "clamp", "parse_date", "parse_bool",
        }
        assert set(ALLOWED_CALLS) == expected

    def test_no_eval_or_compile_in_source(self) -> None:
        """Smoke check: the DSL module text must not perform dynamic execution.

        We tokenise the module file and ensure no `eval(`, `exec(`, `compile(`,
        or `__import__` callsite exists in the actual code (docstring mentions
        are excluded by checking for the open-paren).
        """
        import inspect

        from finspark.services.transformation import dsl as dsl_mod

        src = inspect.getsource(dsl_mod)
        # Strip docstring lines that begin with `"""` or contain doc markers.
        code_lines = []
        in_doc = False
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                in_doc = not in_doc
                continue
            if in_doc:
                continue
            # also drop inline comments
            if "#" in line:
                line = line.split("#", 1)[0]
            code_lines.append(line)
        code = "\n".join(code_lines)
        for forbidden in ("eval(", "exec(", "compile(", "__import__(", "getattr("):
            assert forbidden not in code, (
                f"Forbidden construct {forbidden!r} found in dsl.py code (outside docstrings)"
            )
