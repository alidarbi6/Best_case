"""Stage 5 - drilling parameters + drill string (document §1.3, nodes #540 -> #526)."""
from __future__ import annotations

import logging

import pandas as pd

from ..engine.ops import Agg, duplicate_row_filter, group_by, remove_time
from ..engine.sorting import sort_dataframe
from .base import Context

log = logging.getLogger("best_case")

# columns that are concatenated per parameter record (the others are the group keys)
CONCAT_COLUMNS = [
    "wearbearing", "weardull", "weargauge", "wearinner", "wearloc", "wearother", "wearouter", "wearpulled",
    "com_DrillstringComp", "des_DrillstringComp", "grade", "hoursstart", "joints", "length", "make", "model", "sysseq",
]


def drilling_parameters(raw: pd.DataFrame, wells: pd.DataFrame, cfg) -> pd.DataFrame:
    d = raw[raw["idwell"].isin(set(wells["idwell"].dropna()))]  # #540
    d = remove_time(d, ["dttmend", "dttmstart"], "_date")  # #495
    d = duplicate_row_filter(d, None, reference="jobtyp", selection="MINIMUM", exclude_cols=["jobtyp"])  # #497
    d = sort_dataframe(d, ["sysseq"])  # #683
    keys = [c for c in d.columns if c not in CONCAT_COLUMNS]
    aggs = [Agg(c, "Concatenate", include_missing=True) for c in CONCAT_COLUMNS if c in d.columns]
    d = group_by(d, keys, aggs, delimiter=", ", integral_floats_as_int=True)  # #684
    return d[~(d["depthend"].isna() & d["depthstart"].isna())].reset_index(drop=True)  # #526


def run(ctx: Context) -> None:
    raw, wells = ctx.need("raw_drill", "wells")
    ctx.tables["drill_params"] = drilling_parameters(raw, wells, ctx.cfg)
    log.info("drilling parameters: %d rows", len(ctx.tables["drill_params"]))
