"""Stage 3 - sub-workflow "START / END": start and end time of every activity of a day.

Within one report day (idwell + start date) the activities are ordered by ``sysseq``;
the running total of their durations is added to the day's start time.  The end of
activity *n* is that sum; the start of activity *n* is the end of activity *n-1*
(the first activity keeps the original start time).
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from ..engine.ops import seconds_to_time, time_to_seconds
from ..engine.sorting import sort_dataframe
from .base import Context

log = logging.getLogger("best_case")


def compute_start_end(df: pd.DataFrame, cfg) -> pd.DataFrame:
    p = cfg.get("start_end", {})
    dur = p.get("duration_column", "duration")
    groups = list(p.get("group_columns", ["idwell", "dttmstart_date"]))
    d = sort_dataframe(df, p.get("sort_columns", ["dttmstart_date", "sysseq"]))
    d = d[d[dur].notna()]
    d = sort_dataframe(d, groups)  # group loop visits groups in key order, rows keep their order
    d = d.reset_index(drop=True)

    grp = d.groupby(groups, dropna=False, sort=False)[dur]
    if p.get("cumulative", "backward") == "forward":
        hours = grp.transform(lambda s: s[::-1].cumsum()[::-1])
    else:
        hours = grp.cumsum()

    full = float(p.get("full_day_hours", 24))
    minus = float(p.get("full_day_minus_minutes", 1))
    minutes = np.where(np.floor(hours) == full, hours * 60 - minus, hours * 60)
    minutes = pd.Series(minutes, index=d.index)
    minutes = minutes.round() if p.get("minutes_to_int", "round") == "round" else np.trunc(minutes)

    shifted = seconds_to_time(time_to_seconds(d["dttmstart_time"]) + minutes * 60)
    previous = shifted.groupby([d[g] for g in groups], dropna=False, sort=False).shift(1)
    d["dttmstart_time"] = pd.Series(
        [pv if pv is not None and not pd.isna(pv) else orig for pv, orig in zip(previous, d["dttmstart_time"])],
        index=d.index, dtype=object,
    )
    d["dttmend_time"] = shifted
    return d


def run(ctx: Context) -> None:
    (tl,) = ctx.need("time_log_clean")
    if ctx.cfg.get("start_end.enabled", True):
        ctx.tables["time_log_timed"] = compute_start_end(tl, ctx.cfg)
    else:
        ctx.tables["time_log_timed"] = tl
    log.info("start/end computed for %d rows", len(ctx.tables["time_log_timed"]))
