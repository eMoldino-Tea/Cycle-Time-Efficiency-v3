"""Regression + unit tests for cte_core.

The BASELINE_* constants below were measured from the shipped demo data
generator BEFORE any v3 change. They exist so that adding Country and
multi-part tools can be proven not to have moved a single number.
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cte_core as core


def raw_load(**kwargs):
    """Call load_base_data without Streamlit's cache wrapper."""
    fn = getattr(core.load_base_data, "__wrapped__", core.load_base_data)
    return fn(**kwargs)


BASELINE_ROWS = 8121
BASELINE_SHOTS = 21185467
BASELINE_USED_HOURS = 22439.685969
BASELINE_EXPECTED_HOURS = 21206.694132
BASELINE_WEIGHTED_EFF = 94.4717757403
BASELINE_TOOLS = 78
BASELINE_SUPPLIERS = 14


@pytest.fixture(scope="module")
def demo():
    return raw_load(version=11)


def test_demo_data_shape_is_unchanged(demo):
    assert len(demo) == BASELINE_ROWS
    assert demo["Tooling"].nunique() == BASELINE_TOOLS
    assert demo["Supplier"].nunique() == BASELINE_SUPPLIERS


def test_demo_data_math_is_unchanged(demo):
    assert int(demo["Total_Shots"].sum()) == BASELINE_SHOTS
    assert demo["Used_Hours"].sum() == pytest.approx(BASELINE_USED_HOURS, abs=1e-6)
    assert demo["Expected_Hours"].sum() == pytest.approx(BASELINE_EXPECTED_HOURS, abs=1e-6)
    assert core.calc_weighted_eff(demo) == pytest.approx(BASELINE_WEIGHTED_EFF, abs=1e-9)


def test_regions_are_the_four_canonical_values(demo):
    assert set(demo["Region"].unique()) == {"APAC", "Europe", "North America", "LATAM"}


def test_ensure_geo_columns_adds_country_and_region():
    df = pd.DataFrame({"Plant": ["Plant 5 (CN)", "Plant 3 (DE)", "Plant 7 (BR)"]})
    out = core.ensure_geo_columns(df)
    assert out["Country"].tolist() == ["China", "Germany", "Brazil"]
    assert out["Region"].tolist() == ["APAC", "Europe", "LATAM"]


def test_ensure_geo_columns_is_idempotent_and_non_destructive():
    df = pd.DataFrame({"Plant": ["Plant 5 (CN)"], "Country": ["Custom"], "Region": ["Custom"]})
    out = core.ensure_geo_columns(df)
    assert out["Country"].tolist() == ["Custom"]
    assert out["Region"].tolist() == ["Custom"]


def test_unknown_plant_falls_back_without_raising():
    out = core.ensure_geo_columns(pd.DataFrame({"Plant": ["Plant 99 (ZZ)"]}))
    assert out["Country"].tolist() == ["Unknown"]
    assert out["Region"].tolist() == ["Other"]


def test_demo_data_has_country_column(demo):
    assert "Country" in demo.columns
    assert set(demo["Country"].unique()) == {
        "Mexico", "United States", "Germany", "Poland", "China", "Vietnam", "Brazil",
    }


def test_a_supplier_can_span_multiple_countries(demo):
    spans = demo.groupby("Supplier")["Country"].nunique()
    assert (spans > 1).any(), "Supplier→Country must not be modelled as a strict tree"


def test_some_tools_make_more_than_one_part(demo):
    parts_per_tool = demo.groupby("Tooling")["Part"].nunique()
    multi = int((parts_per_tool > 1).sum())
    assert multi >= 10, f"expected ~20-30% of {len(parts_per_tool)} tools multi-part, got {multi}"
    assert parts_per_tool.max() >= 3, "expected at least one three-part tool"


def test_multi_part_tools_did_not_disturb_the_math(demo):
    # Identical assertions to the baseline lock: Part labels moved, numbers did not.
    assert demo["Used_Hours"].sum() == pytest.approx(BASELINE_USED_HOURS, abs=1e-6)
    assert core.calc_weighted_eff(demo) == pytest.approx(BASELINE_WEIGHTED_EFF, abs=1e-9)


def test_time_range_presets_have_no_last_90_days():
    assert core.TIME_RANGE_PRESETS == [
        "Last 7 Days", "Last 30 Days", "Last Quarter", "Last 12 Months", "Custom Range",
    ]


def test_last_quarter_is_the_previous_complete_calendar_quarter():
    # 2026-07-06 sits in Q3 2026, so "Last Quarter" is Q2 2026 (Apr-Jun).
    start, end = core.resolve_time_range("Last Quarter", pd.Timestamp("2026-07-06"))
    assert start == pd.Timestamp("2026-04-01")
    assert end.date() == pd.Timestamp("2026-06-30").date()
    assert end > pd.Timestamp("2026-06-30 23:00:00")


def test_last_quarter_wraps_across_the_year_boundary():
    start, end = core.resolve_time_range("Last Quarter", pd.Timestamp("2026-01-15"))
    assert start == pd.Timestamp("2025-10-01")
    assert end.date() == pd.Timestamp("2025-12-31").date()


def test_rolling_presets():
    mx = pd.Timestamp("2026-07-06")
    assert core.resolve_time_range("Last 7 Days", mx)[0] == pd.Timestamp("2026-06-29")
    assert core.resolve_time_range("Last 30 Days", mx)[0] == pd.Timestamp("2026-06-06")
    assert core.resolve_time_range("Last 12 Months", mx)[0] == pd.Timestamp("2025-07-06")
    assert core.resolve_time_range("Last 7 Days", mx)[1] == mx


def test_unknown_preset_raises():
    with pytest.raises(ValueError):
        core.resolve_time_range("Last 90 Days", pd.Timestamp("2026-07-06"))
