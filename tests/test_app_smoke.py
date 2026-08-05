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
    # The per-dimension root tabs, and Plant -- which is reachable only from
    # its own root, never from the geography chain.
    "region_all": [("region_all", None)],
    "country_all": [("country_all", None)],
    "supplier_all": [("supplier_all", None)],
    "plant_all": [("plant_all", None)],
    "plant": [("plant_all", None), ("plant", "Plant 5 (CN)")],
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
        assert ("Cycle Time Split &amp; Shot Trend" in text
                or "Cycle Time Split & Shot Trend" in text), \
            f"{level} missing trend graph 2"


def test_trend_graph_2_stat_line_and_footnote():
    at = run_at(STACKS["global"])
    text = all_text(at)
    assert "At or Better Than ACT" in text
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


def test_each_scope_level_offers_its_child_drill_table():
    """Behavioural companion to test_cte_nav.py's static source-text scanner.

    That scanner reads cte_views.py's source text and would stay green even
    if someone tightened render_scope_overview's gating condition (e.g.
    `if child_dim != 'Supplier':` -> `if False:`) -- the parser still sees
    the syntactic `_table_drill(...)` call in the function body, so a
    regression that silently makes Region/Country's drill table stop
    rendering would slip through undetected. This test instead runs the
    real app (via AppTest) and checks for the actual heading text the
    renderer emits, so it fails if the table itself stops appearing.

    Global's child is Region and Region's child is Country, each rendering
    a "<Child> Detail" heading (see render_scope_overview's Finding 1
    block). Country's child is Supplier, which is already covered by the
    page's own always-present "Supplier Detail" table, so no separate
    geography table is rendered for it -- this loop still asserts "Supplier
    Detail" is there for the "country" case, keeping the assertion uniform.
    """
    for lvl in ("global", "region", "country"):
        child = nav.LEVELS[nav.LEVELS[lvl]["child"]]["label"]
        t = all_text(run_at(STACKS[lvl]))
        assert f"{child} Detail" in t, f"{lvl} has no drill table for {child}"


@pytest.mark.parametrize("level", sorted(STACKS))
def test_no_level_renders_a_warning_box(level):
    """No page may render a Streamlit warning element.

    This exists because a real regression slipped through: `width="stretch"`
    was applied to st.plotly_chart during a deprecation migration, but that
    element takes `use_container_width` -- it has no `width` parameter, so the
    value fell into **kwargs, was forwarded to Plotly as a config option, and
    Streamlit rendered a deprecation warning box above all eight charts in the
    live app.

    Every existing test stayed green because they only counted that
    plotly_chart ELEMENTS existed, which they still did. Asserting on the
    absence of warning elements catches this whole class of bug -- a
    deprecated or misrouted keyword argument on any element -- rather than
    just this one instance.
    """
    at = run_at(STACKS[level])
    warnings = [w.value for w in at.warning]
    assert not warnings, f"{level} rendered {len(warnings)} warning box(es): {warnings[:2]}"


def _crumb_buttons(at):
    return [b for b in at.button if b.key and b.key.startswith("crumb_")]


@pytest.mark.parametrize("level", ["global", "region_all", "country_all",
                                   "supplier_all", "plant_all", "type_all", "part_all"])
def test_a_bare_root_page_shows_no_breadcrumb(level):
    """A single-frame stack only ever repeats the root tab bar's own label
    (e.g. "Country" sitting directly under the already-selected Country tab)
    -- it must render nothing rather than that redundant one-crumb line, on
    every root tab, not just the one this was first noticed on."""
    at = run_at(STACKS[level])
    assert _crumb_buttons(at) == [], f"{level} unexpectedly shows a breadcrumb"


def test_a_drilled_in_page_still_shows_its_breadcrumb():
    """The breadcrumb earns its place once there's an actual path to show --
    this must not regress into hiding it everywhere."""
    at = run_at(STACKS["tool"])  # global -> supplier(Foxconn) -> tool(TL-001)
    labels = [b.label for b in _crumb_buttons(at)]
    assert labels == ["Global  ›", "Foxconn  ›", "TL-001"]


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
