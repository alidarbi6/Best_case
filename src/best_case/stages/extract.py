"""Stage 1 - database connection and per-database extraction (document §1.1-1.4).

For every selected database the datasets are read and assembled into three tables that
are concatenated across databases: the time log, the drilling parameters (+ drill
string) and the formations.
"""
from __future__ import annotations

import logging

import pandas as pd

from ..engine.ops import RowFilterSpec, Select, concatenate, join, remove_date, remove_time, row_filter
from .base import Context

log = logging.getLogger("best_case")


# --------------------------------------------------------------------------- per database


def assemble_general_well_data(d: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """§1.1: wells + jobs (+ rigs).  Output keeps idwell, wellname, idrec (job) and jobtyp."""
    if "job_rig" in d:  # sql_join mode: job LEFT JOIN rig already done by SQL Server
        job_rig = d["job_rig"]
    else:
        job_rig = join(
            d["job"], d["rig"], ["idrec"], ["idrecparent"], how="left",
            right_select=Select(exclude=["idwell", "idrecparent", "idrec"]),
        )
    gwd = join(d["well_header"], job_rig, ["idwell"], how="left", right_select=Select(exclude=["idwell"]))
    return gwd[["idwell", "wellname", "idrec", "jobtyp"]]


def assemble_time_log(d: dict[str, pd.DataFrame], gwd: pd.DataFrame, cfg) -> pd.DataFrame:
    """§1.2: job report + time log + well name / job type + wellbore description."""
    if "report_timelog" in d:
        rt = d["report_timelog"].copy()
    else:
        rt = join(
            d["report"], d["timelog"], ["idwell", "idrec"], ["idwell", "idrecparent"], how="left",
            right_select=Select(exclude=["idwell", "idrecparent", "idrec"]),
        )
    rt["duration"] = rt["duration"] * float(cfg.get("time_log.duration_factor", 24))
    rt = remove_time(rt, ["dttmend", "dttmstart"], "_date")
    rt = remove_date(rt, ["dttmend", "dttmstart"], "_time")
    tl = join(
        rt, gwd, ["idwell", "idrecparent"], ["idwell", "idrec"], how="left",
        right_select=Select(include=["wellname", "jobtyp"]),
    )
    tl = join(
        tl, d["wellbore"], ["idwell", "idrecwellbore"], ["idwell", "idrec"], how="left",
        right_select=Select(include=["des"]),
    )
    return tl


def assemble_drill(d: dict[str, pd.DataFrame], gwd: pd.DataFrame) -> pd.DataFrame:
    """§1.3: drill string + components + drilling parameters (+ well name / job type)."""
    if "drillstring_joined" in d:
        ds = d["drillstring_joined"]
    else:
        ds = join(
            d["drillstring"], d["drillstring_comp"], ["idwell", "idrec"], ["idwell", "idrecparent"], how="left",
            right_select=Select(exclude=["idwell", "idrecparent", "idrec"]), suffix="_DrillstringComp",
        )
    params = join(d["drillparam"], gwd, ["idwell"], how="left", right_select=Select(include=["wellname", "jobtyp"]))
    return join(
        ds, params, ["idwell", "idrec"], ["idwell", "idrecparent"], how="left",
        right_select=Select(exclude=["idwell", "idrecparent", "idrec"]), suffix="_DrillstringParam",
    )


def extract_database(source, database: str, mode: str, cfg) -> dict[str, pd.DataFrame]:
    plan = source.registry.plan(mode)
    data = {name: source.read(database, name) for name in plan}
    gwd = assemble_general_well_data(data)
    return {
        "time_log": assemble_time_log(data, gwd, cfg),
        "drill": assemble_drill(data, gwd),
        "formation": data["formation"],
    }


# --------------------------------------------------------------------------- stage


def select_databases(source, cfg) -> list[str]:
    names = pd.DataFrame({"name": source.list_databases()})
    spec = RowFilterSpec.from_dict(cfg.require("database_selection"))
    chosen = row_filter(names, spec)["name"].tolist()
    log.info("databases selected (%d of %d): %s", len(chosen), len(names), chosen)
    return chosen


def run(ctx: Context) -> None:
    cfg, source = ctx.cfg, ctx.source
    mode = cfg.get("queries.mode", "per_table")
    on_error = cfg.get("database.on_database_error", "raise")
    parts: dict[str, list[pd.DataFrame]] = {"time_log": [], "drill": [], "formation": []}
    for db in select_databases(source, cfg):
        try:
            res = extract_database(source, db, mode, cfg)
        except Exception as exc:  # noqa: BLE001
            if on_error == "skip":
                log.warning("database %s skipped: %s", db, exc)
                continue
            raise
        for key, frame in res.items():
            log.info("  %s: %-10s %6d rows", db, key, len(frame))
            parts[key].append(frame)
    if not parts["time_log"]:
        raise RuntimeError("no database produced data - check database_selection and the connection")
    ctx.tables["raw_time_log"] = concatenate(parts["time_log"])
    ctx.tables["raw_drill"] = concatenate(parts["drill"])
    ctx.tables["raw_formation"] = concatenate(parts["formation"])
