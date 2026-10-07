"""Compare our table with a reference produced by the KNIME workflow.

``python -m best_case compare --reference data_validation.xlsx --ours output/intermediate/section_sums.csv``

Both tables are matched on the key columns (default: code4, wellname, formname, category);
the value columns (default: Sum(duration)) are compared with a tolerance.
"""
from __future__ import annotations

import pandas as pd


def load(path: str) -> pd.DataFrame:
    path = str(path)
    return pd.read_csv(path) if path.lower().endswith(".csv") else pd.read_excel(path)


def compare_tables(ref: pd.DataFrame, ours: pd.DataFrame, keys: list[str], values: list[str], tol: float = 1e-6) -> dict:
    ref, ours = ref.copy(), ours.copy()
    for k in keys:  # compare keys as text so that "17" == 17
        ref[k], ours[k] = ref[k].astype(str).str.strip(), ours[k].astype(str).str.strip()
    ref = ref.groupby(keys, dropna=False)[values].sum().reset_index()
    ours = ours.groupby(keys, dropna=False)[values].sum().reset_index()
    m = ref.merge(ours, on=keys, how="outer", suffixes=("_ref", "_ours"), indicator=True)
    only_ref, only_ours = m[m["_merge"] == "left_only"], m[m["_merge"] == "right_only"]
    both = m[m["_merge"] == "both"].copy()
    bad = pd.Series(False, index=both.index)
    for v in values:
        both[f"{v}_diff"] = both[f"{v}_ours"] - both[f"{v}_ref"]
        bad |= both[f"{v}_diff"].abs() > tol
    return {"matched": int((~bad).sum()), "value_differences": both[bad], "only_in_reference": only_ref,
            "only_in_ours": only_ours, "n_reference": len(ref), "n_ours": len(ours)}


def report(res: dict) -> str:
    lines = [f"rows: reference={res['n_reference']} ours={res['n_ours']} | identical={res['matched']} | "
             f"value differences={len(res['value_differences'])} | only in reference={len(res['only_in_reference'])} | "
             f"only in ours={len(res['only_in_ours'])}"]
    for title, df in (("VALUE DIFFERENCES", res["value_differences"]), ("ONLY IN REFERENCE", res["only_in_reference"]),
                      ("ONLY IN OURS", res["only_in_ours"])):
        if len(df):
            lines += ["", title, df.drop(columns=["_merge"], errors="ignore").to_string(index=False)]
    lines.append("\nRESULT: " + ("IDENTICAL" if not (len(res["value_differences"]) or len(res["only_in_reference"])
                                                      or len(res["only_in_ours"])) else "DIFFERENCES FOUND"))
    return "\n".join(lines)
