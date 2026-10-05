"""Stage 6 - assign drilling-parameter rows to formations (document §2, nodes #502 -> #551).

For each well the parameter rows are cross-joined with the well's formations and kept
when their start or end depth lies inside the formation.  A row that spans two
formations appears twice: the shallower copy ends at its formation bottom, the deeper
copy starts at its formation top.
"""
from __future__ import annotations

import logging

import pandas as pd

from ..engine.expr import RuleSet
from ..engine.ops import cross_join, duplicate_row_filter, group_apply
from ..engine.steps import apply_steps
from .base import Context

log = logging.getLogger("best_case")


def split_by_formation(params: pd.DataFrame, formations: pd.DataFrame, cfg) -> pd.DataFrame:
    sp = cfg.rules["formation_split"]
    in_range = RuleSet(sp["range_rules"])
    dup = sp["duplicate"]
    pieces = []
    for idwell, f in formations.groupby("idwell", dropna=False, sort=True):
        data = params[params["idwell"] == idwell]
        if data.empty:
            continue
        right = f.drop(columns=["idwell"]).reset_index(drop=True)
        cj = cross_join(data.reset_index(drop=True), right)
        cj = cj[in_range.matches(cj)].reset_index(drop=True)
        if cj.empty:
            continue
        cj = duplicate_row_filter(
            cj, dup["group_columns"], reference=dup["reference"], selection=dup.get("selection", "MINIMUM"),
            remove_duplicates=False, flag_column=dup.get("flag_column", "Duplicate Status"),
        )
        pieces.append(apply_steps(cj, sp["adjust"]))
    return pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame()


def run(ctx: Context) -> None:
    params, formations = ctx.need("drill_params", "formation_depths")
    ctx.tables["drill_formations"] = split_by_formation(params, formations, ctx.cfg)
    log.info("drill parameters per formation: %d rows", len(ctx.tables["drill_formations"]))
