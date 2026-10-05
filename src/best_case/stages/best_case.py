"""Stage 9 - best case selection and drilling-parameter extraction (document §2, end).

1. total duration per (hole section, well, formation, category)           #186
2. per (hole section, formation, category) keep the well with the minimum   #233
3. take that well's time log and join it with the drilling parameters       #676, #681
"""
from __future__ import annotations

import logging

import pandas as pd

from ..engine.ops import Agg, RowFilterSpec, Select, duplicate_row_filter, group_by, join, row_filter
from .base import Context

log = logging.getLogger("best_case")


def best_sections(sections: pd.DataFrame, cfg) -> pd.DataFrame:
    sums = group_by(
        sections, ["code4", "wellname", "formname", "category"], [Agg("duration", "Sum")], name_policy="method"
    )
    best = duplicate_row_filter(
        sums, ["code4", "formname", "category"], reference="Sum(duration)", selection="MINIMUM"
    )
    best = best.copy()
    best["approach"] = cfg.get("best_case.approach_label", "FOR_HS")
    return best


def _post_filters(df: pd.DataFrame, cfg, stage: str) -> pd.DataFrame:
    for spec in cfg.get("best_case.post_filters", []) or []:
        if spec.get("stage") == stage:
            df = row_filter(df, RowFilterSpec.from_dict(spec))
    return df


def best_case_time_log(time_log: pd.DataFrame, best: pd.DataFrame, cfg) -> pd.DataFrame:
    best = _post_filters(best, cfg, "best_sections")
    tl = join(
        time_log, best, ["code4", "wellname", "formname"], how="inner", right_select=Select(include=["category"])
    )
    return _post_filters(tl, cfg, "best_time_log")


def best_case_result(drill_formations: pd.DataFrame, best_tl: pd.DataFrame) -> pd.DataFrame:
    res = join(
        drill_formations, best_tl, ["wellname", "formname", "dttmend_date"], how="inner",
        right_select=Select(include=[]),
    )
    return res.drop_duplicates().reset_index(drop=True)  # #686


def run(ctx: Context) -> None:
    sections, time_log, drill_formations = ctx.need("sections", "time_log_final", "drill_formations")
    best = best_sections(sections, ctx.cfg)
    best_tl = best_case_time_log(time_log, best, ctx.cfg)
    ctx.tables["best_sections"] = best
    ctx.tables["best_time_log"] = best_tl
    ctx.tables["best_case_result"] = best_case_result(drill_formations, best_tl)
    log.info("best sections: %d, best time-log rows: %d, result rows: %d",
             len(best), len(best_tl), len(ctx.tables["best_case_result"]))
