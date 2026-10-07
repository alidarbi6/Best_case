"""Command line interface:  ``python -m best_case run --settings config/settings.yaml``."""
from __future__ import annotations

import argparse
import logging
import sys
import warnings
from pathlib import Path

from .config import Config
from .pipeline import STAGES, run_pipeline


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="best-case", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="run the pipeline")
    run.add_argument("--settings", default="config/settings.yaml")
    run.add_argument("--set", dest="overrides", action="append", default=[], metavar="KEY=VALUE",
                     help="override a setting, e.g. --set queries.mode=sql_join")
    run.add_argument("--only", action="append", help="run only this stage (repeatable)")
    run.add_argument("--from-stage", help="start at this stage (needs --cache-dir from a previous run)")
    run.add_argument("--cache-dir", type=Path, help="persist stage outputs here (enables --from-stage)")

    sub.add_parser("stages", help="list the pipeline stages")

    cmp_ = sub.add_parser("compare", help="compare a table with a KNIME reference (xlsx/csv)")
    cmp_.add_argument("--reference", required=True)
    cmp_.add_argument("--ours", default="output/intermediate/section_sums.csv")
    cmp_.add_argument("--keys", default="code4,wellname,formname,category")
    cmp_.add_argument("--values", default="Sum(duration)")
    cmp_.add_argument("--tol", type=float, default=1e-6)

    demo = sub.add_parser("demo-data", help="write a synthetic CSV data set (no database needed)")
    demo.add_argument("--out", default="data/raw", type=Path)
    demo.add_argument("--seed", type=int, default=7)

    args = ap.parse_args(argv)
    if args.cmd == "stages":
        for s in STAGES:
            print(f"{s.name:22s} {s.description}")
        return 0
    if args.cmd == "compare":
        from .compare import compare_tables, load, report

        res = compare_tables(load(args.reference), load(args.ours), args.keys.split(","), args.values.split(","), args.tol)
        print(report(res))
        return 0 if res["matched"] == res["n_reference"] == res["n_ours"] else 1
    if args.cmd == "demo-data":
        from .testing.synthetic import write_csv_dataset

        write_csv_dataset(args.out, seed=args.seed)
        print(f"synthetic data written to {args.out}")
        return 0

    warnings.filterwarnings("ignore", category=FutureWarning)
    cfg = Config.load(args.settings, args.overrides)
    logging.basicConfig(level=cfg.get("logging.level", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
    run_pipeline(cfg, only=args.only, start_from=args.from_stage, cache_dir=args.cache_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
