import numpy as np
import pandas as pd

from best_case.engine.ops import (Agg, RowFilterSpec, Select, concatenate, cross_join, distinct,
                                  duplicate_row_filter, group_apply, group_by, join, rank, remove_date,
                                  remove_time, row_filter)
from best_case.engine.sorting import natural_key, sort_dataframe


def test_join_selection_suffix_and_null_keys():
    left = pd.DataFrame({"k": ["a", "b", None], "v": [1, 2, 3], "x": [1, 1, 1]})
    right = pd.DataFrame({"k": ["a", None], "v": [10, 20], "y": [5, 6]})
    out = join(left, right, ["k"], how="left", right_select=Select(exclude=["k"]))
    assert list(out.columns) == ["k", "v", "x", "v (Right)", "y"]
    assert out["v (Right)"].tolist()[0] == 10 and out["v (Right)"].isna().tolist() == [False, True, True]
    assert len(join(left, right, ["k"], how="inner")) == 1  # missing keys never match


def test_join_include_nothing_is_semi_join_and_keeps_left_order():
    left = pd.DataFrame({"k": [3, 1, 2, 1]})
    right = pd.DataFrame({"k": [1, 3], "z": [0, 0]})
    out = join(left, right, ["k"], how="inner", right_select=Select(include=[]))
    assert out["k"].tolist() == [3, 1, 1] and list(out.columns) == ["k"]


def test_group_by_sum_concat_and_names():
    df = pd.DataFrame({"g": ["a", "a", None], "v": [1.0, 2.0, 5.0], "s": ["x", None, "z"], "n": [1.0, 2.0, 3.0]})
    out = group_by(df, ["g"], [Agg("v", "Sum"), Agg("s", "Concatenate", True), Agg("n", "Concatenate")],
                   name_policy="method")
    assert list(out.columns) == ["g", "Sum(v)", "Concatenate(s)", "Concatenate(n)"]
    assert out["Sum(v)"].tolist() == [3.0, 5.0]
    assert out["Concatenate(s)"].tolist() == ["x, ?", "z"]
    assert out["Concatenate(n)"].tolist() == ["1, 2", "3"]
    assert len(distinct(df, ["g"])) == 2


def test_duplicate_row_filter_modes():
    df = pd.DataFrame({"a": [1, 1, 2, 2, 2, 3], "v": [5, 3, 9, 9, 1, 7], "j": ["b", "a", "x", "x", "y", "z"]})
    flagged = duplicate_row_filter(df, ["a"], reference="v", selection="MINIMUM", remove_duplicates=False)
    assert flagged["Duplicate Status"].tolist() == ["duplicate", "chosen", "duplicate", "duplicate", "chosen", "unique"]
    assert duplicate_row_filter(df, ["a"], reference="v", selection="MINIMUM")["v"].tolist() == [3, 1, 7]
    assert duplicate_row_filter(df, ["a"], selection="FIRST")["v"].tolist() == [5, 9, 7]
    # ties -> first; string reference; exclude-style group (all columns except j)
    out = duplicate_row_filter(df, None, reference="j", selection="MINIMUM", exclude_cols=["j"])
    assert len(out) == 5  # the two identical (2, 9) rows collapse
    dup = pd.DataFrame({"a": [1, 1, None, None], "j": ["z", "a", "q", "p"]})
    res = duplicate_row_filter(dup, None, reference="j", selection="MINIMUM", exclude_cols=["j"])
    assert res["j"].tolist() == ["a", "p"]  # missing == missing forms a group


def test_sorter_natural_missing_handling():
    df = pd.DataFrame({"c": ["12 1/4", None, "8 1/2", "17 1/2", "COMPLETION"]})
    nat = sort_dataframe(df, ["c"], natural=True, missing_to_end=True)["c"].tolist()
    assert nat == ["8 1/2", "12 1/4", "17 1/2", "COMPLETION", None] or pd.isna(nat[-1])
    assert nat[:4] == ["8 1/2", "12 1/4", "17 1/2", "COMPLETION"]
    first = sort_dataframe(df, ["c"], natural=False)["c"].tolist()
    assert pd.isna(first[0])  # missing is the smallest value
    d = pd.DataFrame({"t": [1.0, np.nan, 3.0]})
    assert pd.isna(sort_dataframe(d, ["t"], ascending=False)["t"].iloc[-1])
    assert natural_key("8 1/2") < natural_key("12 1/4")


def test_sorter_is_stable_multi_column():
    df = pd.DataFrame({"a": [2, 1, 2, 1], "b": [1, 1, 1, 2], "o": [0, 1, 2, 3]})
    out = sort_dataframe(df, ["a", "b"], ascending=[True, False])
    assert out["o"].tolist() == [3, 1, 0, 2]


def test_rank_standard_competition():
    df = pd.DataFrame({"g": [1, 1, 1, 1], "t": [0.0, 10.0, 10.0, 20.0]})
    assert rank(df, "t", ["g"], "r")["r"].tolist() == [1, 2, 2, 4]


def test_row_filter_case_insensitive_missing_and_modes():
    df = pd.DataFrame({"c": ["Move", "move", "x", None], "p": ["P", "P", "p", "P"]})
    spec = {"match": "all", "conditions": [{"column": "c", "operator": "NEQ", "value": "move", "case_sensitive": False},
                                           {"column": "p", "operator": "EQ", "value": "P"}]}
    assert row_filter(df, spec)["c"].tolist() == []  # "x" has p == "p" (case-sensitive); missing never matches
    wc = {"conditions": [{"column": "c", "operator": "WILDCARD", "value": "MO*", "case_sensitive": False}]}
    assert len(row_filter(df, wc)) == 2
    assert len(row_filter(df, {**wc, "mode": "non_matching"})) == 2
    assert len(row_filter(df, {**wc, "enabled": False})) == 4


def test_group_apply_and_concatenate_and_cross():
    df = pd.DataFrame({"g": ["b", "a", "b"], "v": [1, 2, 3]})
    out = group_apply(df, ["g"], lambda g: g.iloc[1:])
    assert out["v"].tolist() == [3]
    assert len(concatenate([df, pd.DataFrame({"z": [1]})])) == 4
    assert len(cross_join(df, pd.DataFrame({"x": [1, 2]}))) == 6


def test_modify_date_time():
    df = pd.DataFrame({"t": pd.to_datetime(["2024-01-02 13:05:07", None])})
    d = remove_time(df, ["t"])
    assert d["t_date"].iloc[0] == pd.Timestamp("2024-01-02")
    tt = remove_date(df, ["t"])
    assert str(tt["t_time"].iloc[0]) == "13:05:07" and tt["t_time"].iloc[1] is None
