"""Generic relational building blocks equivalent to the KNIME nodes used by the workflow.

Every function is pure (returns a new DataFrame) and knows nothing about drilling.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Callable, Iterable, Iterator, Mapping, Sequence

import numpy as np
import pandas as pd

from .expr import RuleSet, like_mask, regex_mask
from .sorting import sort_dataframe


# --------------------------------------------------------------------------- column selection


@dataclass
class Select:
    """Column selection as in KNIME dialogs: an include list *or* an exclude list.

    ``Select()`` selects everything.  Names that do not exist are silently ignored
    (KNIME keeps stale names in dialogs too).
    """

    include: Sequence[str] | None = None
    exclude: Sequence[str] | None = None

    @classmethod
    def of(cls, spec: "Select | Mapping | Sequence[str] | None") -> "Select":
        if spec is None:
            return cls()
        if isinstance(spec, Select):
            return spec
        if isinstance(spec, Mapping):
            return cls(include=spec.get("include"), exclude=spec.get("exclude"))
        return cls(include=list(spec))

    def resolve(self, columns: Iterable[str]) -> list[str]:
        cols = list(columns)
        if self.include is not None:
            return [c for c in self.include if c in cols]
        if self.exclude is not None:
            ex = set(self.exclude)
            return [c for c in cols if c not in ex]
        return cols


# --------------------------------------------------------------------------- joiner


def join(
    left: pd.DataFrame,
    right: pd.DataFrame,
    left_on: Sequence[str],
    right_on: Sequence[str] | None = None,
    how: str = "inner",
    left_select: Select | Mapping | Sequence[str] | None = None,
    right_select: Select | Mapping | Sequence[str] | None = None,
    suffix: str = " (Right)",
    null_keys_match: bool = False,
) -> pd.DataFrame:
    """KNIME *Joiner* (match all criteria).

    * ``how`` is ``"inner"`` or ``"left"``.
    * Output = selected left columns + selected right columns; right columns whose
      name collides with a left output column get ``suffix`` appended.
    * Missing key values never match (SQL semantics) unless ``null_keys_match``.
    * Left row order is preserved.
    """
    right_on = list(right_on or left_on)
    left_on = list(left_on)
    if how not in ("inner", "left"):
        raise ValueError(f"unsupported join type {how!r}")
    for c in left_on:
        if c not in left.columns:
            raise KeyError(f"join: left column {c!r} missing (have {list(left.columns)})")
    for c in right_on:
        if c not in right.columns:
            raise KeyError(f"join: right column {c!r} missing (have {list(right.columns)})")

    left_cols = Select.of(left_select).resolve(left.columns)
    right_cols = Select.of(right_select).resolve(right.columns)
    out_right_names = {c: (c + suffix if c in left_cols else c) for c in right_cols}

    keys = [f"__k{i}__" for i in range(len(left_on))]
    L = left.reset_index(drop=True)
    R = right.reset_index(drop=True)
    lk = pd.DataFrame({k: L[c] for k, c in zip(keys, left_on)})
    rk = pd.DataFrame({k: R[c] for k, c in zip(keys, right_on)})
    if not null_keys_match:
        # make missing keys unique so that they cannot match each other
        for k in keys:
            lk[k] = _sentinel_missing(lk[k], "L")
            rk[k] = _sentinel_missing(rk[k], "R")
    lpart = pd.concat([lk, L[left_cols].reset_index(drop=True)], axis=1)
    rpart = pd.concat([rk, R[right_cols].rename(columns=out_right_names)], axis=1)
    merged = lpart.merge(rpart, on=keys, how=how, sort=False)
    # restore: drop key helpers, order = left cols then right cols
    return merged[left_cols + [out_right_names[c] for c in right_cols]].reset_index(drop=True)


def _sentinel_missing(s: pd.Series, tag: str) -> pd.Series:
    na = s.isna()
    if not na.any():
        return s
    s = s.astype(object)
    s[na] = [f"__missing_{tag}_{i}" for i in range(int(na.sum()))]
    return s


def cross_join(left: pd.DataFrame, right: pd.DataFrame, right_suffix: str = " (#1)") -> pd.DataFrame:
    """KNIME *Cross Joiner*."""
    r = right.rename(columns={c: c + right_suffix for c in right.columns if c in left.columns})
    return left.merge(r, how="cross")


# --------------------------------------------------------------------------- aggregation

AGGREGATIONS = ("Sum", "Minimum", "Maximum", "Mean", "Count", "First", "Last", "Concatenate")


@dataclass
class Agg:
    column: str
    method: str
    include_missing: bool = False
    out_name: str | None = None


def _format_value(v, ints_for_integral_floats: bool) -> str:
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return "?"
    if isinstance(v, (float, np.floating)):
        if ints_for_integral_floats and float(v).is_integer():
            return str(int(v))
        return repr(float(v))
    if isinstance(v, (np.integer,)):
        return str(int(v))
    return str(v)


def group_by(
    df: pd.DataFrame,
    by: Sequence[str],
    aggs: Sequence[Agg],
    *,
    name_policy: str = "keep",
    delimiter: str = ", ",
    integral_floats_as_int: bool = True,
) -> pd.DataFrame:
    """KNIME *GroupBy*.

    ``name_policy``: ``"keep"`` (Keep original name(s)) or ``"method"``
    (``Sum(duration)``-style, i.e. *Aggregation method (column name)*).
    Group keys that are missing form their own group.  Group order = first appearance.
    """
    by = list(by)
    if not aggs:
        return df[by].drop_duplicates().reset_index(drop=True)
    if not by:
        raise ValueError("group_by needs at least one grouping column")
    grouped = df.groupby(by, dropna=False, sort=False)
    columns: dict[str, pd.Series] = {}
    for a in aggs:
        method = a.method.split("_V")[0]  # tolerate KNIME ids such as "Sum_V2.5.2"
        if method == "Concatenate":
            def fmt(s, inc=a.include_missing):
                return delimiter.join(
                    _format_value(v, integral_floats_as_int) for v in (s if inc else s.dropna())
                )

            vals = grouped[a.column].agg(fmt)
        elif method in ("Sum", "Minimum", "Maximum", "Mean", "Count", "First", "Last"):
            how = {"Sum": "sum", "Minimum": "min", "Maximum": "max", "Mean": "mean", "Count": "count",
                   "First": "first", "Last": "last"}[method]
            vals = grouped[a.column].agg(how)
        else:
            raise ValueError(f"unknown aggregation {a.method!r}")
        name = a.out_name or (f"{method}({a.column})" if name_policy == "method" else a.column)
        columns[name] = vals
    return pd.DataFrame(columns).reset_index()


def distinct(df: pd.DataFrame, by: Sequence[str]) -> pd.DataFrame:
    """GroupBy with no aggregation: distinct combinations of *by* (first-appearance order)."""
    return group_by(df, by, [])


# --------------------------------------------------------------------------- duplicate row filter


def duplicate_row_filter(
    df: pd.DataFrame,
    group_cols: Sequence[str] | None = None,
    *,
    reference: str | None = None,
    selection: str = "FIRST",
    remove_duplicates: bool = True,
    flag_column: str | None = "Duplicate Status",
    exclude_cols: Sequence[str] = (),
) -> pd.DataFrame:
    """KNIME *Duplicate Row Filter*.

    Rows with equal values in ``group_cols`` (default: all columns except
    ``exclude_cols``; missing == missing) form a group.  Per group one row is
    *chosen* (FIRST / LAST / MINIMUM / MAXIMUM of ``reference``; ties -> first).
    With ``remove_duplicates`` only chosen + unique rows survive and no flag column is
    added; otherwise a flag column holds ``unique`` / ``chosen`` / ``duplicate``.
    Row order is retained.
    """
    if df.empty:
        out = df.copy()
        if not remove_duplicates and flag_column:
            out[flag_column] = pd.Series(dtype=object)
        return out
    cols = list(group_cols) if group_cols else [c for c in df.columns if c not in set(exclude_cols)]
    gid = df.groupby(cols, dropna=False, sort=False).ngroup().to_numpy()
    size = pd.Series(gid).map(pd.Series(gid).value_counts()).to_numpy()
    sel = selection.upper()
    pos = np.arange(len(df))
    if sel == "FIRST":
        rank = pd.Series(pos).groupby(gid).rank(method="first").to_numpy()
    elif sel == "LAST":
        rank = pd.Series(-pos).groupby(gid).rank(method="first").to_numpy()
    elif sel in ("MINIMUM", "MAXIMUM"):
        if reference is None:
            raise ValueError("MINIMUM/MAXIMUM selection needs a reference column")
        ref = df[reference].reset_index(drop=True)
        rank = ref.groupby(gid).rank(method="first", ascending=(sel == "MINIMUM"), na_option="bottom").to_numpy()
    else:
        raise ValueError(f"unknown row selection {selection!r}")
    chosen = rank == 1
    if remove_duplicates:
        return df[chosen | (size == 1)].reset_index(drop=True)
    flag = np.where(size == 1, "unique", np.where(chosen, "chosen", "duplicate"))
    out = df.reset_index(drop=True).copy()
    out[flag_column or "Duplicate Status"] = flag
    return out


# --------------------------------------------------------------------------- row filter


@dataclass
class Condition:
    column: str
    operator: str  # EQ NEQ LT LE GT GE WILDCARD REGEX IS_MISSING IS_NOT_MISSING IN
    value: object = None
    case_sensitive: bool = True


@dataclass
class RowFilterSpec:
    """Declarative form of the KNIME *Row Filter* (data-value based)."""

    conditions: list[Condition] = field(default_factory=list)
    match: str = "all"  # all | any
    mode: str = "matching"  # matching | non_matching
    enabled: bool = True
    name: str = ""

    @classmethod
    def from_dict(cls, d: Mapping) -> "RowFilterSpec":
        conds = [
            Condition(
                column=c["column"],
                operator=str(c["operator"]).upper(),
                value=c.get("value"),
                case_sensitive=bool(c.get("case_sensitive", True)),
            )
            for c in d.get("conditions", [])
        ]
        return cls(
            conditions=conds,
            match=str(d.get("match", "all")).lower(),
            mode=str(d.get("mode", "matching")).lower(),
            enabled=bool(d.get("enabled", True)),
            name=str(d.get("name", "")),
        )


def condition_mask(df: pd.DataFrame, c: Condition) -> pd.Series:
    s = df[c.column]
    op = c.operator
    if op == "IS_MISSING":
        return s.isna()
    if op == "IS_NOT_MISSING":
        return s.notna()
    valid = s.notna()
    if op == "WILDCARD":
        return like_mask(s, str(c.value), c.case_sensitive)
    if op == "REGEX":
        return regex_mask(s, str(c.value), c.case_sensitive)
    if op == "IN":
        vals = list(c.value)
        if not c.case_sensitive:
            low = {str(v).lower() for v in vals}
            return s.map(lambda v: str(v).lower() in low if not pd.isna(v) else False).astype(bool)
        return s.isin(vals) & valid
    if op in ("EQ", "NEQ") and isinstance(c.value, str) and not c.case_sensitive:
        eq = s.map(lambda v: str(v).lower() == c.value.lower() if not pd.isna(v) else False).astype(bool)
        return eq if op == "EQ" else (~eq & valid)
    if op in ("EQ", "NEQ", "LT", "LE", "GT", "GE"):
        val = c.value
        if not isinstance(val, str) and not pd.api.types.is_numeric_dtype(s) and val is not None:
            pass
        try:
            res = {"EQ": s == val, "NEQ": s != val, "LT": s < val, "LE": s <= val, "GT": s > val, "GE": s >= val}[op]
        except TypeError:
            sv = s.astype(str)
            res = {"EQ": sv == str(val), "NEQ": sv != str(val), "LT": sv < str(val), "LE": sv <= str(val),
                   "GT": sv > str(val), "GE": sv >= str(val)}[op]
        return res.fillna(False).astype(bool) & valid
    raise ValueError(f"unknown operator {op!r}")


def row_filter(df: pd.DataFrame, spec: RowFilterSpec | Mapping) -> pd.DataFrame:
    """Apply a :class:`RowFilterSpec`; a disabled / empty spec returns the input unchanged."""
    if not isinstance(spec, RowFilterSpec):
        spec = RowFilterSpec.from_dict(spec)
    if not spec.enabled or not spec.conditions:
        return df
    masks = [condition_mask(df, c) for c in spec.conditions]
    combined = masks[0]
    for m in masks[1:]:
        combined = (combined & m) if spec.match == "all" else (combined | m)
    keep = combined if spec.mode == "matching" else ~combined
    return df[keep].reset_index(drop=True)


# --------------------------------------------------------------------------- misc nodes


def concatenate(frames: Sequence[pd.DataFrame]) -> pd.DataFrame:
    """KNIME *Concatenate* (union of columns, rows appended in port order)."""
    frames = [f for f in frames if f is not None and len(f.columns)]
    if not frames:
        return pd.DataFrame()
    non_empty = [f for f in frames if len(f)] or frames[:1]
    return pd.concat(non_empty, ignore_index=True, sort=False)


def rank(df: pd.DataFrame, by: str, group_by_cols: Sequence[str], out: str, ascending: bool = True) -> pd.DataFrame:
    """KNIME *Rank* (standard competition ranking, 1,2,2,4)."""
    out_df = df.copy()
    out_df[out] = (
        out_df.groupby(list(group_by_cols), dropna=False)[by]
        .rank(method="min", ascending=ascending)
        .astype("Int64")
        .to_numpy()
    )
    return out_df


def group_apply(
    df: pd.DataFrame, by: Sequence[str], fn: Callable[[pd.DataFrame], pd.DataFrame | None]
) -> pd.DataFrame:
    """KNIME *Group Loop Start* ... *Loop End*.

    Groups are visited in sorted key order (KNIME sorts unsorted input); row order
    inside a group is kept; empty results are ignored.
    """
    if df.empty:
        return df.copy()
    parts = []
    for _, g in df.groupby(list(by), dropna=False, sort=True):
        res = fn(g.reset_index(drop=True))
        if res is not None and len(res):
            parts.append(res)
    if not parts:
        return df.iloc[0:0].copy()
    return pd.concat(parts, ignore_index=True)


def fill_missing(df: pd.DataFrame, column: str, direction: str) -> pd.DataFrame:
    """KNIME *Missing Value* with previous / next value strategy for one column."""
    out = df.copy()
    out[column] = out[column].ffill() if direction == "previous" else out[column].bfill()
    return out


# ---- date / time helpers (Modify Date / Modify Time) ----


def remove_time(df: pd.DataFrame, columns: Sequence[str], suffix: str = "_date") -> pd.DataFrame:
    """KNIME *Modify Time* (remove time) appending new date-only columns."""
    out = df.copy()
    for c in columns:
        out[c + suffix] = pd.to_datetime(out[c]).dt.normalize()
    return out


def remove_date(df: pd.DataFrame, columns: Sequence[str], suffix: str = "_time") -> pd.DataFrame:
    """KNIME *Modify Date* (remove date) appending new ``datetime.time`` columns."""
    out = df.copy()
    for c in columns:
        ts = pd.to_datetime(out[c])
        out[c + suffix] = pd.Series([t.time() if not pd.isna(t) else None for t in ts], index=out.index, dtype=object)
    return out


def time_to_seconds(s: pd.Series) -> pd.Series:
    return s.map(lambda t: t.hour * 3600 + t.minute * 60 + t.second + t.microsecond / 1e6 if t is not None and not pd.isna(t) else np.nan)


def seconds_to_time(sec: pd.Series) -> pd.Series:
    def conv(x):
        if pd.isna(x):
            return None
        x = x % 86400
        whole = int(x)
        micro = int(round((x - whole) * 1e6))
        return (dt.datetime.min + dt.timedelta(seconds=whole, microseconds=micro)).time()

    return sec.map(conv).astype(object)
