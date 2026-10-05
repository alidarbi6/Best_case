"""Query registry: every SQL statement lives in its own file listed in ``queries.yaml``."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml


class QueryError(ValueError):
    pass


class QueryRegistry:
    def __init__(self, registry_file: Path):
        self.registry_file = Path(registry_file)
        self.base_dir = self.registry_file.parent
        with open(self.registry_file, encoding="utf-8") as fh:
            self.spec = yaml.safe_load(fh) or {}
        self.system = self.spec.get("system", {})
        self.datasets = self.spec.get("datasets", {})
        self.plans = self.spec.get("plans", {})

    # ---- lookup
    def plan(self, mode: str) -> list[str]:
        if mode not in self.plans:
            raise QueryError(f"Unknown queries.mode {mode!r}; available: {sorted(self.plans)}")
        return list(self.plans[mode])

    def _entry(self, name: str) -> dict:
        entry = self.datasets.get(name) or self.system.get(name)
        if entry is None:
            raise QueryError(f"Query {name!r} is not defined in {self.registry_file}")
        return entry

    def sql(self, name: str) -> str:
        entry = self._entry(name)
        path = self.base_dir / entry["file"]
        if not path.exists():
            raise QueryError(f"SQL file for {name!r} not found: {path}")
        return path.read_text(encoding="utf-8").strip().rstrip(";")

    def required_columns(self, name: str) -> list[str]:
        return list(self._entry(name).get("columns", []))

    def string_columns(self, name: str) -> list[str]:
        """Columns that are text in the database (used when reading CSV stand-ins)."""
        return list(self._entry(name).get("string_columns", []))

    def validate(self, name: str, frame: pd.DataFrame) -> pd.DataFrame:
        """Make sure a result set honours the column contract of its dataset."""
        missing = [c for c in self.required_columns(name) if c not in frame.columns]
        if missing:
            raise QueryError(
                f"Query {name!r} ({self._entry(name)['file']}) must return column(s) {missing}; "
                f"it returned {list(frame.columns)}"
            )
        return frame
