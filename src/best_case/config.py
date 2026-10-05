"""Configuration loading (settings.yaml + rules.yaml + lookups.yaml)."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Iterable

import yaml


class ConfigError(ValueError):
    pass


def _deep_update(base: dict, other: dict) -> dict:
    for k, v in other.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_update(base[k], v)
        else:
            base[k] = v
    return base


def _set_path(d: dict, dotted: str, value: Any) -> None:
    keys = dotted.split(".")
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = value


class Config:
    """Read-only view of the settings with dotted-path access.

    ``cfg.get("start_end.enabled")`` / ``cfg["start_end"]["enabled"]``.
    """

    def __init__(self, data: dict, base_dir: Path):
        self.data = data
        self.base_dir = Path(base_dir)

    # ---- access
    def get(self, path: str, default: Any = None) -> Any:
        node: Any = self.data
        for key in path.split("."):
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    def require(self, path: str) -> Any:
        sentinel = object()
        val = self.get(path, sentinel)
        if val is sentinel or val is None:
            raise ConfigError(f"Missing required setting {path!r}")
        return val

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def path(self, dotted: str) -> Path:
        """Resolve a path-valued setting relative to the settings directory."""
        p = Path(self.require(dotted))
        return p if p.is_absolute() else (self.base_dir / p).resolve()

    # ---- loading
    @classmethod
    def load(cls, settings_file: str | Path, overrides: Iterable[str] = ()) -> "Config":
        settings_file = Path(settings_file).resolve()
        with open(settings_file, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        base = settings_file.parent
        for ov in overrides:
            if "=" not in ov:
                raise ConfigError(f"Override must look like key.sub=value, got {ov!r}")
            key, raw = ov.split("=", 1)
            _set_path(data, key.strip(), yaml.safe_load(raw))
        cfg = cls(data, base)
        cfg.rules = cfg._load_side_file("files.rules")
        cfg.lookups = cfg._load_side_file("files.lookups")
        return cfg

    def _load_side_file(self, setting: str) -> dict:
        p = self.path(setting)
        if not p.exists():
            raise ConfigError(f"{setting} points to missing file {p}")
        with open(p, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}

    def copy_with(self, **overrides: Any) -> "Config":
        new = Config(copy.deepcopy(self.data), self.base_dir)
        new.rules, new.lookups = self.rules, self.lookups
        for k, v in overrides.items():
            _set_path(new.data, k.replace("__", "."), v)
        return new

    rules: dict
    lookups: dict
