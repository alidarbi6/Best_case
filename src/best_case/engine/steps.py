"""Declarative column-cleaning steps (String Manipulation / Rule Engine nodes)."""
from __future__ import annotations

from typing import Iterable, Mapping

import pandas as pd

from .expr import RuleSet, evaluate_expression


def apply_steps(df: pd.DataFrame, steps: Iterable[Mapping]) -> pd.DataFrame:
    """Apply ``type: expression`` / ``type: rules`` steps in order; returns a new frame.

    The result of a step is written to ``column`` (replacing it in place when it exists,
    appending it otherwise), exactly like the KNIME nodes with "replace column".
    """
    out = df.copy()
    for step in steps:
        kind = step.get("type")
        column = step["column"]
        if kind == "expression":
            out[column] = evaluate_expression(out, step["expression"], step.get("convert_to_int", False))
        elif kind == "rules":
            out[column] = RuleSet(step["rules"]).evaluate(out)
        else:
            raise ValueError(f"unknown cleaning step type {kind!r} in {step.get('name', step)}")
    return out
