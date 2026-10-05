"""KNIME-style *Sorter* (stable, natural string order, configurable missing handling)."""
from __future__ import annotations

import re
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

_CHUNK = re.compile(r"(\d+)")


def natural_key(value) -> tuple:
    """Key for 'natural' ordering: digit runs compare numerically (``"8 1/2" < "12 1/4"``)."""
    parts = []
    for chunk in _CHUNK.split(str(value)):
        if chunk == "":
            continue
        parts.append((0, int(chunk), "") if chunk.isdigit() else (1, 0, chunk))
    return tuple(parts)


def _codes(series: pd.Series, natural: bool) -> np.ndarray:
    """Dense sortable integer codes; missing values get ``-1`` (smallest)."""
    if natural and not pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_datetime64_any_dtype(series):
        uniques = pd.unique(series.dropna())
        order = sorted(uniques, key=natural_key)
        mapping = {v: i for i, v in enumerate(order)}
        return np.array([mapping[v] if not pd.isna(v) else -1 for v in series], dtype=np.int64)
    codes, _ = pd.factorize(series, sort=True)
    return codes.astype(np.int64)


def sort_dataframe(
    df: pd.DataFrame,
    columns: Sequence[str],
    ascending: bool | Sequence[bool] = True,
    *,
    natural: bool | Sequence[bool] = False,
    missing_to_end: bool = False,
) -> pd.DataFrame:
    """Stable multi-column sort.

    Mirrors the KNIME Sorter: with ``missing_to_end=False`` a missing value is the
    *smallest* value (first when ascending, last when descending).
    """
    columns = list(columns)
    if not columns or df.empty:
        return df.copy()
    asc = [ascending] * len(columns) if isinstance(ascending, bool) else list(ascending)
    nat = [natural] * len(columns) if isinstance(natural, bool) else list(natural)
    keys = []
    for col, a, nt in zip(columns, asc, nat):
        codes = _codes(df[col], nt)
        missing = codes < 0
        big = int(codes.max()) + 1 if codes.size else 0
        if missing_to_end:
            k = np.where(missing, big, codes if a else -codes)
            if not a:
                k = np.where(missing, big, -codes)
        else:
            k = codes if a else -codes
        keys.append(k)
    order = np.lexsort(tuple(reversed(keys)))
    return df.iloc[order].reset_index(drop=True)
