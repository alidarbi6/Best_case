"""Stage 10 - alternative best-case approaches (sub-workflows "Approach 1/2/3").

These branches end in the KNIME workflow without an exporter; here they are produced as
an extra table.  Each approach returns ``code4, <formation>, category, Sum(duration),
approach`` where the duration is the minimum over wells.

* HS     : total duration per section/well, best well per section
* Code1  : per ``code1`` activity the best well, then summed over activities
* OPSCAT : same with the operation category
"""
from __future__ import annotations

import logging

import pandas as pd

from ..engine.ops import Agg, Select, concatenate, duplicate_row_filter, group_by, join
from .base import Context

log = logging.getLogger("best_case")
SUM = "Sum(duration)"


def _label(df: pd.DataFrame, label: str) -> pd.DataFrame:
    out = df.copy()
    out["approach"] = label
    return out


def approach_hs(sections: pd.DataFrame, form: str, label: str) -> pd.DataFrame:
    g = group_by(sections, ["code4", "wellname", form, "category"], [Agg("duration", "Sum")], name_policy="method")
    return _label(duplicate_row_filter(g, ["code4", form, "category"], reference=SUM, selection="MINIMUM"), label)


def _by_activity(sections, lookup: pd.DataFrame, key_col: str, lookup_key: str, value_col: str, form: str, label: str):
    s = join(sections, lookup, [key_col], [lookup_key], how="inner", right_select=Select(include=[value_col]))
    keys = [key_col, "code4", "wellname", form, "category", value_col]
    g = group_by(s, keys, [Agg("duration", "Sum")], name_policy="method")
    best = duplicate_row_filter(g, [c for c in keys if c != "wellname"], reference=SUM, selection="MINIMUM")
    total = group_by(best, ["code4", form, "category"], [Agg(SUM, "Sum", out_name=SUM)])
    total = duplicate_row_filter(total, ["code4", form, "category"], reference=SUM, selection="MINIMUM")
    return _label(total, label)


def build_approaches(sections: pd.DataFrame, cfg) -> pd.DataFrame:
    p = cfg.get("approaches", {})
    form = p.get("formation_column", "formname")
    labels = p.get("labels", {})
    code1 = pd.DataFrame(
        {"drilling_code1": list(cfg.lookups["code1_activity"].keys()),
         "activity": list(cfg.lookups["code1_activity"].values())}
    )
    ops = pd.DataFrame(
        {"operation_category": list(cfg.lookups["opscategory_operation"].keys()),
         "operation": list(cfg.lookups["opscategory_operation"].values())}
    )
    parts = [
        approach_hs(sections, form, labels.get("hs", "HS")),
        _by_activity(sections, code1, "code1", "drilling_code1", "activity", form, labels.get("code1", "Code1")),
        _by_activity(sections, ops, "opscategory", "operation_category", "operation", form, labels.get("opscat", "OPSCAT")),
    ]
    res = concatenate(parts)
    res[SUM] = res[SUM] / float(p.get("hours_to_days", 24))  # #414
    return duplicate_row_filter(res, ["code4", form, "category", "approach"], reference=SUM, selection="MINIMUM")  # #383


def run(ctx: Context) -> None:
    (sections,) = ctx.need("sections")
    ctx.tables["approaches"] = build_approaches(sections, ctx.cfg)
    log.info("approach table: %d rows", len(ctx.tables["approaches"]))
