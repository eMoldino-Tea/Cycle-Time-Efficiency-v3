"""End-to-end smoke tests for the v3 drill-down app.

These run the REAL app script headlessly via Streamlit's AppTest harness and
seed the navigation stack directly, which is the only practical way to
exercise the drill-down levels: the drill affordance is a row click inside
Streamlit's canvas-based dataframe grid, which synthetic browser clicks
cannot reach.

Each level is asserted to render without raising and to produce the panels
its spec section calls for.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from streamlit.testing.v1 import AppTest  # noqa: E402

import cte_nav as nav  # noqa: E402

APP = os.path.join(ROOT, "Cycle-Time-Efficiency-v3.py")

# One representative navigation stack per level in cte_nav.LEVELS. Values are
# taken from the demo dataset: Foxconn operates in China and Mexico, TL-001 is
# a two-part tool, Part-001 is made by more than one tool.
STACKS = {
    "global": [("global", None)],
    "region": [("global", None), ("region", "APAC")],
    "country": [("global", None), ("region", "APAC"), ("country", "China")],
    "supplier": [("global", None), ("supplier", "Foxconn")],
    "tool": [("global", None), ("supplier", "Foxconn"), ("tool", "TL-001")],
    "type_all": [("type_all", None)],
    "type": [("type_all", None), ("type", "Injection Molding")],
    "part_all": [("part_all", None)],
    "part": [("part_all", None), ("part", "Part-001")],
    "part_tools": [("part_all", None), ("part", "Part-001"), ("part_tools", None)],
}


def run_at(stack=None):
    at = AppTest.from_file(APP, default_timeout=300)
    if stack is not None:
        at.session_state[nav._STACK_KEY] = list(stack)
    at.run()
    return at


def all_text(at):
    return "\n".join(
        [m.value for m in at.markdown]
        + [c.value for c in at.caption]
        + [h.value for h in at.subheader]
    )


def test_every_level_in_the_registry_has_a_representative_stack():
    assert set(STACKS) == set(nav.LEVELS), "a level was added without a smoke test"


@pytest.mark.parametrize("level", sorted(STACKS))
def test_level_renders_without_raising(level):
    at = run_at(STACKS[level])
    assert not at.exception, f"{level} raised: {at.exception}"


def test_global_overview_shows_six_tiles_and_region_pies():
    at = run_at(STACKS["global"])
    text = all_text(at)
    for tile in ("TOTAL TOOLS", "FAST TOOLS (GAIN)", "WITHIN TOOLS (NEUTRAL)",
                 "SLOW TOOLS (LOSS)", "SAVING OPPORTUNITY", "LOSS"):
        assert tile in text.upper(), f"missing tile: {tile}"
    # one small-multiple pie per region, plus both trend charts and the rankings
    assert len(at.get("plotly_chart")) >= 4 + 2


def test_both_trend_graphs_appear_at_every_level():
    for level in sorted(STACKS):
        if level == "part_tools":
            continue  # spec 7.1 is a plain tool list, no trend block
        at = run_at(STACKS[level])
        text = all_text(at)
        assert "ACT-Weighted Deviation" in text, f"{level} missing trend graph 1"
        assert "CT Split &amp; Shot Trend" in text or "CT Split & Shot Trend" in text, \
            f"{level} missing trend graph 2"


def test_trend_graph_2_stat_line_and_footnote():
    at = run_at(STACKS["global"])
    text = all_text(at)
    assert "CT Compliance" in text
    assert "active months" in text
    # the footnote that keeps CT Compliance distinct from CT Efficiency
    assert "different measure from the Cycle Time Efficiency" in text


def test_tool_report_shows_identity_and_a_dropdown_for_a_multi_part_tool():
    at = run_at(STACKS["tool"])
    text = all_text(at)
    assert "TL-001" in text
    # TL-001 makes two parts, so the parts control is a real select widget
    assert len(at.selectbox) >= 1, "expected a parts dropdown for a multi-part tool"
    labels = " ".join(sb.label for sb in at.selectbox)
    assert "Parts (" in labels


def test_single_part_tool_shows_no_parts_dropdown():
    at = run_at([("global", None), ("supplier", "Foxconn"), ("tool", "TL-002")])
    assert not at.exception
    labels = " ".join(sb.label for sb in at.selectbox)
    assert "Parts (" not in labels, "single-part tool should render inline, not a dropdown"


def test_part_overview_counts_parts_not_tools():
    at = run_at(STACKS["part_all"])
    text = all_text(at).upper()
    assert "TOTAL PARTS" in text
    assert "FAST PARTS (GAIN)" in text


def test_supplier_table_comma_joins_a_multi_country_supplier():
    at = run_at(STACKS["global"])
    sup = at.dataframe[-1].value  # Supplier Detail is the last table on the page
    assert "Country" in sup.columns
    assert sup["Country"].str.contains(",").any(), \
        "a supplier spanning two countries must show both"


def test_time_range_presets_have_no_last_90_days():
    at = run_at()
    ranges = [r for r in at.radio if r.label == "Select range"]
    assert ranges, "Time Range radio not found"
    assert list(ranges[0].options) == list(
        __import__("cte_core").TIME_RANGE_PRESETS)
    assert "Last 90 Days" not in ranges[0].options


def test_tolerance_slider_changes_the_tier_counts():
    at = run_at(STACKS["global"])
    before = all_text(at)
    at.slider[0].set_value(10.0).run()
    assert not at.exception
    after = all_text(at)
    assert "Tolerance: ±10%" in after
    assert before != after, "widening the tolerance band should change the page"


def test_last_quarter_preset_scopes_to_a_complete_quarter():
    at = run_at()
    ranges = [r for r in at.radio if r.label == "Select range"][0]
    ranges.set_value("Last Quarter").run()
    assert not at.exception
    # demo data ends 2026-07-06 (Q3), so the previous complete quarter is Q2 2026
    assert "2026-04-01 to 2026-06-30" in all_text(at)
