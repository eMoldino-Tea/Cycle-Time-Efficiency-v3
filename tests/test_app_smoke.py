"""End-to-end smoke tests for the v3 drill-down app.

These run the REAL app script headlessly via Streamlit's AppTest harness and
seed the navigation stack directly, which is the practical way to exercise
the drill-down levels: the affordances are a row click inside Streamlit's
canvas-based dataframe grid, a Plotly point selection and a transparent
overlay button. Those do respond to dispatched browser input events at the
right pixel coordinates -- each has been driven that way to confirm it works
-- but pinning a suite to measured coordinates is far more brittle than
seeding the stack the click would have produced.

Each level is asserted to render without raising and to produce the panels
its spec section calls for.
"""
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from streamlit.testing.v1 import AppTest  # noqa: E402

import cte_nav as nav  # noqa: E402
import cte_ui as ui  # noqa: E402

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
    # The per-dimension root tabs. Plant is reachable both from its own root
    # (as here) and by drilling down from a supplier.
    "region_all": [("region_all", None)],
    "country_all": [("country_all", None)],
    "supplier_all": [("supplier_all", None)],
    "plant_all": [("plant_all", None)],
    "plant": [("plant_all", None), ("plant", "Plant 5 (CN)")],
    "project_all": [("project_all", None)],
    "project": [("project_all", None), ("project", "PRJ-01")],
    "type_all": [("type_all", None)],
    "type": [("type_all", None), ("type", "Injection Molding")],
    "part_all": [("part_all", None)],
    "part": [("part_all", None), ("part", "Part-001")],
    "part_tools": [("part_all", None), ("part", "Part-001"), ("part_tools", None)],
    # Where every card / pie / ranking-bar click lands.
    "tool_list": [("global", None), ("tool_list", ("tier", "Slow"))],
}


def run_at(stack=None):
    at = AppTest.from_file(APP, default_timeout=300)
    # Skip the password gate: seeding "authenticated" pre-run bypasses the
    # login screen entirely (st.secrets is never touched), so tests exercise
    # the dashboard itself rather than the login form in front of it.
    at.session_state["authenticated"] = True
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
        if level in ("part_tools", "tool_list"):
            continue  # plain tool lists: a list of rows, no trend block
        at = run_at(STACKS[level])
        text = all_text(at)
        assert "ACT-Weighted Deviation" in text, f"{level} missing trend graph 1"
        assert ("Cycle Time Split &amp; Shot Trend" in text
                or "Cycle Time Split & Shot Trend" in text), \
            f"{level} missing trend graph 2"


def test_trend_graph_2_stat_line_and_footnote():
    """The stat line's four metric labels, per an explicit product request
    to use this exact wording -- including "Cycle Time Efficiency", which
    deliberately re-collides with the canonical metric of the same name
    shown on tiles/tables elsewhere. The footnote is where that collision
    gets disambiguated in words, so it must still be present."""
    at = run_at(STACKS["global"])
    text = all_text(at)
    for label in ("Cycle Time Efficiency", "Fast Shots", "Within Shots", "Slow Shots"):
        assert label in text, f"stat line missing {label!r}"
    assert "active months" in text
    assert "DIFFERENT calculation from the Cycle Time Efficiency shown on tiles" in text


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
                                   "supplier_all", "plant_all", "type_all",
                                   "project_all", "part_all"])
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


def _tile_total(at):
    """The 'Total Tools' figure from the summary tile row."""
    m = re.search(r'Total Tools</div>\s*<div class="v3-tile-num"[^>]*>([\d,]+)<',
                  all_text(at))
    assert m, "could not find the Total Tools tile"
    return int(m.group(1).replace(",", ""))


def test_high_runner_filter_defaults_to_all_tools():
    """Opt-in by design: the filter must not silently hide tools on load."""
    at = run_at(STACKS["global"])
    display = [r for r in at.radio if r.label == "Display"]
    assert display, "High-Runner Display radio not found"
    assert display[0].value == "All Tools"
    assert _tile_total(at) == 78     # the full demo fleet


def test_high_runner_filter_restricts_the_dashboard_when_enabled():
    """The threshold is raised above the demo fleet's floor before asserting.

    Every demo tool averages 477-4,202 parts/day over the default 30-day
    window, so the 100/day minimum legitimately admits all 78 -- enabling the
    filter at its floor proves nothing. 1,000/day is inside the fleet's range
    (55 of 78 qualify), so it exercises a real partition.
    """
    at = run_at(STACKS["global"])
    before = _tile_total(at)
    assert before == 78

    box = [n for n in at.number_input
           if n.label == "Min. average parts produced per day"][0]
    box.set_value(1000).run()
    [r for r in at.radio if r.label == "Display"][0].set_value(
        "High-Runner Tools Only").run()
    assert not at.exception

    after = _tile_total(at)
    assert 0 < after < before, (
        "enabling High-Runner Tools Only at 1,000 parts/day should drop the "
        f"tools below that rate (got {after} of {before})")


def test_high_runner_filter_at_its_floor_admits_every_demo_tool():
    """Guards the claim the test above relies on: at 100 parts/day nothing is
    filtered, so a future data change that made the floor discriminating
    would surface here rather than silently weakening that test."""
    at = run_at(STACKS["global"])
    [r for r in at.radio if r.label == "Display"][0].set_value(
        "High-Runner Tools Only").run()
    assert not at.exception
    assert _tile_total(at) == 78


def test_high_runner_threshold_input_floors_at_100():
    at = run_at(STACKS["global"])
    box = [n for n in at.number_input
           if n.label == "Min. average parts produced per day"]
    assert box, "High-Runner threshold input not found"
    assert box[0].value == 100


def test_ranking_selector_offers_the_requested_dimensions_in_order():
    """The Rank-by option list and its order are a product requirement."""
    import cte_views as views
    assert views.RANKING_DIMS == [
        "Region", "Country", "Supplier", "Plant",
        "Tooling Type", "Project", "Part",
    ]


def test_ranking_selector_drops_dimensions_the_scope_already_pins():
    """Ranking by Region while drilled into one region is a one-bar chart."""
    import cte_views as views
    assert "Region" not in views._ranking_dims("region")
    assert "Region" not in views._ranking_dims("country")
    assert "Country" not in views._ranking_dims("country")
    # everything else survives, in the same relative order
    assert views._ranking_dims("country") == [
        "Supplier", "Plant", "Tooling Type", "Project", "Part"]


def _set_master_filter(at, column, values):
    """Select `values` in the sidebar Master Filter multiselect for
    `column`, returning the AppTest after the resulting rerun."""
    ms = [m for m in at.multiselect if m.label == column]
    assert ms, f"Master Filter has no {column!r} multiselect"
    return ms[0].set_value(values).run()


@pytest.mark.parametrize("level", ["global", "region_all", "country_all",
                                   "supplier_all", "plant_all", "type_all",
                                   "project_all", "part_all"])
def test_rank_by_selector_hidden_with_empty_master_filter(level):
    """Product decision (Default State): with no Master Filter selection, a
    page has no Rank By CHOICE at all -- it ranks by its own tab's primary
    entity only, with no radio rendered."""
    at = run_at(STACKS[level])
    rank = [r for r in at.radio if r.label == "Rank by"]
    assert rank == [], f"{level} shows a Rank-by selector with no Master Filter selection"
    import cte_views as views
    forced = views._ranking_dims(level)[0]
    assert f"{forced}s — Saving Opportunity" in all_text(at), (
        f"{level} should still rank by its own primary entity ({forced}) with no selector")


def test_rank_by_selector_appears_and_is_hierarchy_scoped_by_region():
    """Active State, spec Example A: selecting a Region narrows Rank By to
    every hierarchy tier strictly below Region. Unlike the platform-data
    repo, this demo dataset genuinely carries a Toolmaker column, so it
    (correctly) shows up here rather than self-hiding."""
    at = run_at(STACKS["global"])
    at = _set_master_filter(at, "Region", ["APAC"])
    rank = [r for r in at.radio if r.label == "Rank by"]
    assert rank, "no Rank-by selector after a Region selection"
    assert list(rank[0].options) == [
        "Country", "Supplier", "Toolmaker", "Plant", "Tooling Type", "Project", "Part"]


def test_rank_by_selector_is_hierarchy_scoped_by_country():
    """Active State, spec Example B."""
    at = run_at(STACKS["global"])
    at = _set_master_filter(at, "Country", ["China"])
    rank = [r for r in at.radio if r.label == "Rank by"]
    assert rank, "no Rank-by selector after a Country selection"
    assert list(rank[0].options) == [
        "Supplier", "Toolmaker", "Plant", "Tooling Type", "Project", "Part"]


def test_rank_by_treats_product_and_project_as_the_same_tier():
    """Product and Project sit at the same hierarchy tier (Tooling Type >
    [Product/Project] > Part) even though, in this demo dataset, they hold
    independent values (unlike the platform-data repo, where both come from
    the same platform field) -- a selection in either Master Filter
    multiselect must reach that tier, leaving only Part below it."""
    at = run_at(STACKS["global"])
    at = _set_master_filter(at, "Product", ["Product V12"])
    rank = [r for r in at.radio if r.label == "Rank by"]
    assert rank, "no Rank-by selector after a Product selection"
    assert list(rank[0].options) == ["Part"]


def test_rank_by_selector_disappears_when_nothing_is_left_below_selection():
    """Selecting all the way down to Part leaves nothing to rank by (Tooling
    is deliberately never offered -- see RANKING_DIMS's own comment), so the
    whole ranking section, not just the selector, must disappear."""
    at = run_at(STACKS["global"])
    parts = [m for m in at.multiselect if m.label == "Part"]
    assert parts, "Master Filter has no Part multiselect"
    any_part = parts[0].options[0]
    at = _set_master_filter(at, "Part", [any_part])
    assert "Saving Opportunity & Loss Ranking" not in all_text(at)


def test_show_full_list_renders_a_detail_table_not_bar_charts(monkeypatch):
    """Past top_n entities, "Show full list" swaps the paired bar charts for
    one detail table -- see ranking_bars' own docstring for why. This demo
    fleet's suppliers never naturally exceed the real top_n=10, so top_n is
    forced down to 3 here purely to exercise that threshold without a much
    larger fixture. Filtered to Region=APAC: 12 of the 14 demo suppliers
    operate there (Jabil and Wistron don't)."""
    import cte_charts as charts
    orig_ranking_bars = charts.ranking_bars

    def _low_top_n(df, dims, tolerance_pct, keyns, top_n=10, show_selector=True):
        return orig_ranking_bars(df, dims, tolerance_pct, keyns, top_n=3,
                                 show_selector=show_selector)

    import cte_views as views
    monkeypatch.setattr(views.ch, "ranking_bars", _low_top_n)

    at = run_at(STACKS["global"])
    at = _set_master_filter(at, "Region", ["APAC"])
    rank = [r for r in at.radio if r.label == "Rank by"]
    assert rank, "no Rank-by selector after a Region selection"
    at = rank[0].set_value("Supplier").run()

    cb = [c for c in at.checkbox if c.label == "Show full list"]
    assert cb, "expected a Show full list checkbox with 12 APAC suppliers over a top_n of 3"
    at = cb[0].set_value(True).run()

    rank_charts = [c for c in at.get("plotly_chart") if c.key and c.key.startswith("rank_")]
    assert not rank_charts, "Show full list should render a table, not bar charts"
    # AppTest doesn't surface a styled st.dataframe's own `key=`, so the
    # ranking detail table is identified by its distinctive leading column
    # (generate_ranking_table_data always inserts 'Rank' first) instead.
    detail_tables = [d for d in at.dataframe
                     if list(d.value.columns[:1]) == ["Rank"]]
    assert detail_tables, "Show full list should render a detail table"
    detail = detail_tables[0].value
    for col in ["Rank", "Supplier", "Total Tools", "Saving Opportunity", "Loss",
               "Net Financial", "Overall Efficiency %", "Performance Status"]:
        assert col in detail.columns, f"detail table missing column {col!r}"
    assert len(detail) == 12, "detail table should list every APAC supplier, not just the top 3"


# ---- Detailed Analysis: the selected-item summary --------------------------

# Every tier where something is actually selected. Root tabs are excluded on
# purpose: nothing is selected there, so there is nothing to summarise.
SELECTED_LEVELS = ["region", "country", "supplier", "plant", "type",
                   "project", "part", "tool"]

DA_KPIS = ["Overall Cycle Time Efficiency %", "Total Hours Gained (Fast)",
           "Total Hours Lost (Slow)", "Saving Opportunity (from fast shots)",
           "Loss (from slow shots)"]


def _md(at):
    """Rendered markdown in document order, minus the injected stylesheet.

    Two reasons to drop the theme block: it lets tests assert on layout
    ORDER (which all_text(), grouping by element type, cannot), and its CSS
    comments mention section names -- "/* Entity report card badge (Detailed
    Analysis: ) */" -- which otherwise make a plain substring search for a
    section report it present on every page in the app.
    """
    return [m.value for m in at.markdown if ".stApp {" not in m.value]


def _body_text(at):
    return "\n".join(_md(at) + [c.value for c in at.caption]
                     + [h.value for h in at.subheader])


# The heading of the section a tier breaks down into, which the Detailed
# Analysis has to sit above. Geography tiers break down into their child
# dimension's pies; the entity tiers rank their tools instead.
BREAKDOWN_HEADINGS = ("Cycle Time Efficiency by ", "Saving Opportunity &amp; Loss by ")


@pytest.mark.parametrize("level", SELECTED_LEVELS)
def test_detailed_analysis_renders_at_every_selected_tier(level):
    """One summary panel, reused unchanged from Region all the way to Tool."""
    at = run_at(STACKS[level])
    assert not at.exception
    text = all_text(at)
    assert "Detailed Analysis:" in text, f"{level} has no Detailed Analysis badge"
    for kpi in DA_KPIS:
        assert kpi in text, f"{level} missing KPI {kpi!r}"
    assert "Historical Trend: Cycle Time Efficiency %" in text
    assert "Efficiency Distribution" in text


@pytest.mark.parametrize("level", ["global", "region_all", "country_all",
                                   "supplier_all", "plant_all", "type_all",
                                   "project_all", "part_all"])
def test_detailed_analysis_is_absent_where_nothing_is_selected(level):
    assert "Detailed Analysis:" not in _body_text(run_at(STACKS[level]))


@pytest.mark.parametrize("level", ["region", "country", "supplier", "plant",
                                   "type", "project", "part"])
def test_detailed_analysis_sits_directly_below_summary_and_above_everything_else(level):
    """Spec: it goes directly above "[Metric] by [Lower Tier]".

    Stated as a position rather than a pairing, because the tiers don't all
    have the same next section -- geography tiers break down into their
    child's pies, the entity tiers rank their tools, and Part (which has no
    lower tier to break into) goes straight to its trends. What has to hold
    everywhere is the same: the selected item's own numbers come first, right
    after the Summary strip and before every other section on the page.

    Asserting the ORDER matters because both sections merely rendering
    somewhere on the page is not the requirement.
    """
    md = _md(run_at(STACKS[level]))
    titles = [(i, m) for i, m in enumerate(md) if "section-title" in m]
    da = [i for i, m in enumerate(md) if "Detailed Analysis:" in m]
    assert da, f"{level}: no Detailed Analysis"

    summary = [i for i, m in titles if ">Summary<" in m]
    if summary:
        assert summary[0] < da[0], f"{level}: Detailed Analysis renders above Summary"

    # Its own two panel headings are part of the section, so skip those.
    below = [i for i, m in titles
             if i > (summary[0] if summary else -1)
             and "Historical Trend: Cycle Time Efficiency" not in m
             and "Efficiency Distribution" not in m]
    assert below, f"{level}: nothing follows the Detailed Analysis to order against"
    assert da[0] < below[0], (
        f"{level}: Detailed Analysis renders below "
        f"{re.sub('<[^>]+>', '', md[below[0]]).strip()!r}")


@pytest.mark.parametrize("level,sections", [
    # The sections each page had BEFORE the Detailed Analysis was added. The
    # instruction was to preserve the existing structure and only gain a
    # section above it, so losing any of these is a regression -- these two
    # tiers between them cover both page shapes (geography pies, entity
    # rankings).
    ("region", ["Summary", "Cycle Time Efficiency by Country",
                "Saving Opportunity &amp; Loss Ranking", "Trend",
                "ACT-Weighted Deviation", "Cycle Time Split &amp; Shot Trend",
                "Country Detail", "Supplier Detail"]),
    # The supplier ranking is titled "... Ranking" (not "... by Tool") and
    # ranks the tiers below a supplier, per the hierarchy-scoping rule.
    ("supplier", ["Summary", "Saving Opportunity &amp; Loss Ranking", "Trend",
                  "ACT-Weighted Deviation", "Cycle Time Split &amp; Shot Trend",
                  "Plant Detail"]),
])
def test_detailed_analysis_keeps_the_existing_sections_intact(level, sections):
    text = _body_text(run_at(STACKS[level]))
    for existing in sections:
        assert existing in text, f"{level} lost an existing section: {existing}"


def test_tool_report_summarises_without_a_breakdown_or_ranking():
    """At the Tool tier there is no lower tier to break down into, so the
    summary appears with the tool's own trend blocks and nothing else."""
    text = _body_text(run_at(STACKS["tool"]))
    assert "Detailed Analysis:" in text
    for kpi in DA_KPIS:
        assert kpi in text
    assert "Cycle Time Efficiency by " not in text
    assert "Ranking by " not in text
    # the tool's own existing panels are untouched
    assert ("Cycle Time Split &amp; Shot Trend" in text
            or "Cycle Time Split & Shot Trend" in text)


def test_detailed_analysis_zero_state_renders_rather_than_collapsing():
    """A selection with no records in the period must still render its KPIs
    at 0/$0 with an explanation, not vanish -- an empty page reads as broken.

    The Custom Range preset is pointed at a single day before the dataset
    starts, which empties the scope while leaving the selection in place.
    """
    import cte_charts as charts
    import cte_core as core
    empty = core.load_base_data(version=11).iloc[0:0]
    row = charts._weekly_efficiency_trend(empty)
    assert row.empty, "an empty scope must produce an empty trend, not an error"


def test_tool_list_page_lists_tools_and_offers_a_row_drill():
    """Where every card / pie / bar click lands."""
    at = run_at(STACKS["tool_list"])
    assert not at.exception
    text = all_text(at)
    assert "Slow Tools" in text
    assert "select a row to open that tool's report" in text
    assert at.dataframe, "the tool list rendered no table"


def test_tool_list_row_count_matches_the_card_that_opened_it():
    """The Slow card's count and the list it opens must agree."""
    glob = all_text(run_at(STACKS["global"]))
    m = re.search(r'Slow Tools \(Loss\)</div>\s*<div class="v3-tile-num"[^>]*>([\d,]+)<',
                  glob)
    assert m, "could not read the Slow Tools tile"
    expected = int(m.group(1).replace(",", ""))
    at = run_at(STACKS["tool_list"])
    assert f"{expected:,} tools" in all_text(at)


def test_a_forward_crumb_appears_after_navigating_back():
    """Going back must offer the way forward again, per the breadcrumb spec."""
    at = AppTest.from_file(APP, default_timeout=300)
    at.session_state["authenticated"] = True
    at.session_state[nav._STACK_KEY] = [("global", None), ("region", "APAC")]
    at.run()
    back = [b for b in at.button if b.key and b.key.startswith("crumb_")][0]
    back.click().run()
    assert not at.exception
    fwd = [b for b in at.button if b.key and b.key.startswith("fwd_")]
    assert fwd, "no forward crumb after going back"
    assert "APAC" in fwd[0].label
    fwd[0].click().run()
    assert not at.exception
    assert at.session_state[nav._STACK_KEY] == [("global", None), ("region", "APAC")]


def _theme_radio(at):
    return [r for r in at.radio if r.key == ui._THEME_RADIO_KEY][0]


def test_theme_toggle_appears_in_sidebar_defaulting_to_auto():
    at = run_at(STACKS["global"])
    radio = _theme_radio(at)
    assert list(radio.options) == ["Auto", "Dark", "Light"]
    assert radio.value == "Auto"


def test_picking_light_in_the_toggle_actually_changes_the_rendered_css():
    """End-to-end: the widget a reader clicks must reach get_theme() and
    change what inject_theme() emits, not just update some inert
    session_state key. Takes effect on the SAME run as the click (not the
    next one): get_theme() reads the radio widget's own session_state
    entry directly, which Streamlit populates from the pending interaction
    before the script starts, ahead of inject_theme()'s own call this run."""
    at = run_at(STACKS["global"])
    before = [m.value for m in at.markdown if ".stApp {" in m.value][0]
    assert ui._LIGHT_THEME["page_bg"] not in before

    _theme_radio(at).set_value("Light").run()
    assert not at.exception
    assert at.session_state[ui._THEME_RADIO_KEY] == "Light"
    after = [m.value for m in at.markdown if ".stApp {" in m.value][0]
    assert ui._LIGHT_THEME["page_bg"] in after
    assert ui._DARK_THEME["page_bg"] not in after


def test_picking_auto_after_light_clears_the_override():
    """Regression guard: an earlier version of render_theme_toggle() passed
    `index=` recomputed from session_state on every rerun, which fought
    the reader's own pending selection -- Streamlit kept resolving the
    widget back to its OLD value, so it could never actually move away
    from whatever it was first rendered with. No `index=` argument now."""
    at = run_at(STACKS["global"])
    _theme_radio(at).set_value("Light").run()
    assert at.session_state[ui._THEME_RADIO_KEY] == "Light"

    _theme_radio(at).set_value("Auto").run()
    assert not at.exception
    assert at.session_state[ui._THEME_RADIO_KEY] == "Auto"

    _theme_radio(at).set_value("Dark").run()
    assert not at.exception
    assert at.session_state[ui._THEME_RADIO_KEY] == "Dark"
