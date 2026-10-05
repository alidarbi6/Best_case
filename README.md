# Best Case Workflow (Python)

Python port of the KNIME *Drilling Operations Best Case* workflow: finds, per hole section and
formation, the best (shortest) completed operation among the new-design wells and extracts the
matching drilling parameters.

* Persian documentation: [`docs/README_fa.md`](docs/README_fa.md)
* Everything that may change lives in `config/`: SQL queries (one file each), cleaning rules
  (KNIME rule syntax), lookups and parameters.
* Every pipeline stage is a separate module in `src/best_case/stages/` and can be replaced
  (`pipeline.overrides` in `settings.yaml`).

```bash
pip install -e .[mssql,test]
export BEST_CASE_DB_PASSWORD=...        # never stored in files
python -m best_case run --settings config/settings.yaml
python -m best_case demo-data && python -m best_case run --set source.type=csv_dir   # offline demo
python -m pytest -q
```
