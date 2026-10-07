"""Pipeline definition and runner.

Each stage is a plain function ``fn(ctx)`` registered in :data:`STAGES`.  To replace a
stage without touching this package, point ``pipeline.overrides`` in settings.yaml at
your own function (``"my_module:my_function"``) - it receives the same ``Context``.
"""
from __future__ import annotations

import importlib
import logging
import pickle
from pathlib import Path

from .config import Config
from .io.queries import QueryRegistry
from .io.sources import DataSource, build_source
from .stages import (report, approaches, best_case, export, extract, formation_split, formations, merge_time_log,
                     sections, start_end, time_log, drilling_parameters)
from .stages.base import Context, Stage

log = logging.getLogger("best_case")

STAGES: list[Stage] = [
    Stage("extract", extract.run, (), ("raw_time_log", "raw_drill", "raw_formation"),
          "Read databases, run queries, assemble time log / drill data / formations (§1)"),
    Stage("time_log", time_log.run, ("raw_time_log",), ("time_log_clean", "wells"),
          "Deduplicate, keep new-design wells, clean text columns (§1.2)"),
    Stage("start_end", start_end.run, ("time_log_clean",), ("time_log_timed",),
          "Compute start/end time of day from durations"),
    Stage("formations", formations.run, ("raw_formation", "wells"), ("formation_depths",),
          "Clean formations, derive bottoms, rank (§1.4)"),
    Stage("drilling_parameters", drilling_parameters.run, ("raw_drill", "wells"), ("drill_params",),
          "Drill string + parameters, concatenate components (§1.3)"),
    Stage("formation_split", formation_split.run, ("drill_params", "formation_depths"), ("drill_formations",),
          "Assign parameter rows to formations (§2)"),
    Stage("merge_time_log", merge_time_log.run, ("time_log_timed", "drill_formations"), ("time_log_final",),
          "Append formations to the time log and fill formation names (§2)"),
    Stage("sections", sections.run, ("time_log_final",), ("sections",),
          "Completed hole sections + category (§2)"),
    Stage("best_case", best_case.run, ("sections", "time_log_final", "drill_formations"),
          ("section_sums", "best_sections", "best_time_log", "best_case_result"), "Best case per section/formation and result (§2)"),
    Stage("approaches", approaches.run, ("sections",), ("approaches",),
          "Alternative approaches HS / Code1 / OPSCAT", optional_flag="approaches.enabled"),
    Stage("report", report.run, ("sections", "best_sections", "best_time_log", "best_case_result"), (),
          "Comparison report in the layout of the presentation (tables, Excel charts, PNG charts)",
          optional_flag="report.enabled"),
    Stage("export", export.run, ("best_case_result",), (), "Write Excel / CSV"),
]


def _resolve_override(spec: str):
    module, _, attr = spec.partition(":")
    return getattr(importlib.import_module(module), attr)


def run_pipeline(
    cfg: Config,
    *,
    source: DataSource | None = None,
    only: list[str] | None = None,
    start_from: str | None = None,
    cache_dir: Path | None = None,
) -> Context:
    registry = QueryRegistry(cfg.path("queries.file"))
    own_source = source is None
    source = source or build_source(cfg, registry)
    ctx = Context(cfg=cfg, source=source)
    names = [s.name for s in STAGES]
    if start_from and start_from not in names:
        raise ValueError(f"unknown stage {start_from!r}; stages: {names}")
    overrides = cfg.get("pipeline.overrides", {}) or {}
    started = start_from is None
    try:
        for st in STAGES:
            if not started and st.name == start_from:
                started = True
                if cache_dir:
                    _load_cache(ctx, cache_dir, st.inputs)
            if not started:
                continue
            if only and st.name not in only:
                continue
            if st.optional_flag and not cfg.get(st.optional_flag, True):
                log.info("stage %-20s skipped (%s is false)", st.name, st.optional_flag)
                continue
            func = _resolve_override(overrides[st.name]) if st.name in overrides else st.func
            log.info("stage %-20s %s", st.name, st.description)
            func(ctx)
            if cache_dir:
                _save_cache(ctx, cache_dir, st.outputs)
    finally:
        if own_source:
            source.close()
    return ctx


def _save_cache(ctx: Context, cache_dir: Path, names) -> None:
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    for n in names:
        with open(cache_dir / f"{n}.pkl", "wb") as fh:
            pickle.dump(ctx.tables[n], fh)


def _load_cache(ctx: Context, cache_dir: Path, required) -> None:
    """Load every cached table (later stages may need tables of several earlier stages)."""
    cache_dir = Path(cache_dir)
    for p in sorted(cache_dir.glob("*.pkl")):
        with open(p, "rb") as fh:
            ctx.tables[p.stem] = pickle.load(fh)
    missing = [n for n in required if n not in ctx.tables]
    if missing:
        raise FileNotFoundError(f"cache missing table(s) {missing} in {cache_dir} (run the earlier stages first)")
