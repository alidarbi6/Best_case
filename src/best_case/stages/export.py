"""Stage 11 - Excel / CSV export (workflow node: Excel Writer #687)."""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from .base import Context

log = logging.getLogger("best_case")

_INTERMEDIATE = [
    "time_log_final", "sections", "section_sums", "best_sections", "best_time_log", "drill_params",
    "formation_depths", "drill_formations", "approaches",
]


def _excel_safe(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[c]) and getattr(out[c].dt, "tz", None) is not None:
            out[c] = out[c].dt.tz_localize(None)
    return out


def run(ctx: Context) -> None:
    cfg = ctx.cfg
    out_dir = cfg.path("export.directory")
    out_dir.mkdir(parents=True, exist_ok=True)
    result = ctx.tables.get("best_case_result")
    xl = cfg.get("export.excel", {})
    if xl.get("enabled", True) and result is not None:
        path = out_dir / xl.get("file", "best_case.xlsx")
        date_fmt = xl.get("date_columns_format", "yyyy-mm-dd")
        with pd.ExcelWriter(path, engine="openpyxl", datetime_format="yyyy-mm-dd hh:mm:ss", date_format=date_fmt) as w:
            _excel_safe(result).to_excel(w, sheet_name=xl.get("sheet", "best_case"), index=False)
            if "approaches" in ctx.tables and cfg.get("export.approaches_sheet"):
                _excel_safe(ctx.tables["approaches"]).to_excel(w, sheet_name=cfg.get("export.approaches_sheet"), index=False)
        log.info("Excel written: %s", path)
        ctx.tables["_excel_path"] = pd.DataFrame({"path": [str(path)]})
    if cfg.get("export.save_intermediate", False) and cfg.get("export.intermediate_format", "csv") == "csv":
        inter = Path(out_dir) / "intermediate"
        inter.mkdir(exist_ok=True)
        for name in _INTERMEDIATE + ["best_case_result"]:
            if name in ctx.tables:
                ctx.tables[name].to_csv(inter / f"{name}.csv", index=False)
        log.info("intermediate tables written to %s", inter)
