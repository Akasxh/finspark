"""Safe pipe-chained transformation DSL.

A tiny hand-rolled token parser. No use of ``eval``/``exec``/``compile``/
``__import__``/``getattr``. The grammar:

    expression  := pipeline
    pipeline    := call ( "|" call )*
    call        := IDENT ( "(" args? ")" )?
    args        := arg ( "," arg )*
    arg         := NUMBER | STRING

Only the identifiers in :data:`ALLOWED_CALLS` may appear. Anything else is
rejected at parse time with a :class:`DSLError`.

Allow-list:
    ``int``, ``float``, ``str``, ``upper``, ``lower``,
    ``strip(chars=" ")``, ``clamp(lo, hi)``, ``parse_date(fmt)``, ``parse_bool``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

__all__ = [
    "DSLError",
    "ALLOWED_CALLS",
    "apply_transformation",
    "validate_expression",
    "parse_expression",
]


class DSLError(ValueError):
    """Raised for any tokenisation, parse, or runtime error inside the DSL."""


# ---------------------------------------------------------------------------
# Lexer
# ---------------------------------------------------------------------------

# Token kinds
_T_IDENT = "IDENT"
_T_PIPE = "PIPE"
_T_LPAREN = "LPAREN"
_T_RPAREN = "RPAREN"
_T_COMMA = "COMMA"
_T_NUMBER = "NUMBER"
_T_STRING = "STRING"
_T_EOF = "EOF"


@dataclass(frozen=True)
class _Token:
    kind: str
    value: Any
    pos: int


def _is_ident_start(ch: str) -> bool:
    return ch.isalpha() or ch == "_"


def _is_ident_continue(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def _tokenize(expr: str) -> list[_Token]:
    tokens: list[_Token] = []
    i = 0
    n = len(expr)
    while i < n:
        ch = expr[i]
        if ch.isspace():
            i += 1
            continue
        if ch == "|":
            tokens.append(_Token(_T_PIPE, "|", i))
            i += 1
            continue
        if ch == "(":
            tokens.append(_Token(_T_LPAREN, "(", i))
            i += 1
            continue
        if ch == ")":
            tokens.append(_Token(_T_RPAREN, ")", i))
            i += 1
            continue
        if ch == ",":
            tokens.append(_Token(_T_COMMA, ",", i))
            i += 1
            continue
        if ch in ('"', "'"):
            # String literal — read until matching unescaped quote.
            quote = ch
            j = i + 1
            buf: list[str] = []
            while j < n and expr[j] != quote:
                if expr[j] == "\\" and j + 1 < n:
                    nxt = expr[j + 1]
                    # Minimal escape support: \\, \', \", \n, \t.
                    if nxt == "n":
                        buf.append("\n")
                    elif nxt == "t":
                        buf.append("\t")
                    elif nxt in ("\\", "'", '"'):
                        buf.append(nxt)
                    else:
                        # Unknown escape — keep literal.
                        buf.append("\\")
                        buf.append(nxt)
                    j += 2
                    continue
                buf.append(expr[j])
                j += 1
            if j >= n:
                raise DSLError(f"Unterminated string literal at position {i}")
            tokens.append(_Token(_T_STRING, "".join(buf), i))
            i = j + 1
            continue
        if ch.isdigit() or (ch == "-" and i + 1 < n and expr[i + 1].isdigit()):
            # Number literal — integer or float, possibly negative.
            j = i + 1
            saw_dot = False
            while j < n and (expr[j].isdigit() or (expr[j] == "." and not saw_dot)):
                if expr[j] == ".":
                    saw_dot = True
                j += 1
            raw = expr[i:j]
            num: int | float
            try:
                num = float(raw) if saw_dot else int(raw)
            except ValueError as exc:
                raise DSLError(f"Invalid number literal {raw!r} at position {i}") from exc
            tokens.append(_Token(_T_NUMBER, num, i))
            i = j
            continue
        if _is_ident_start(ch):
            j = i + 1
            while j < n and _is_ident_continue(expr[j]):
                j += 1
            tokens.append(_Token(_T_IDENT, expr[i:j], i))
            i = j
            continue
        raise DSLError(
            f"Unexpected character {ch!r} at position {i} (only allow-listed calls "
            f"chained with '|' are permitted)"
        )
    tokens.append(_Token(_T_EOF, "", n))
    return tokens


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Call:
    name: str
    args: tuple[Any, ...]
    pos: int


def _parse(tokens: list[_Token]) -> list[_Call]:
    """Parse the token stream into a sequence of calls (the pipeline)."""

    idx = 0

    def peek() -> _Token:
        return tokens[idx]

    def consume(kind: str) -> _Token:
        nonlocal idx
        tok = tokens[idx]
        if tok.kind != kind:
            raise DSLError(
                f"Expected {kind} but got {tok.kind} ({tok.value!r}) at position {tok.pos}"
            )
        idx += 1
        return tok

    def parse_call() -> _Call:
        nonlocal idx
        ident_tok = consume(_T_IDENT)
        name = str(ident_tok.value)
        args: list[Any] = []
        if peek().kind == _T_LPAREN:
            consume(_T_LPAREN)
            if peek().kind != _T_RPAREN:
                # at least one arg
                args.append(_parse_arg())
                while peek().kind == _T_COMMA:
                    consume(_T_COMMA)
                    args.append(_parse_arg())
            consume(_T_RPAREN)
        return _Call(name=name, args=tuple(args), pos=ident_tok.pos)

    def _parse_arg() -> Any:
        nonlocal idx
        tok = peek()
        if tok.kind == _T_NUMBER:
            idx += 1
            return tok.value
        if tok.kind == _T_STRING:
            idx += 1
            return tok.value
        raise DSLError(
            f"Only numeric and string literals are allowed as arguments "
            f"(got {tok.kind} {tok.value!r} at position {tok.pos})"
        )

    if peek().kind == _T_EOF:
        return []

    calls: list[_Call] = [parse_call()]
    while peek().kind == _T_PIPE:
        consume(_T_PIPE)
        calls.append(parse_call())
    consume(_T_EOF)
    return calls


# ---------------------------------------------------------------------------
# Allow-listed callables
# ---------------------------------------------------------------------------


_TRUTHY = {"true", "1", "yes", "on", "t", "y"}
_FALSY = {"false", "0", "no", "off", "f", "n"}


def _call_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip()
    try:
        return int(s)
    except ValueError:
        # tolerate float-looking strings
        return int(float(s))


def _call_float(value: Any) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    return float(str(value).strip())


def _call_str(value: Any) -> str:
    return str(value)


def _call_upper(value: Any) -> str:
    return str(value).upper()


def _call_lower(value: Any) -> str:
    return str(value).lower()


def _call_strip(value: Any, chars: str = " ") -> str:
    # Treat "" as whitespace strip (Python default) to avoid empty-strip surprises.
    return str(value).strip(chars if chars else None)


def _call_clamp(value: Any, lo: Any, hi: Any) -> Any:
    # Coerce numeric comparison only when value is numeric. Otherwise raise.
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise DSLError(
            f"clamp() requires a numeric value, got {type(value).__name__}"
        )
    if not isinstance(lo, (int, float)) or not isinstance(hi, (int, float)):
        raise DSLError("clamp(lo, hi) requires numeric bounds")
    if lo > hi:
        raise DSLError(f"clamp() bounds must satisfy lo <= hi (got lo={lo}, hi={hi})")
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def _call_parse_date(value: Any, fmt: str) -> str:
    if not isinstance(fmt, str):
        raise DSLError("parse_date(fmt) requires a string format")
    s = str(value).strip()
    try:
        return datetime.strptime(s, fmt).date().isoformat()
    except ValueError as exc:
        raise DSLError(f"parse_date: unable to parse {s!r} with format {fmt!r}") from exc


def _call_parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    s = str(value).strip().lower()
    if s in _TRUTHY:
        return True
    if s in _FALSY:
        return False
    raise DSLError(f"parse_bool: cannot parse {value!r}")


@dataclass(frozen=True)
class _CallSpec:
    fn: Callable[..., Any]
    arity: tuple[int, int]  # (min, max) explicit args excluding the piped value
    arg_kinds: tuple[str, ...]  # "number" | "string" — for the optional args


ALLOWED_CALLS: dict[str, _CallSpec] = {
    "int": _CallSpec(_call_int, (0, 0), ()),
    "float": _CallSpec(_call_float, (0, 0), ()),
    "str": _CallSpec(_call_str, (0, 0), ()),
    "upper": _CallSpec(_call_upper, (0, 0), ()),
    "lower": _CallSpec(_call_lower, (0, 0), ()),
    # strip: 0 or 1 string arg (chars).
    "strip": _CallSpec(_call_strip, (0, 1), ("string",)),
    # clamp(lo, hi): exactly 2 numeric args.
    "clamp": _CallSpec(_call_clamp, (2, 2), ("number", "number")),
    # parse_date(fmt): exactly 1 string arg.
    "parse_date": _CallSpec(_call_parse_date, (1, 1), ("string",)),
    "parse_bool": _CallSpec(_call_parse_bool, (0, 0), ()),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_expression(expr: str) -> list[_Call]:
    """Tokenise + parse + validate the expression. Raises DSLError on issues."""
    if expr is None:
        return []
    tokens = _tokenize(expr)
    calls = _parse(tokens)
    for call in calls:
        spec = ALLOWED_CALLS.get(call.name)
        if spec is None:
            raise DSLError(
                f"Unknown transformation {call.name!r} at position {call.pos}. "
                f"Allowed: {sorted(ALLOWED_CALLS)}"
            )
        n_args = len(call.args)
        lo, hi = spec.arity
        if n_args < lo or n_args > hi:
            raise DSLError(
                f"{call.name}() expects between {lo} and {hi} arguments, got {n_args}"
            )
        # Type-check each provided arg against the declared kind.
        for i, arg in enumerate(call.args):
            kind = spec.arg_kinds[i]
            if kind == "number" and not isinstance(arg, (int, float)):
                raise DSLError(
                    f"{call.name}() argument #{i + 1} must be a number, got {type(arg).__name__}"
                )
            if kind == "string" and not isinstance(arg, str):
                raise DSLError(
                    f"{call.name}() argument #{i + 1} must be a string, got {type(arg).__name__}"
                )
    return calls


def apply_transformation(value: Any, expr: str | None) -> Any:
    """Apply a pipe-chained transformation expression to ``value``.

    If ``expr`` is None, empty, or whitespace-only, returns ``value`` unchanged.
    """
    if expr is None:
        return value
    expr_stripped = expr.strip()
    if not expr_stripped:
        return value
    calls = parse_expression(expr_stripped)
    current = value
    for call in calls:
        spec = ALLOWED_CALLS[call.name]
        try:
            current = spec.fn(current, *call.args)
        except DSLError:
            raise
        except Exception as exc:
            raise DSLError(
                f"{call.name}() raised at position {call.pos}: {exc}"
            ) from exc
    return current


def validate_expression(expr: str | None) -> tuple[bool, str | None]:
    """Return ``(ok, error_message)``. Useful for UI/API validation."""
    try:
        parse_expression(expr or "")
    except DSLError as exc:
        return False, str(exc)
    return True, None
