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


def test_every_level_declares_the_exact_required_trend_dim():
    expected_trend_dim = {
        "global": "Supplier",
        "region": "Supplier",
        "country": "Supplier",
        "supplier": "Tooling",
        "type_all": "Tooling Type",
        "type": "Tooling",
        "part_all": "Part",
        "part": "Tooling",
        "part_tools": "Tooling",
        "tool": "Tooling",
    }
    required_keys = {"label", "col", "child", "trend_dim", "entity_noun"}

    assert set(nav.LEVELS.keys()) == set(expected_trend_dim.keys())
    for key, cfg in nav.LEVELS.items():
        assert required_keys.issubset(cfg.keys()), key
        assert cfg["trend_dim"] == expected_trend_dim[key], key


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


# ---- session-state-bound functions ----------------------------------------
@pytest.fixture
def session_state(monkeypatch):
    """A plain dict standing in for st.session_state, isolated per test so
    stacks don't leak between tests."""
    state = {}
    monkeypatch.setattr(nav.st, "session_state", state)
    return state


def test_get_stack_initializes_to_the_global_root(session_state):
    assert nav.get_stack() == [("global", None)]
    assert session_state[nav._STACK_KEY] == [("global", None)]


def test_get_stack_returns_the_same_stack_on_repeated_calls(session_state):
    first = nav.get_stack()
    first.append(("region", "APAC"))
    assert nav.get_stack() == [("global", None), ("region", "APAC")]


def test_push_then_current_returns_the_pushed_frame(session_state):
    nav.push("region", "APAC")
    assert nav.current() == ("region", "APAC")
    assert nav.current_root() == "global"
    assert nav.get_stack() == [("global", None), ("region", "APAC")]


def test_pop_to_truncates_to_the_given_index_inclusive(session_state):
    nav.push("region", "APAC")
    nav.push("country", "China")
    nav.push("supplier", "Foxconn")
    nav.pop_to(1)
    assert nav.get_stack() == [("global", None), ("region", "APAC")]
    assert nav.current() == ("region", "APAC")


def test_pop_to_never_leaves_an_empty_stack(session_state):
    nav.push("region", "APAC")
    nav.pop_to(-1)
    assert nav.get_stack() == [("global", None)]

    nav.push("region", "APAC")
    nav.push("country", "China")
    nav.pop_to(-100)
    assert len(nav.get_stack()) >= 1
    assert nav.get_stack()[0] == ("global", None)


def test_set_root_discards_an_existing_deep_stack(session_state):
    nav.push("region", "APAC")
    nav.push("country", "China")
    nav.set_root("type_all")
    assert nav.get_stack() == [("type_all", None)]
    assert nav.current_root() == "type_all"


def test_keyns_differs_for_structurally_different_stacks(session_state):
    # Both stacks naively join to the identical string "a-1_b-2" via
    # f"{lvl}-{val}" joined with "_" -- a one-frame stack whose value
    # happens to contain the frame separator, versus a genuinely two-frame
    # stack. keyns() must still tell them apart.
    stack_one = [("a", "1_b-2")]
    stack_two = [("a", "1"), ("b", "2")]

    session_state[nav._STACK_KEY] = stack_one
    key_one = nav.keyns()

    session_state[nav._STACK_KEY] = stack_two
    key_two = nav.keyns()

    assert key_one != key_two


def test_keyns_is_deterministic_for_the_same_stack(session_state):
    stack = [("global", None), ("region", "APAC"), ("supplier", "Bosch Tooling")]
    session_state[nav._STACK_KEY] = list(stack)
    first = nav.keyns()
    session_state[nav._STACK_KEY] = list(stack)
    second = nav.keyns()
    assert first == second
