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
