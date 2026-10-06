import pandas as pd

from best_case.stages.report import build_tables, hole_size, section_label
from best_case.testing.synthetic import write_csv_dataset
from best_case.pipeline import run_pipeline
from best_case.config import Config


def _sections():
    rows = []

    def add(well, cat, c1, hours, form="g"):
        rows.append({"wellname": well, "category": cat, "code4": "12 1/4", "code1": c1, "duration": hours,
                     "formname": form})

    add("A", "SPH", "4", 48); add("A", "SPH", "5", 24)          # A: 3 d (2 + 1)
    add("B", "SPH", "4", 24); add("B", "SPH", "5", 72)          # B: 4 d (1 + 3)
    add("C", "JR", "4", 24 * 5)                                 # C: 5 d, only activity 4
    return pd.DataFrame(rows)


def test_hole_size_and_label():
    assert hole_size("12 1/4") == 12.25 and hole_size("8 1/2") == 8.5 and hole_size("24") == 24
    assert section_label("12 1/4") == "12 1/4″"


def test_approach_definitions_match_the_presentation(cfg):
    sec = _sections()
    best = pd.DataFrame({"code4": ["12 1/4"], "wellname": ["A"], "formname": ["g"], "category": ["SPH"],
                         "Sum(duration)": [72.0], "approach": ["FOR_HS"]})
    t = {"sections": sec, "best_sections": best, "best_time_log": pd.DataFrame(
        {"code4": [], "com": [], "wellname": [], "formname": [], "dttmend_date": pd.to_datetime([]), "sysseq": [],
         "duration": []}),
        "best_case_result": pd.DataFrame({"wellname": [], "formname": [], "dttmend_date": pd.to_datetime([])})}
    out = build_tables(t, cfg.copy_with(report__hole_sections=[]))
    comp = out["Comparison"]
    assert list(comp.columns) == ["Hole Section", "Approach I", "Approach II", "Approach Combination"]
    row = comp.iloc[0]
    assert row["Approach I"] == 3.0                    # min over wells of the section total
    assert row["Approach II"] == 2.0                   # min(code1 4)=1 + min(code1 5)=1
    assert row["Approach Combination"] == 2.0
    assert comp.iloc[-1]["Hole Section"] == "Total"
    assert out["Approach I winners"]["Best Well (Approach I)"].tolist() == ["A"]
    f = out["Duration by Formation"]
    assert list(f.columns) == ["Hole Section", "Well", "Type", "Formation", "Duration (Days)"]
    assert set(f["Formation"]) == {"G"}


def test_pipeline_writes_report_files(settings_file, tmp_path):
    write_csv_dataset(tmp_path / "raw")
    cfg = Config.load(settings_file, ["source.type=csv_dir", "queries.mode=per_table", "time_log.well_filter_mode=include",
                                      f"export.directory={tmp_path}", f"source.csv_dir={tmp_path / 'raw'}",
                                      "report.hole_sections=[]"])
    run_pipeline(cfg)
    rep = tmp_path / "report"
    assert (rep / "best_case_report.xlsx").exists()
    assert {"slide06_approach1_by_well.png", "slide07_approach1_vs_2.png", "slide09_all_approaches.png"} <= {
        f.name for f in rep.glob("*.png")}
    sheets = pd.read_excel(rep / "best_case_report.xlsx", sheet_name=None)
    assert "8 Comparison" in sheets and "14 Drilling Parameters II" in sheets
    from openpyxl import load_workbook

    wb = load_workbook(rep / "best_case_report.xlsx")
    assert len(wb["6 Approach I - Duration by Well"]._charts) == 1  # native Excel chart
