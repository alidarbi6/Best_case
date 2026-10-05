"""Expression + rule language compatible with the subset of KNIME used by the workflow.

Two entry points share one tokenizer / parser:

* :func:`evaluate_expression`  - KNIME *String Manipulation* / *Math Formula*
  (``strip(lowerCase(replaceChars($code4$, "\\"", "")))``, ``$duration$ * 24`` ...)
* :class:`RuleSet`            - KNIME *Rule Engine* / *Rule-based Row Filter / Splitter*
  (``$wellname$ LIKE "SPH*" => "SPH"``, ``TRUE => $des$`` ...)

Keeping the KNIME syntax means a rule that is edited in the KNIME dialog can be
pasted into ``config/rules.yaml`` unchanged.

Semantics worth knowing
-----------------------
* ``$col$`` is a column reference; ``"text"`` a string; numbers, ``TRUE``/``FALSE``.
* Comparisons with a missing value are *false* (rule does not fire).
* ``LIKE`` is a case-sensitive wildcard match over the whole string
  (``*`` = any sequence, ``?`` = one character).
* The first rule whose condition is true wins; rows matched by no rule get a missing value.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Sequence

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- tokenizer

_NUM_RE = re.compile(r"\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")
_ID_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_OPS = ["=>", "<=", ">=", "!=", "==", "&&", "||", "=", "<", ">", "+", "-", "*", "/", "%", "(", ")", ",", "!"]
_KEYWORDS = {"AND", "OR", "NOT", "LIKE", "MATCHES", "IN", "MISSING", "TRUE", "FALSE"}


class ExpressionError(ValueError):
    pass


@dataclass(frozen=True)
class Token:
    kind: str  # col | str | num | id | kw | op | end
    value: Any
    pos: int


def tokenize(text: str) -> list[Token]:
    tokens: list[Token] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
        elif c == "$":
            j = text.find("$", i + 1)
            if j < 0:
                raise ExpressionError(f"Unterminated column reference at {i}: {text!r}")
            tokens.append(Token("col", text[i + 1 : j], i))
            i = j + 1
        elif c == '"':
            j, buf = i + 1, []
            while j < n and text[j] != '"':
                if text[j] == "\\" and j + 1 < n:
                    buf.append(text[j + 1])
                    j += 2
                else:
                    buf.append(text[j])
                    j += 1
            if j >= n:
                raise ExpressionError(f"Unterminated string at {i}: {text!r}")
            tokens.append(Token("str", "".join(buf), i))
            i = j + 1
        elif c.isdigit() or (c == "." and i + 1 < n and text[i + 1].isdigit()):
            m = _NUM_RE.match(text, i)
            if not m:
                raise ExpressionError(f"Bad number at {i}: {text!r}")
            s = m.group(0)
            tokens.append(Token("num", float(s) if any(ch in s for ch in ".eE") else int(s), i))
            i = m.end()
        elif c.isalpha() or c == "_":
            m = _ID_RE.match(text, i)
            word = m.group(0)
            if word.upper() in _KEYWORDS:
                tokens.append(Token("kw", word.upper(), i))
            else:
                tokens.append(Token("id", word, i))
            i = m.end()
        else:
            for op in _OPS:
                if text.startswith(op, i):
                    tokens.append(Token("op", op, i))
                    i += len(op)
                    break
            else:
                raise ExpressionError(f"Unexpected character {c!r} at {i}: {text!r}")
    tokens.append(Token("end", None, n))
    return tokens


# --------------------------------------------------------------------------- parser
# AST nodes are plain tuples: ("col", name) ("lit", v) ("bin", op, a, b) ("not", a)
# ("missing", a) ("call", name, [args]) ("neg", a) ("in", a, [items])


class _Parser:
    def __init__(self, tokens: Sequence[Token], text: str):
        self.t = list(tokens)
        self.i = 0
        self.text = text

    # helpers
    def peek(self) -> Token:
        return self.t[self.i]

    def next(self) -> Token:
        tok = self.t[self.i]
        self.i += 1
        return tok

    def accept(self, kind: str, value: Any = None) -> Token | None:
        tok = self.peek()
        if tok.kind == kind and (value is None or tok.value == value):
            self.i += 1
            return tok
        return None

    def expect(self, kind: str, value: Any = None) -> Token:
        tok = self.accept(kind, value)
        if tok is None:
            got = self.peek()
            raise ExpressionError(f"Expected {value or kind} at {got.pos}, got {got.value!r}: {self.text!r}")
        return tok

    # grammar
    def parse(self):
        node = self.or_expr()
        if self.peek().kind != "end":
            raise ExpressionError(f"Unexpected {self.peek().value!r} at {self.peek().pos}: {self.text!r}")
        return node

    def or_expr(self):
        node = self.and_expr()
        while self.accept("kw", "OR") or self.accept("op", "||"):
            node = ("bin", "OR", node, self.and_expr())
        return node

    def and_expr(self):
        node = self.not_expr()
        while self.accept("kw", "AND") or self.accept("op", "&&"):
            node = ("bin", "AND", node, self.not_expr())
        return node

    def not_expr(self):
        if self.accept("kw", "NOT") or self.accept("op", "!"):
            return ("not", self.not_expr())
        return self.compare()

    def compare(self):
        left = self.additive()
        tok = self.peek()
        if tok.kind == "op" and tok.value in ("=", "==", "!=", "<", "<=", ">", ">="):
            self.next()
            op = "=" if tok.value == "==" else tok.value
            return ("bin", op, left, self.additive())
        if tok.kind == "kw" and tok.value in ("LIKE", "MATCHES"):
            self.next()
            return ("bin", tok.value, left, self.additive())
        if tok.kind == "kw" and tok.value == "IN":
            self.next()
            self.expect("op", "(")
            items = [self.additive()]
            while self.accept("op", ","):
                items.append(self.additive())
            self.expect("op", ")")
            return ("in", left, items)
        return left

    def additive(self):
        node = self.term()
        while True:
            tok = self.peek()
            if tok.kind == "op" and tok.value in ("+", "-"):
                self.next()
                node = ("bin", tok.value, node, self.term())
            else:
                return node

    def term(self):
        node = self.unary()
        while True:
            tok = self.peek()
            if tok.kind == "op" and tok.value in ("*", "/", "%"):
                self.next()
                node = ("bin", tok.value, node, self.unary())
            else:
                return node

    def unary(self):
        if self.accept("op", "-"):
            return ("neg", self.unary())
        if self.accept("kw", "MISSING"):
            return ("missing", self.unary())
        return self.primary()

    def primary(self):
        tok = self.next()
        if tok.kind == "col":
            return ("col", tok.value)
        if tok.kind in ("str", "num"):
            return ("lit", tok.value)
        if tok.kind == "kw" and tok.value in ("TRUE", "FALSE"):
            return ("lit", tok.value == "TRUE")
        if tok.kind == "op" and tok.value == "(":
            node = self.or_expr()
            self.expect("op", ")")
            return node
        if tok.kind == "id":
            self.expect("op", "(")
            args = []
            if not self.accept("op", ")"):
                args.append(self.or_expr())
                while self.accept("op", ","):
                    args.append(self.or_expr())
                self.expect("op", ")")
            return ("call", tok.value, args)
        raise ExpressionError(f"Unexpected {tok.value!r} at {tok.pos}: {self.text!r}")


def parse_expression(text: str):
    return _Parser(tokenize(text), text).parse()


# --------------------------------------------------------------------------- evaluation helpers


def _isna(x) -> Any:
    if isinstance(x, (pd.Series, pd.Index)):
        return x.isna()
    if x is None:
        return True
    try:
        return bool(pd.isna(x))
    except (TypeError, ValueError):
        return False


def wildcard_to_regex(pattern: str) -> str:
    """``*`` -> any sequence, ``?`` -> any single char, everything else literal."""
    out = []
    for ch in pattern:
        if ch == "*":
            out.append(".*")
        elif ch == "?":
            out.append(".")
        else:
            out.append(re.escape(ch))
    return "".join(out)


def like_mask(values: pd.Series, pattern: str, case_sensitive: bool = True) -> pd.Series:
    rx = re.compile(wildcard_to_regex(pattern), re.DOTALL | (0 if case_sensitive else re.IGNORECASE))
    return pd.Series(
        [bool(rx.fullmatch(str(v))) if not _isna(v) else False for v in values], index=values.index, dtype=bool
    )


def regex_mask(values: pd.Series, pattern: str, case_sensitive: bool = True) -> pd.Series:
    rx = re.compile(pattern, 0 if case_sensitive else re.IGNORECASE)
    return pd.Series(
        [bool(rx.fullmatch(str(v))) if not _isna(v) else False for v in values], index=values.index, dtype=bool
    )


def _as_bool(x, index) -> pd.Series | bool:
    if isinstance(x, pd.Series):
        return x.fillna(False).astype(bool)
    return bool(x) if not _isna(x) else False


# ---- scalar string / math functions (KNIME / Apache-commons semantics) ----


def _strip(s, chars=None):
    return s.strip(chars) if chars else s.strip()


def _capitalize(s, delimiters=None):
    """Apache ``WordUtils.capitalize``: upper-case the first char of every word."""
    delims = set(delimiters) if delimiters else set(" \t\n\r\f")
    out, cap = [], True
    for ch in s:
        if ch in delims:
            out.append(ch)
            cap = True
        elif cap:
            out.append(ch.upper())
            cap = False
        else:
            out.append(ch)
    return "".join(out)


def _replace_chars(s, search, repl):
    """Apache ``StringUtils.replaceChars``: char-by-char mapping; extra search chars are removed."""
    table = {}
    for i, ch in enumerate(search):
        table[ord(ch)] = repl[i] if i < len(repl) else None
    return s.translate(table)


def _substr(s, start, length=None):
    start = int(start)
    return s[start:] if length is None else s[start : start + int(length)]


_STRING_FUNCS: dict[str, Callable] = {
    "strip": _strip,
    "stripstart": lambda s, c=None: s.lstrip(c),
    "stripend": lambda s, c=None: s.rstrip(c),
    "lowercase": lambda s: s.lower(),
    "uppercase": lambda s: s.upper(),
    "capitalize": _capitalize,
    "replacechars": _replace_chars,
    "replace": lambda s, a, b: s.replace(a, b),
    "substr": _substr,
    "length": lambda s: len(s),
    "join": lambda *a: "".join(str(x) for x in a),
    "regexreplace": lambda s, pat, rep: re.sub(pat, rep, s),
    "string": lambda x: str(x),
}

_NUMERIC_FUNCS: dict[str, Callable] = {
    "floor": np.floor,
    "ceil": np.ceil,
    "abs": np.abs,
    "sqrt": np.sqrt,
    "round": np.round,
    "log": np.log,
    "exp": np.exp,
}


def _call(name: str, args: list):
    key = name.lower()
    if key == "if":
        cond, a, b = args
        if isinstance(cond, pd.Series):
            cond = cond.fillna(False).astype(bool)
            idx = cond.index
            a_s = a if isinstance(a, pd.Series) else pd.Series([a] * len(idx), index=idx)
            return a_s.where(cond, b if isinstance(b, pd.Series) else b)
        return a if cond else b
    if key in ("min", "max") and len(args) == 2:
        fn = np.minimum if key == "min" else np.maximum
        return fn(args[0], args[1])
    if key == "pow" and len(args) == 2:
        return np.power(args[0], args[1])
    if key in _NUMERIC_FUNCS:
        x = args[0]
        if isinstance(x, pd.Series):
            return pd.Series(_NUMERIC_FUNCS[key](x.astype(float).to_numpy()), index=x.index)
        return float(_NUMERIC_FUNCS[key](float(x)))
    if key in _STRING_FUNCS:
        fn = _STRING_FUNCS[key]
        series_args = [a for a in args if isinstance(a, pd.Series)]
        if not series_args:
            return None if any(_isna(a) for a in args) else fn(*args)
        idx = series_args[0].index
        cols = [a.tolist() if isinstance(a, pd.Series) else [a] * len(idx) for a in args]
        out = []
        for vals in zip(*cols):
            out.append(None if any(_isna(v) for v in vals) else fn(*(str(vals[0]) if i == 0 and not isinstance(vals[0], str) and key != "string" else v for i, v in enumerate(vals))))
        return pd.Series(out, index=idx, dtype=object).infer_objects()
    raise ExpressionError(f"Unknown function {name!r}")


class _Evaluator:
    def __init__(self, df: pd.DataFrame):
        self.df = df

    def ev(self, node):
        kind = node[0]
        if kind == "col":
            name = node[1]
            if name not in self.df.columns:
                raise ExpressionError(f"Column {name!r} not found; available: {list(self.df.columns)}")
            return self.df[name]
        if kind == "lit":
            return node[1]
        if kind == "neg":
            return -self.ev(node[1])
        if kind == "not":
            v = self.ev(node[1])
            v = _as_bool(v, self.df.index)
            return ~v if isinstance(v, pd.Series) else (not v)
        if kind == "missing":
            return _isna(self.ev(node[1]))
        if kind == "call":
            return _call(node[1], [self.ev(a) for a in node[2]])
        if kind == "in":
            left = self.ev(node[1])
            items = [self.ev(i) for i in node[2]]
            if isinstance(left, pd.Series):
                return left.isin(items).fillna(False)
            return left in items
        if kind == "bin":
            return self.binary(node[1], node[2], node[3])
        raise ExpressionError(f"Bad node {node!r}")

    def binary(self, op, a_node, b_node):
        a, b = self.ev(a_node), self.ev(b_node)
        if op in ("AND", "OR"):
            a, b = _as_bool(a, self.df.index), _as_bool(b, self.df.index)
            return (a & b) if op == "AND" else (a | b)
        if op in ("LIKE", "MATCHES"):
            if not isinstance(b, str):
                raise ExpressionError(f"{op} needs a constant pattern")
            fn = like_mask if op == "LIKE" else regex_mask
            if isinstance(a, pd.Series):
                return fn(a, b)
            return bool(fn(pd.Series([a]), b).iloc[0])
        if op in ("=", "!=", "<", "<=", ">", ">="):
            return self.compare(op, a, b)
        # arithmetic
        if op == "+" and (isinstance(a, str) or isinstance(b, str)):
            return _call("join", [a, b])
        if op == "+":
            return a + b
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if op == "/":
            return a / b
        if op == "%":
            return a % b
        raise ExpressionError(f"Unsupported operator {op}")

    def compare(self, op, a, b):
        import operator

        fn = {"=": operator.eq, "!=": operator.ne, "<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge}[op]
        a_na, b_na = _isna(a), _isna(b)
        if not isinstance(a, pd.Series) and not isinstance(b, pd.Series):
            return False if (a_na or b_na) else bool(fn(a, b))
        a_s = a if isinstance(a, pd.Series) else None
        b_s = b if isinstance(b, pd.Series) else None
        ref = a_s if a_s is not None else b_s
        try:
            res = fn(a, b)
        except TypeError:
            res = fn(a.astype(str) if a_s is not None else a, b.astype(str) if b_s is not None else b)
        res = pd.Series(res, index=ref.index) if not isinstance(res, pd.Series) else res
        valid = pd.Series(True, index=ref.index)
        if a_s is not None:
            valid &= ~a_s.isna()
        if b_s is not None:
            valid &= ~b_s.isna()
        if a_s is None and a_na or b_s is None and b_na:
            valid &= False
        return res.fillna(False).astype(bool) & valid


# --------------------------------------------------------------------------- public API


def evaluate_expression(df: pd.DataFrame, expression: str, convert_to_int: str | bool = False) -> pd.Series:
    """Evaluate a String-Manipulation / Math-Formula expression row-wise over *df*.

    ``convert_to_int`` may be ``False``, ``True``/``"round"`` or ``"trunc"``.
    """
    node = parse_expression(expression)
    res = _Evaluator(df).ev(node)
    if not isinstance(res, pd.Series):
        res = pd.Series([res] * len(df), index=df.index)
    if convert_to_int:
        mode = "round" if convert_to_int is True else convert_to_int
        vals = res.astype(float)
        vals = vals.round() if mode == "round" else np.trunc(vals)
        res = vals.astype("Int64")
    return res


class RuleSet:
    """Ordered ``condition => outcome`` rules (KNIME Rule Engine syntax)."""

    def __init__(self, rules: Iterable[str] | str):
        if isinstance(rules, str):
            rules = rules.splitlines()
        self.source: list[str] = []
        self.parsed: list[tuple[Any, Any]] = []
        for line in rules:
            stripped = line.strip()
            if not stripped or stripped.startswith("//"):
                continue
            self.source.append(stripped)
            self.parsed.append(self._parse_rule(stripped))

    @staticmethod
    def _parse_rule(line: str):
        tokens = tokenize(line)
        for idx, tok in enumerate(tokens):
            if tok.kind == "op" and tok.value == "=>":
                cond_tokens = tokens[:idx] + [Token("end", None, tok.pos)]
                out_tokens = tokens[idx + 1 :]
                cond = _Parser(cond_tokens, line).parse()
                outcome = _Parser(out_tokens, line).parse()
                return cond, outcome
        raise ExpressionError(f"Rule has no '=>': {line!r}")

    def evaluate(self, df: pd.DataFrame) -> pd.Series:
        """Return the outcome of the first matching rule per row (missing if none)."""
        n = len(df)
        values = np.empty(n, dtype=object)
        values[:] = None
        unassigned = np.ones(n, dtype=bool)
        ev = _Evaluator(df)
        for cond, outcome in self.parsed:
            if not unassigned.any():
                break
            c = _as_bool(ev.ev(cond), df.index)
            mask = (c.to_numpy() if isinstance(c, pd.Series) else np.full(n, bool(c))) & unassigned
            if not mask.any():
                continue
            out = ev.ev(outcome)
            if isinstance(out, pd.Series):
                values[mask] = out.to_numpy(dtype=object)[mask]
            else:
                values[mask] = out
            unassigned &= ~mask
        return pd.Series(values, index=df.index).infer_objects()

    def matches(self, df: pd.DataFrame) -> pd.Series:
        """Boolean mask of rows whose outcome is ``TRUE`` (Rule-based Row Filter / Splitter)."""
        res = self.evaluate(df)
        return res.map(lambda v: v is True or (isinstance(v, (bool, np.bool_)) and bool(v))).astype(bool)

    def __len__(self) -> int:
        return len(self.parsed)
