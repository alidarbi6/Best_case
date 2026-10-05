"""Stage / pipeline-context primitives."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

from ..config import Config

log = logging.getLogger("best_case")


@dataclass
class Context:
    cfg: Config
    source: object | None = None  # DataSource
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)

    def need(self, *names: str) -> list[pd.DataFrame]:
        missing = [n for n in names if n not in self.tables]
        if missing:
            raise KeyError(f"tables {missing} are not available yet (available: {sorted(self.tables)})")
        return [self.tables[n] for n in names]


@dataclass
class Stage:
    name: str
    func: Callable[[Context], None]
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    description: str = ""
    optional_flag: str | None = None  # settings path; stage is skipped when it is false
