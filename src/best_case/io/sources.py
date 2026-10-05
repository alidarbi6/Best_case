"""Data sources: SQL Server (production) or a directory of CSV files (tests / offline)."""
from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable

import pandas as pd

from ..config import Config, ConfigError
from .queries import QueryRegistry

log = logging.getLogger(__name__)


class DataSource(ABC):
    """Anything that can list databases and return the named datasets of one database."""

    registry: QueryRegistry

    @abstractmethod
    def list_databases(self) -> list[str]: ...

    @abstractmethod
    def read(self, database: str, dataset: str) -> pd.DataFrame: ...

    def close(self) -> None:  # pragma: no cover - trivial
        pass


class DatabaseSource(DataSource):
    """SQL Server access through SQLAlchemy.

    ``engine_factory(database_name) -> Engine`` can be injected (tests use SQLite).
    """

    def __init__(self, cfg: Config, registry: QueryRegistry, engine_factory: Callable | None = None):
        self.cfg = cfg
        self.registry = registry
        self._engines: dict[str, object] = {}
        self._factory = engine_factory or self._mssql_engine

    def _mssql_engine(self, database: str):
        from sqlalchemy import create_engine

        d = self.cfg.require("database")
        user = os.environ.get(d.get("user_env", ""), "") or d.get("user")
        pwd_env = d.get("password_env", "BEST_CASE_DB_PASSWORD")
        password = os.environ.get(pwd_env)
        if not user or password is None:
            raise ConfigError(f"Set the DB credentials via environment variables ({d.get('user_env')}, {pwd_env}).")
        from urllib.parse import quote_plus

        url = d["url_template"].format(
            user=quote_plus(user), password=quote_plus(password), host=d["host"], port=d["port"], database=database
        )
        return create_engine(url, connect_args={"login_timeout": int(d.get("login_timeout", 30))})

    def _engine(self, database: str):
        if database not in self._engines:
            self._engines[database] = self._factory(database)
        return self._engines[database]

    def _query(self, database: str, sql: str) -> pd.DataFrame:
        from sqlalchemy import text

        with self._engine(database).connect() as conn:
            return pd.read_sql(text(sql), conn)

    def list_databases(self) -> list[str]:
        master = self.cfg.get("database.master_database", "master")
        df = self._query(master, self.registry.sql("databases"))
        self.registry.validate("databases", df)
        return df["name"].tolist()

    def read(self, database: str, dataset: str) -> pd.DataFrame:
        df = self._query(database, self.registry.sql(dataset))
        return self.registry.validate(dataset, df)

    def close(self) -> None:
        for e in self._engines.values():
            e.dispose()


class CsvDirSource(DataSource):
    """``<dir>/<database>/<dataset>.csv`` - lets the pipeline run without a database."""

    def __init__(self, directory: Path, registry: QueryRegistry):
        self.dir = Path(directory)
        self.registry = registry

    def list_databases(self) -> list[str]:
        listing = self.dir / "databases.csv"
        if listing.exists():
            return pd.read_csv(listing)["name"].tolist()
        return sorted(p.name for p in self.dir.iterdir() if p.is_dir())

    def read(self, database: str, dataset: str) -> pd.DataFrame:
        path = self.dir / database / f"{dataset}.csv"
        if not path.exists():
            raise FileNotFoundError(path)
        df = pd.read_csv(path, dtype={c: str for c in self.registry.string_columns(dataset)})
        for col in df.columns:
            if col.startswith("dttm"):
                df[col] = pd.to_datetime(df[col])
        return self.registry.validate(dataset, df)


def build_source(cfg: Config, registry: QueryRegistry) -> DataSource:
    kind = cfg.get("source.type", "database")
    if kind == "database":
        return DatabaseSource(cfg, registry)
    if kind == "csv_dir":
        return CsvDirSource(cfg.path("source.csv_dir"), registry)
    raise ConfigError(f"source.type must be 'database' or 'csv_dir', got {kind!r}")
