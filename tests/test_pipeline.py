import pandas as pd
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool

from best_case.config import Config, ConfigError
from best_case.io.queries import QueryError, QueryRegistry
from best_case.io.sources import CsvDirSource, DatabaseSource
from best_case.pipeline import run_pipeline
from best_case.testing.synthetic import build_tables, write_csv_dataset

TABLE_NAMES = {
    "well_header": "wvt_wvwellheader", "job": "wvt_wvjob", "rig": "wvt_wvjobrig", "report": "wvt_wvjobreport",
    "timelog": "wvt_wvjobreporttimelog", "wellbore": "wvt_wvwellbore", "drillstring": "wvt_wvjobdrillstring",
    "drillstring_comp": "wvt_wvjobdrillstringcomp", "drillparam": "wvt_wvjobdrillstringdrillparam",
    "formation": "wvt_wvwellboreformation",
}


class SqliteSource(DatabaseSource):
    """Runs the real .sql files against SQLite (schema ``dbo`` attached) - no SQL Server needed."""

    def __init__(self, cfg, registry, tables):
        def factory(database):
            eng = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

            @event.listens_for(eng, "connect")
            def _attach(conn, _):
                conn.execute("ATTACH DATABASE ':memory:' AS dbo")

            with eng.begin() as conn:
                for ds, df in tables.get(database, {}).items():
                    df.to_sql(TABLE_NAMES[ds], conn, schema="dbo", index=False)
            return eng

        super().__init__(cfg, registry, factory)
        self._names = list(tables)

    def list_databases(self):
        return ["master", *self._names]

    def _query(self, database, sql):
        df = super()._query(database, sql)
        for c in df.columns:
            if c.startswith("dttm") or c.endswith("dttmend") or c.endswith("dttmstart"):
                df[c] = pd.to_datetime(df[c])
        return df


@pytest.fixture(scope="module")
def tables():
    return build_tables(seed=7)


def _cfg(settings_file, tmp_path, **kw):
    cfg = Config.load(settings_file, ["source.type=csv_dir", f"export.directory={tmp_path}"])
    return cfg.copy_with(**kw) if kw else cfg


def test_end_to_end_csv(settings_file, tmp_path, tables):
    write_csv_dataset(tmp_path / "raw")
    cfg = _cfg(settings_file, tmp_path, source__csv_dir=str(tmp_path / "raw"))
    ctx = run_pipeline(cfg)
    res = ctx.tables["best_case_result"]
    assert len(res) > 0
    assert (tmp_path / "best_case.xlsx").exists()
    xl = pd.read_excel(tmp_path / "best_case.xlsx", sheet_name=None)
    assert set(xl) == {"best_case", "approaches"} and len(xl["best_case"]) == len(res)
    assert (tmp_path / "intermediate" / "best_sections.csv").exists()
    # only new-design wells survive and the old-design / unfinished logic holds
    tl = ctx.tables["time_log_final"]
    assert not {"SPH-99", "JR-11"} & set(tl["wellname"])
    secs = ctx.tables["sections"]
    assert "12 1/4" not in set(secs[secs.wellname == "SPH-03"]["code4"])  # unfinished well loses its last section
    assert set(ctx.tables["best_sections"]["category"]) == {"SPH", "JR"}
    # every result row lies inside the formation range it was assigned to
    assert (res["depthstart"] <= res["depthend"]).all()
    assert (res["depthstart"] >= res["depthdrillingtop"]).all() and (res["depthend"] <= res["depthdrillingbtm"]).all()
    # times of day are consistent: the end of one activity is the start of the next
    d = tl[(tl.wellname == "SPH-01") & (tl.dttmstart_date == tl.dttmstart_date.min())].sort_values("sysseq")
    assert list(d["dttmend_time"])[:-1] == list(d["dttmstart_time"])[1:]


def test_per_table_and_sql_join_modes_agree(settings_file, tmp_path, tables):
    results = {}
    for mode in ("per_table", "sql_join"):
        cfg = _cfg(settings_file, tmp_path / mode, queries__mode=mode, source__type="database")
        registry = QueryRegistry(cfg.path("queries.file"))
        src = SqliteSource(cfg, registry, tables)
        ctx = run_pipeline(cfg, source=src)
        results[mode] = ctx
    a, b = results["per_table"].tables, results["sql_join"].tables
    for name in ("time_log_final", "best_case_result", "sections"):
        cols = sorted(a[name].columns)
        assert cols == sorted(b[name].columns), name
        key = list(a[name].columns)
        x = a[name][key].astype(str).sort_values(key).reset_index(drop=True)
        y = b[name][key].astype(str).sort_values(key).reset_index(drop=True)
        pd.testing.assert_frame_equal(x, y)


def test_stage_selection_cache_and_override(settings_file, tmp_path, tables):
    write_csv_dataset(tmp_path / "raw")
    cfg = _cfg(settings_file, tmp_path, source__csv_dir=str(tmp_path / "raw"))
    cache = tmp_path / "cache"
    run_pipeline(cfg, cache_dir=cache)
    # resume from a later stage using the cache
    ctx = run_pipeline(cfg, start_from="sections", cache_dir=cache, only=["sections", "best_case"])
    assert len(ctx.tables["best_case_result"]) > 0
    # override a stage with user code
    (tmp_path / "mystage.py").write_text(
        "def custom_start_end(ctx):\n    ctx.tables['time_log_timed'] = ctx.tables['time_log_clean']\n"
    )
    import sys
    sys.path.insert(0, str(tmp_path))
    cfg2 = cfg.copy_with(pipeline__overrides={"start_end": "mystage:custom_start_end"})
    ctx2 = run_pipeline(cfg2, source=CsvDirSource(tmp_path / "raw", QueryRegistry(cfg.path("queries.file"))))
    assert ctx2.tables["time_log_timed"].equals(ctx2.tables["time_log_clean"])


def test_switching_approaches_off_and_database_selection(settings_file, tmp_path):
    write_csv_dataset(tmp_path / "raw")
    cfg = _cfg(settings_file, tmp_path, source__csv_dir=str(tmp_path / "raw"), approaches__enabled=False)
    ctx = run_pipeline(cfg)
    assert "approaches" not in ctx.tables
    cfg = cfg.copy_with(database_selection={"match": "any", "conditions": [
        {"column": "name", "operator": "WILDCARD", "value": "JR*"}]})
    ctx = run_pipeline(cfg)
    assert set(ctx.tables["time_log_final"]["wellname"]) <= {"JR-03", "JR-04"}


def test_query_contract_is_validated(settings_file, tmp_path):
    cfg = Config.load(settings_file)
    reg = QueryRegistry(cfg.path("queries.file"))
    with pytest.raises(QueryError, match="must return column"):
        reg.validate("well_header", pd.DataFrame({"idwell": [1]}))
    with pytest.raises(QueryError):
        reg.plan("nope")
    with pytest.raises(ConfigError):
        Config.load(settings_file, ["oops"])


def test_database_source_requires_credentials(settings_file, monkeypatch):
    monkeypatch.delenv("BEST_CASE_DB_PASSWORD", raising=False)
    cfg = Config.load(settings_file)
    src = DatabaseSource(cfg, QueryRegistry(cfg.path("queries.file")))
    with pytest.raises(ConfigError, match="environment variables"):
        src.list_databases()
