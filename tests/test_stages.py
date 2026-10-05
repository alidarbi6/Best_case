import datetime as dt

import numpy as np
import pandas as pd

from best_case.stages.formation_split import split_by_formation
from best_case.stages.formations import formation_depths
from best_case.stages.merge_time_log import merge_time_log
from best_case.stages.sections import build_sections, completed_hole_sections
from best_case.stages.start_end import compute_start_end
from best_case.stages.best_case import best_case_result, best_case_time_log, best_sections
from best_case.stages.approaches import build_approaches
from best_case.stages.drilling_parameters import drilling_parameters


def _t(h, m=0):
    return dt.time(h, m)


def test_start_end_running_total_within_a_day(cfg):
    df = pd.DataFrame({
        "idwell": ["w"] * 4, "dttmstart_date": pd.to_datetime(["2024-01-01"] * 4),
        "sysseq": [2, 1, 3, 4], "duration": [6.0, 12.0, 6.0, np.nan],
        "dttmstart_time": [_t(6)] * 4, "dttmend_time": [_t(0)] * 4,
    })
    out = compute_start_end(df, cfg)
    assert len(out) == 3  # row without duration dropped
    assert out["sysseq"].tolist() == [1, 2, 3]
    assert out["dttmstart_time"].tolist() == [_t(6), _t(18), _t(0)]
    # 24 h in total -> one minute shorter, wraps over midnight: 6:00 + 23:59 = 05:59
    assert out["dttmend_time"].tolist() == [_t(18), _t(0), _t(5, 59)]


def test_start_end_forward_variant_is_selectable(cfg):
    df = pd.DataFrame({"idwell": ["w"] * 2, "dttmstart_date": pd.to_datetime(["2024-01-01"] * 2), "sysseq": [1, 2],
                       "duration": [1.0, 2.0], "dttmstart_time": [_t(0)] * 2, "dttmend_time": [_t(0)] * 2})
    out = compute_start_end(df, cfg.copy_with(start_end__cumulative="forward"))
    assert out["dttmend_time"].tolist() == [_t(3), _t(2)]


def test_formation_depths_bottom_filling_cleaning_and_rank(cfg):
    raw = pd.DataFrame({
        "idwell": ["w"] * 5, "idrecparent": "p", "idrec": list("abcde"), "depthdrillingtop": [0.0, 1500.0, 2600.0, 3200.0, 10.0],
        "depthdrillingbtm": [1500.0, np.nan, np.nan, np.nan, np.nan],
        "depthfinalsource": "x", "formname": [" GACHSARAN Fm ", "Fahliyan", "IL-1", "TD", None], "layername": None,
    })
    wells = pd.DataFrame({"idwell": ["w"], "wellname": ["SPH-01"]})
    out = formation_depths(raw, wells, cfg)
    assert out["formname"].tolist() == ["gachsaran", "fahliyan", "ilam"]
    assert out["depthdrillingbtm"].tolist() == [1500.0, 2600.0, 3200.0]  # bottom = top of the next (deeper) one
    assert out["form_seq"].tolist() == [1, 2, 3]


def test_formation_split_duplicates_a_row_that_spans_two_formations(cfg):
    params = pd.DataFrame({"idwell": ["w", "w"], "depthstart": [100.0, 1400.0], "depthend": [200.0, 1600.0]})
    forms = pd.DataFrame({"idwell": ["w", "w"], "formname": ["g", "f"], "depthdrillingtop": [0.0, 1500.0],
                          "depthdrillingbtm": [1500.0, 2600.0], "form_seq": [1, 2]})
    out = split_by_formation(params, forms, cfg)
    assert len(out) == 3
    span = out[out["Duplicate Status"] != "unique"].sort_values("depthstart")
    assert span[["formname", "depthstart", "depthend"]].values.tolist() == [["g", 1400.0, 1500.0], ["f", 1500.0, 1600.0]]


def test_merge_fills_formation_previous_then_next_and_drops_formation_rows(cfg):
    timed = pd.DataFrame({
        "idwell": ["w"] * 3, "idrec": ["a", "b", "c"], "dttmstart_date": pd.to_datetime(["2024-01-01", "2024-01-03", "2024-01-05"]),
    })
    stub = pd.DataFrame({"idwell": ["w", "w"], "dttmstart_date": pd.to_datetime(["2024-01-02", "2024-01-04"]),
                         "formname": ["f1", "f2"], "form_seq": [1, 2], "wellname": "x"})
    out = merge_time_log(timed, stub, cfg)
    assert out["idrec"].tolist() == ["a", "b", "c"]
    assert out["formname"].tolist() == ["f1", "f1", "f2"]  # "a" gets the *next* value (no previous exists)


def test_completed_sections_drop_smallest_section_of_unfinished_well(cfg):
    pairs = pd.DataFrame({
        "code4": ["17 1/2", "12 1/4", "8 1/2", "COMPLETION", "17 1/2", "12 1/4"],
        "wellname": ["A", "A", "A", "A", "B", "B"],
    })
    out = completed_hole_sections(pairs, cfg)
    assert sorted(out[out.wellname == "A"].code4) == ["12 1/4", "17 1/2", "8 1/2", "COMPLETION"]
    assert out[out.wellname == "B"].code4.tolist() == ["17 1/2"]  # B has no completion: 12 1/4 (smallest) dropped


def _mini_time_log():
    rows = []
    for well, dur in (("SPH-01", 10.0), ("SPH-02", 4.0), ("JR-03", 6.0)):
        rows.append({"idwell": well, "idrec": "r", "wellname": well, "code1": "4", "code2": "P", "code4": "12 1/4",
                     "formname": "g", "duration": dur, "opscategory": "2", "dttmend_date": pd.Timestamp("2024-01-01")})
        rows.append({"idwell": well, "idrec": "r", "wellname": well, "code1": "5", "code2": "P", "code4": "COMPLETION",
                     "formname": "g", "duration": 1.0, "opscategory": "2", "dttmend_date": pd.Timestamp("2024-01-02")})
    return pd.DataFrame(rows)


def test_best_case_picks_minimum_per_category_and_joins_parameters(cfg):
    sections = build_sections(_mini_time_log(), cfg)
    assert set(sections["category"]) == {"SPH", "JR"}
    best = best_sections(sections, cfg)
    assert best.set_index(["category", "code4"])["wellname"].to_dict() == {("SPH", "12 1/4"): "SPH-02", ("JR", "12 1/4"): "JR-03"}
    tl = _mini_time_log()
    best_tl = best_case_time_log(tl, best, cfg)
    assert set(best_tl["wellname"]) == {"SPH-02", "JR-03"} and len(best_tl) == 2
    drill = pd.DataFrame({"wellname": ["SPH-02", "SPH-01", "JR-03"], "formname": "g",
                          "dttmend_date": pd.Timestamp("2024-01-01"), "depthstart": [1.0, 2.0, 3.0]})
    res = best_case_result(drill, best_tl)
    assert res["wellname"].tolist() == ["SPH-02", "JR-03"]


def test_optional_post_filters_can_be_switched_on(cfg):
    sections = build_sections(_mini_time_log(), cfg)
    best = best_sections(sections, cfg)
    on = cfg.copy_with()
    for f in on.data["best_case"]["post_filters"]:
        if f["name"] == "single_well_test":
            f["enabled"] = True
            f["conditions"] = [{"column": "wellname", "operator": "EQ", "value": "jr-03", "case_sensitive": False}]
    assert set(best_case_time_log(_mini_time_log(), best, on)["wellname"]) == {"JR-03"}


def test_approaches_produce_all_three_labels(cfg):
    sections = build_sections(_mini_time_log(), cfg)
    out = build_approaches(sections, cfg)
    assert set(out["approach"]) == {"HS", "Code1", "OPSCAT"}
    hs = out[(out.approach == "HS") & (out.category == "SPH")]
    assert hs["Sum(duration)"].iloc[0] == 4.0 / 24


def test_drilling_parameters_concatenates_components_and_drops_rows_without_depth(cfg):
    base = {"idwell": "w", "idrecparent": "p", "idrec": "s", "bitno": "1", "bittfa": 1.0, "com": "c", "des": "d", "stringno": 1,
            "depthend": 20.0, "depthstart": 10.0, "dttmend": pd.Timestamp("2024-01-01 10:00"), "dttmstart": pd.Timestamp("2024-01-01 08:00"),
            "wellname": "SPH-01", "jobtyp": "Drilling - Original", "wearbearing": None, "weardull": "1", "weargauge": None,
            "wearinner": None, "wearloc": None, "wearother": None, "wearouter": None, "wearpulled": None, "grade": "G",
            "hoursstart": 1.0, "joints": 2, "length": 3.5, "make": "m", "model": "x"}
    rows = [{**base, "com_DrillstringComp": "a", "des_DrillstringComp": "bit", "sysseq": 2},
            {**base, "com_DrillstringComp": "b", "des_DrillstringComp": "motor", "sysseq": 1},
            {**base, "idrec": "s2", "depthend": np.nan, "depthstart": np.nan, "sysseq": 1,
             "com_DrillstringComp": "z", "des_DrillstringComp": "z"}]
    out = drilling_parameters(pd.DataFrame(rows), pd.DataFrame({"idwell": ["w"]}), cfg)
    assert len(out) == 1
    assert out["des_DrillstringComp"].iloc[0] == "motor, bit"  # ordered by sysseq
    assert out["length"].iloc[0] == "3.5, 3.5" and out["sysseq"].iloc[0] == "1, 2"
