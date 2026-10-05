"""Stage 8 - completed hole sections (sub-workflow "COMPLETED HO", nodes #369, #460, #397, #439).

A hole section (``code4``) of a well counts as completed when the well has a
*completion* activity; for wells without one the first section in natural order
(the smallest = last drilled hole size) is still being drilled and is dropped.
"""
from __future__ import annotations

import logging

import pandas as pd

from ..engine.ops import RowFilterSpec, Select, concatenate, distinct, group_apply, join, row_filter
from ..engine.sorting import sort_dataframe
from ..engine.steps import apply_steps
from .base import Context

log = logging.getLogger("best_case")


def completed_hole_sections(pairs: pd.DataFrame, cfg) -> pd.DataFrame:
    code = str(cfg.get("completed_sections.completion_code", "completion")).lower()
    s = sort_dataframe(pairs, ["code4"], natural=True, missing_to_end=True)  # #292
    is_completion = s["code4"].map(lambda v: not pd.isna(v) and str(v).lower() == code)
    completion = s[is_completion]  # #301
    matched = join(s, completion, ["wellname"], how="inner", right_select=Select(include=[]))  # #302 port 1
    has_completion = s["wellname"].isin(set(completion["wellname"].dropna()))
    unmatched = s[~has_completion]  # #302 port 2 (wells without a completion)
    trimmed = group_apply(unmatched, ["wellname"], lambda g: g.iloc[1:])  # #293, #303, #304
    return concatenate([matched, trimmed])  # #305


def build_sections(time_log: pd.DataFrame, cfg) -> pd.DataFrame:
    pairs = distinct(time_log, ["code4", "wellname"])  # #369
    completed = completed_hole_sections(pairs, cfg)
    filtered = row_filter(time_log, RowFilterSpec.from_dict(cfg.require("section_filter")))  # #460
    drop = list(cfg.get("completed_sections.drop_columns", []))
    log.info("sections: %d time-log rows, %d (code4, well) pairs, %d completed pairs, %d rows pass the section filter",
             len(time_log), len(pairs), len(completed), len(filtered))
    sections = join(
        filtered, completed, ["wellname", "code4"], how="inner",
        left_select=Select(exclude=drop), right_select=Select(include=[]),
    )  # #397
    return apply_steps(sections, cfg.rules["well_category"])  # #439


def run(ctx: Context) -> None:
    (tl,) = ctx.need("time_log_final")
    ctx.tables["sections"] = build_sections(tl, ctx.cfg)
    log.info("completed-section rows: %d", len(ctx.tables["sections"]))
