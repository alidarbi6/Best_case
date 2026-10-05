"""Stage 7 - merge time log and formations, fill the formation of every activity.

Document §2: the formation table is appended to the time log, sorted by date and
formation sequence; ``formname`` is filled with the previous and then the next known
value per well; rows without ``idrec`` (the formation rows) are dropped.
"""
from __future__ import annotations

import logging

import pandas as pd

from ..engine.ops import concatenate, fill_missing, group_apply
from ..engine.sorting import sort_dataframe
from .base import Context

log = logging.getLogger("best_case")


def merge_time_log(timed: pd.DataFrame, drill_formations: pd.DataFrame, cfg) -> pd.DataFrame:
    stub_cols = [c for c in cfg.get("formation_stub_columns") if c in drill_formations.columns]
    stub = drill_formations[stub_cols]
    merged = concatenate([timed, stub])  # #659
    merged = sort_dataframe(merged, ["dttmstart_date", "form_seq"])  # #660

    def fill(g: pd.DataFrame) -> pd.DataFrame:
        g = fill_missing(g, "formname", "previous")  # #665
        return fill_missing(g, "formname", "next")  # #667

    merged = group_apply(merged, ["idwell"], fill)
    return merged[merged["idrec"].notna()].reset_index(drop=True)  # #669


def run(ctx: Context) -> None:
    timed, drill_formations = ctx.need("time_log_timed", "drill_formations")
    ctx.tables["time_log_final"] = merge_time_log(timed, drill_formations, ctx.cfg)
    log.info("time log with formations: %d rows", len(ctx.tables["time_log_final"]))
