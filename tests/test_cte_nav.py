import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cte_nav as nav


@pytest.fixture
def frame():
    return pd.DataFrame({
        "Region": ["APAC", "APAC", "Europe", "APAC"],
        "Country": ["China", "Vietnam", "Germany", "China"],
        "Supplier": ["Foxconn", "Foxconn", "Bosch Tooling", "Jabil"],
        "Tooling": ["TL-001", "TL-002", "TL-003", "TL-004"],
        "Tooling Type": ["Injection Molding"] * 4,
        "Part": ["Part-001", "Part-002", "Part-003", "Part-001"],
    })


def test_level_registry_chain_is_complete():
    assert nav.LEVELS["global"]["child"] == "region"
    assert nav.LEVELS["region"]["child"] == "country"
    assert nav.LEVELS["country"]["child"] == "supplier"
    assert nav.LEVELS["supplier"]["child"] == "tool"
    assert nav.LEVELS["tool"]["child"] is None
    assert nav.LEVELS["part"]["child"] == "part_tools"
    assert nav.LEVELS["part_tools"]["child"] == "tool"


def test_every_level_declares_a_trend_dim():
    for key, cfg in nav.LEVELS.items():
        assert cfg["trend_dim"] in {"Supplier", "Tooling", "Tooling Type", "Part"}, key


def test_scope_df_applies_each_frame_in_order(frame):
    stack = [("global", None), ("region", "APAC"), ("country", "China")]
    out = nav.scope_df(frame, stack)
    assert sorted(out["Tooling"]) == ["TL-001", "TL-004"]


def test_scope_df_root_frames_do_not_filter(frame):
    assert len(nav.scope_df(frame, [("global", None)])) == 4
    assert len(nav.scope_df(frame, [("part_all", None)])) == 4


def test_scope_df_down_to_a_single_tool(frame):
    stack = [("global", None), ("region", "APAC"), ("country", "China"),
             ("supplier", "Foxconn"), ("tool", "TL-001")]
    out = nav.scope_df(frame, stack)
    assert out["Tooling"].tolist() == ["TL-001"]


def test_scope_df_cross_cutting_part_path_ignores_geography(frame):
    stack = [("part_all", None), ("part", "Part-001")]
    out = nav.scope_df(frame, stack)
    assert sorted(out["Tooling"]) == ["TL-001", "TL-004"]


def test_crumb_labels_uses_values_after_the_root():
    stack = [("global", None), ("region", "APAC"), ("supplier", "Foxconn")]
    assert nav.crumb_labels(stack) == [(0, "Global"), (1, "APAC"), (2, "Foxconn")]


def test_scope_df_on_missing_column_is_a_no_op(frame):
    out = nav.scope_df(frame.drop(columns=["Country"]), [("global", None), ("country", "China")])
    assert len(out) == 4
