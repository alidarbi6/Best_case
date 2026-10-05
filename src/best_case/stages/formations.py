"""Stage 4 - formation depths (document §1.4, nodes #542 -> #663)."""
from __future__ import annotations

import logging

import pandas as pd

from ..engine.ops import Agg, Select, group_apply, group_by, join, rank
from ..engine.sorting import sort_dataframe
from ..engine.steps import apply_steps
from .base import Context

log = logging.getLogger("best_case")


def formation_depths(raw: pd.DataFrame, wells: pd.DataFrame, cfg) -> pd.DataFrame:
    # keep the formations of the new-design wells, add wellname (#542)
    f = join(raw, wells, ["idwell"], how="inner", right_select=Select(include=["wellname"]))
    # deepest first; the bottom of a formation = top of the next (deeper) one (#576-#578)
    f = sort_dataframe(f, ["depthdrillingtop"], ascending=False)

    def fill_bottom(g: pd.DataFrame) -> pd.DataFrame:
        g = g.copy()
        g["depthdrillingbtm"] = g["depthdrillingbtm"].fillna(g["depthdrillingtop"].shift(1))
        return g

    f = group_apply(f, ["idwell"], fill_bottom)
    f = apply_steps(f, cfg.rules["formation_cleaning"])  # #474, #475
    f = f[~(f["depthdrillingbtm"].isna() & f["depthdrillingtop"].isna())]  # #513
    f = f[f["formname"].map(lambda v: not pd.isna(v) and str(v).lower() != "td")]  # #532 (TD excluded)
    f = group_by(
        f, ["idwell", "formname"],
        [Agg("depthdrillingtop", "Minimum"), Agg("depthdrillingbtm", "Maximum")],
    )  # #537
    f = rank(f, "depthdrillingtop", ["idwell"], "form_seq")  # #663
    return sort_dataframe(f, ["idwell", "form_seq"])  # tidy order (KNIME leaves it arbitrary)


def run(ctx: Context) -> None:
    raw, wells = ctx.need("raw_formation", "wells")
    ctx.tables["formation_depths"] = formation_depths(raw, wells, ctx.cfg)
    log.info("formations: %d rows", len(ctx.tables["formation_depths"]))
