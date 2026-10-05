import numpy as np
import pandas as pd
import pytest

from best_case.engine.expr import ExpressionError, RuleSet, evaluate_expression, tokenize


def test_string_functions_match_knime_examples():
    df = pd.DataFrame({"c": [' 12 1/4" ', "Move/R/U", None]})
    out = evaluate_expression(df, 'strip(lowerCase(replaceChars($c$, "\\"", "")))')
    assert out.tolist()[:2] == ["12 1/4", "move/r/u"]
    assert pd.isna(out.iloc[2])  # missing in -> missing out
    cap = evaluate_expression(pd.DataFrame({"j": ["drilling - original", "r/d & move"]}), 'capitalize($j$, "/ -")')
    assert cap.tolist() == ["Drilling - Original", "R/D & Move"]


def test_math_with_if_and_int_conversion():
    df = pd.DataFrame({"s": [0.5, 1.0, 24.0, 23.99999]})
    out = evaluate_expression(df, "if(floor($s$) == 24, $s$ * 60 - 1, $s$ * 60)", True)
    assert out.tolist() == [30, 60, 1439, 1440]


def test_rules_first_match_wins_and_default():
    df = pd.DataFrame({"d": ["Sidetrack 1", "x ST 1", "plain", None]})
    rs = RuleSet(
        ['// comment', '$d$ LIKE "*ST*1" OR $d$ LIKE "*Sidetrack*1" => "ST #1"', "TRUE => $d$"]
    )
    out = rs.evaluate(df)
    assert out.tolist()[:3] == ["ST #1", "ST #1", "plain"]
    assert pd.isna(out.iloc[3])


def test_rules_without_default_give_missing_and_like_is_case_sensitive():
    df = pd.DataFrame({"w": ["SPH-01", "sph-02", "JR-03", "XX"]})
    out = RuleSet(['$w$ LIKE "SPH*" => "SPH"', '$w$ LIKE "JR*" => "JR"']).evaluate(df)
    assert out.tolist()[0] == "SPH" and pd.isna(out.iloc[1]) and out.iloc[2] == "JR" and pd.isna(out.iloc[3])


def test_comparison_with_missing_is_false_and_missing_operator():
    df = pd.DataFrame({"a": [1.0, np.nan, 5.0], "b": [2.0, 2.0, np.nan]})
    assert RuleSet(["$a$ < $b$ => TRUE"]).matches(df).tolist() == [True, False, False]
    assert RuleSet(["NOT MISSING $a$ => TRUE"]).matches(df).tolist() == [True, False, True]
    assert RuleSet(["MISSING $b$ => TRUE"]).matches(df).tolist() == [False, False, True]


def test_range_rule_of_formation_split():
    df = pd.DataFrame({"depthstart": [10.0, 90.0, 500.0], "depthend": [20.0, 120.0, 600.0],
                       "depthdrillingtop": [0.0, 0.0, 0.0], "depthdrillingbtm": [100.0, 100.0, 100.0]})
    rs = RuleSet(["$depthstart$ >= $depthdrillingtop$ AND $depthstart$ <= $depthdrillingbtm$ => TRUE",
                  "$depthend$ >= $depthdrillingtop$ AND $depthend$ <= $depthdrillingbtm$ => TRUE"])
    assert rs.matches(df).tolist() == [True, True, False]


def test_column_name_with_parentheses_and_errors():
    df = pd.DataFrame({"Sum(duration)": [1.0, 2.0]})
    assert evaluate_expression(df, "$Sum(duration)$ / 24").round(4).tolist() == [0.0417, 0.0833]
    with pytest.raises(ExpressionError):
        evaluate_expression(df, "$nope$ + 1")
    with pytest.raises(ExpressionError):
        RuleSet(["TRUE"])
    assert [t.kind for t in tokenize('$a$ = "x"')][:3] == ["col", "op", "str"]
