"""Stage 2 - time-log preparation (document §1.2, nodes #413 -> #416)."""
from __future__ import annotations

import logging

import pandas as pd

from ..engine.ops import RowFilterSpec, distinct, duplicate_row_filter, row_filter
from ..engine.steps import apply_steps
from .base import Context

log = logging.getLogger("best_case")


def prepare_time_log(raw: pd.DataFrame, cfg) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns ``(cleaned time log of the new-design wells, well list idwell/wellname)``."""
    tl = duplicate_row_filter(raw, None, selection="FIRST")  # exact duplicate rows (#413)
    col = cfg.get("time_log.well_filter_column", "wellname")
    wells = list(cfg.lookups["new_design_wells"])
    spec = RowFilterSpec.from_dict(
        {"conditions": [{"column": col, "operator": "IN", "value": wells, "case_sensitive": True}]}
    )
    tl = row_filter(tl, spec)  # Rule-based Row Splitter #412 (matching output)
    well_list = distinct(tl, ["idwell", "wellname"])  # GroupBy #539
    tl = apply_steps(tl, cfg.rules["time_log_cleaning"])
    return tl, well_list


def run(ctx: Context) -> None:
    (raw,) = ctx.need("raw_time_log")
    ctx.tables["time_log_clean"], ctx.tables["wells"] = prepare_time_log(raw, ctx.cfg)
    log.info("time log: %d rows, %d wells", len(ctx.tables["time_log_clean"]), len(ctx.tables["wells"]))
