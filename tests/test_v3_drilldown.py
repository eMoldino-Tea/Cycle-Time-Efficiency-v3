"""Tests for the v3 drill-down additions.

  1. Clicking any figure (summary card, saving/loss card, pie caption,
     ranking bar) opens the list of tools that figure was computed from.
  2. A "Detailed Analysis" summary for whatever is currently selected,
     rendered at every tier from Region down to Tool.
  3. A breadcrumb that walks backwards AND forwards through the drill path.
  4. Ranking scoped to the selection's own tier and below, never above.

The drill-down assertions target `_tools_matching` directly rather than
through the UI. All four affordances (card overlay, pie caption, ranking bar,
table row) have been driven end-to-end in a real browser, but doing so needs
dispatched input events at measured pixel coordinates -- too brittle to keep
in a suite. What these tests pin instead is the part a pixel click can't
check anyway: that the filter tuple a click carries selects exactly the tools
the clicked figure was counting.
"""
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import cte_core as core  # noqa: E402
import cte_nav as nav  # noqa: E402
import cte_views as views  # noqa: E402

TOL = core.DEFAULT_TOLERANCE_PCT


@pytest.fixture(scope="module")
def scope():
    """The demo dataset, priced and classified the way the app does it."""
    df = core.ensure_geo_columns(core.load_base_data(version=11))
    df = core.apply_tolerance(df, TOL)
    return core.apply_financials(df, 40.0, 180.0)


@pytest.fixture
def session_state(monkeypatch):
    state = {}
    monkeypatch.setattr(nav.st, "session_state", state)
    return state


# ---- 1. drill-down: a clicked figure opens the tools behind it -------------

def test_tier_drill_selects_exactly_the_tools_the_card_counted(scope):
    """The Slow card says N; clicking it must list those same N tools.

    This is the whole promise of the drill-down: the number you clicked and
    the list you land on are the same population, classified per tool by
    weighted efficiency -- not per record, which would give a different N.
    """
    summary = core.scope_summary(scope, TOL)
    for tier in ("Fast", "Within", "Slow"):
        sub, extra = views._tools_matching(scope, ("tier", tier), TOL)
        assert sub['Tooling'].nunique() == summary[tier.lower()], tier
        assert extra == []


def test_tier_drill_partitions_the_total(scope):
    """Fast + Within + Slow must account for every tool exactly once."""
    tools = set()
    for tier in ("Fast", "Within", "Slow"):
        sub, _ = views._tools_matching(scope, ("tier", tier), TOL)
        this = set(sub['Tooling'])
        assert not (tools & this), f"{tier} overlaps an earlier tier"
        tools |= this
    assert tools == set(scope['Tooling'])


def test_total_card_drill_lists_every_tool_in_scope(scope):
    sub, extra = views._tools_matching(scope, ("tier", "All"), TOL)
    assert set(sub['Tooling']) == set(scope['Tooling'])
    assert extra == []


@pytest.mark.parametrize("which,money,cols", [
    ("saving", "Financial_Gain", ["Hours Gained", "Shots Gained"]),
    ("loss", "Financial_Loss", ["Hours Lost", "Shots Lost"]),
])
def test_money_drill_lists_only_tools_contributing_to_that_figure(
        scope, which, money, cols):
    """Clicking Saving Opportunity must not list tools that saved nothing."""
    sub, extra = views._tools_matching(scope, ("metric", which), TOL)
    assert extra == cols, "the drill must explain the money it came from"
    per_tool = sub.groupby('Tooling')[money].sum()
    assert (per_tool > 0).all()
    # And nothing that contributes was left out.
    all_tools = scope.groupby('Tooling')[money].sum()
    assert set(per_tool.index) == set(all_tools[all_tools > 0].index)


def test_money_drill_preserves_the_headline_figure(scope):
    """The tool list must add up to the card the reader clicked."""
    summary = core.scope_summary(scope, TOL)
    for which, money, key in [("saving", "Financial_Gain", "saving_opportunity"),
                              ("loss", "Financial_Loss", "loss")]:
        sub, _ = views._tools_matching(scope, ("metric", which), TOL)
        assert sub[money].sum() == pytest.approx(summary[key])


def test_dimension_drill_from_a_pie_or_bar_lists_that_slice(scope):
    """A pie caption / ranking bar carries ('dim', column, value)."""
    region = scope['Region'].dropna().iloc[0]
    sub, extra = views._tools_matching(scope, ("dim", "Region", region), TOL)
    assert set(sub['Region']) == {region}
    assert set(sub['Tooling']) == set(scope.loc[scope['Region'] == region, 'Tooling'])
    # Every tool row already carries its Region, so nothing is appended.
    assert "Region" in core.V3_TOOL_COLS and extra == []


def test_dimension_drill_surfaces_a_column_the_tool_table_does_not_show(scope):
    """Drilling by Supplier has to say which supplier each tool belongs to."""
    supplier = scope['Supplier'].dropna().iloc[0]
    sub, extra = views._tools_matching(scope, ("dim", "Supplier", supplier), TOL)
    assert set(sub['Supplier']) == {supplier}
    assert "Supplier" not in core.V3_TOOL_COLS and extra == ["Supplier"]


def test_dimension_drill_on_an_absent_column_is_empty_not_an_error(scope):
    sub, _ = views._tools_matching(scope, ("dim", "Nonexistent", "x"), TOL)
    assert sub.empty


def test_every_drill_spec_the_click_handler_emits_is_understood(scope):
    """_handle_clicks and _tools_matching must not drift apart.

    Each tuple below is one that `_handle_clicks` can push; every one has to
    be a shape `_tools_matching` handles, or that click becomes a dead page.
    """
    specs = [("tier", "All"), ("tier", "Fast"), ("tier", "Within"),
             ("tier", "Slow"), ("metric", "saving"), ("metric", "loss"),
             ("dim", "Region", scope['Region'].dropna().iloc[0])]
    for spec in specs:
        sub, extra = views._tools_matching(scope, spec, TOL)
        assert isinstance(sub, pd.DataFrame)
        assert isinstance(extra, list)
        assert nav.frame_label('tool_list', spec)


# ---- 2. breadcrumb: backwards and forwards ---------------------------------

def test_going_back_parks_the_trimmed_frames_for_forward(session_state):
    nav.push('region', 'APAC')
    nav.push('country', 'China')
    nav.pop_to(0)
    assert nav.get_stack() == [('global', None)]
    assert nav.forward_frames() == [('region', 'APAC'), ('country', 'China')]


def test_going_forward_restores_the_frames_in_order(session_state):
    nav.push('region', 'APAC')
    nav.push('country', 'China')
    nav.pop_to(0)
    nav.go_forward()
    assert nav.get_stack() == [('global', None), ('region', 'APAC')]
    assert nav.forward_frames() == [('country', 'China')]
    nav.go_forward()
    assert nav.get_stack() == [('global', None), ('region', 'APAC'),
                               ('country', 'China')]
    assert nav.forward_frames() == []


def test_two_hops_back_then_forward_returns_to_the_same_place(session_state):
    nav.push('region', 'APAC')
    nav.push('country', 'China')
    deep = list(nav.get_stack())
    nav.pop_to(0)
    nav.go_forward()
    nav.go_forward()
    assert nav.get_stack() == deep


def test_a_new_drill_after_going_back_discards_the_forward_history(session_state):
    """Branching off mid-path must not leave a forward crumb to a page the
    reader can no longer get to from here."""
    nav.push('region', 'APAC')
    nav.pop_to(0)
    assert nav.forward_frames()
    nav.push('region', 'Europe')
    assert nav.forward_frames() == []


def test_going_forward_with_no_history_is_a_no_op(session_state):
    nav.push('region', 'APAC')
    before = list(nav.get_stack())
    nav.go_forward()
    assert nav.get_stack() == before


def test_switching_root_tabs_clears_the_forward_history(session_state):
    nav.push('region', 'APAC')
    nav.pop_to(0)
    nav.set_root('part_all')
    assert nav.forward_frames() == []


def test_crumb_labels_cover_every_frame_of_a_deep_path(session_state):
    """One clickable crumb per prior tier -- the full path, not a truncation."""
    for lvl, val in [('region', 'APAC'), ('country', 'China'),
                     ('supplier', 'Foxconn'), ('plant', 'Plant 5 (CN)'),
                     ('tool', 'TL-001')]:
        nav.push(lvl, val)
    crumbs = nav.crumb_labels(nav.get_stack())
    assert [c[1] for c in crumbs] == ['Global', 'APAC', 'China', 'Foxconn',
                                      'Plant 5 (CN)', 'TL-001']
    assert [c[0] for c in crumbs] == list(range(6))


@pytest.mark.parametrize("value,expected", [
    (("tier", "Slow"), "Slow Tools"),
    (("tier", "All"), "All Tools"),
    (("metric", "saving"), "Saving Opportunity"),
    (("metric", "loss"), "Loss"),
    (("dim", "Region", "APAC"), "APAC Tools"),
])
def test_a_drill_down_frame_gets_a_readable_crumb(value, expected):
    assert nav.frame_label('tool_list', value) == expected


# ---- 3. the Detailed Analysis zero-state -----------------------------------

ZERO_STATE_APP = """
import sys
sys.path.insert(0, {root!r})
import pandas as pd
import streamlit as st
import cte_core as core
import cte_charts as charts
import cte_ui as ui

ui.inject_theme()
empty = core.apply_tolerance(core.load_base_data(version=11), 5.0).iloc[0:0]
charts.render_detailed_analysis(empty, "Nothing Here", "zs", "2026-01-01 to 2026-01-02", 5.0)
"""


def test_detailed_analysis_zero_state_renders_zeros_rather_than_collapsing():
    """A selection with no records must still render its five KPIs at 0/$0
    with an explanation in each panel.

    An empty selection that renders nothing is indistinguishable from a page
    that failed to load, which is exactly what the zero-state is for. Driven
    through a minimal harness app because the real dashboard's own
    empty-scope guard stops the script before any renderer is reached, so
    this path is not observable from the full app.
    """
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_string(ZERO_STATE_APP.format(root=ROOT), default_timeout=120)
    at.run()
    assert not at.exception

    text = "\n".join([m.value for m in at.markdown] + [i.value for i in at.info])
    assert "Nothing Here" in text, "the zero-state must still name what was selected"
    for kpi in ("Overall Cycle Time Efficiency %", "Total Hours Gained (Fast)",
                "Total Hours Lost (Slow)", "Saving Opportunity (from fast shots)",
                "Loss (from slow shots)"):
        assert kpi in text, f"zero-state dropped KPI {kpi!r}"
    assert text.count("0%") >= 1 and text.count("$0") >= 2, \
        "zero-state KPIs must read 0 / $0, not blank"

    # Both panels explain themselves rather than rendering an empty chart.
    infos = [i.value for i in at.info]
    assert infos.count("No data for selected period.") == 2, \
        f"expected both panels to explain the gap, got {infos}"
    assert not at.get("plotly_chart"), "no chart should be drawn with no data"


# ---- 4. ranking scope: own tier and below, never above ---------------------

# The hierarchy the ranking selector is scoped against.
HIERARCHY = ['Region', 'Country', 'Supplier', 'Plant', 'Tooling Type',
             'Project', 'Part']

# Level -> exactly what its Rank-by selector must offer. Global sits above
# the whole hierarchy so it offers all of it; a root tab offers its own tier
# and below (nothing is pinned yet, so ranking the tab's own tier is real);
# selecting one entity pins that tier, so it starts one lower.
EXPECTED_RANKING_DIMS = {
    'global':       HIERARCHY,
    'region_all':   HIERARCHY,
    'country_all':  HIERARCHY[1:],
    'supplier_all': HIERARCHY[2:],
    'plant_all':    HIERARCHY[3:],
    'type_all':     HIERARCHY[4:],
    'project_all':  HIERARCHY[5:],
    'part_all':     HIERARCHY[6:],
    'region':       HIERARCHY[1:],
    'country':      HIERARCHY[2:],
    'supplier':     HIERARCHY[3:],
    'plant':        HIERARCHY[4:],
    'type':         HIERARCHY[5:],
    'project':      HIERARCHY[6:],
    'part':         [],
}


@pytest.mark.parametrize("level,expected", sorted(EXPECTED_RANKING_DIMS.items()))
def test_ranking_offers_its_own_tier_and_below_only(level, expected):
    assert views._ranking_dims(level) == expected


@pytest.mark.parametrize("level", sorted(EXPECTED_RANKING_DIMS))
def test_ranking_never_offers_a_tier_above_the_selection(level):
    """The point of the scoping: a node has one parent per level above, so
    ranking by a higher tier would draw a single bar labelled with the thing
    you are already inside."""
    dims = views._ranking_dims(level)
    if not dims:
        return
    floor = HIERARCHY.index(dims[0])
    assert dims == HIERARCHY[floor:], f"{level} ranking is not a contiguous tail"
    above = set(HIERARCHY[:floor])
    assert not (above & set(dims)), f"{level} ranks by a tier above it"


def test_selecting_an_entity_drops_its_own_tier_from_the_ranking():
    """A selected Country must not rank by Country, though the Country TAB
    (where no single country is pinned) still must."""
    for tab, sel, tier in [('country_all', 'country', 'Country'),
                           ('supplier_all', 'supplier', 'Supplier'),
                           ('plant_all', 'plant', 'Plant'),
                           ('type_all', 'type', 'Tooling Type'),
                           ('project_all', 'project', 'Project'),
                           ('part_all', 'part', 'Part')]:
        assert tier in views._ranking_dims(tab), f"{tab} should still rank by {tier}"
        assert tier not in views._ranking_dims(sel), \
            f"{sel} must not rank by its own pinned tier {tier}"


def test_tool_is_never_a_ranking_dimension():
    """Part is the lowest ranking tier; Tool is reached by a row click."""
    for level in EXPECTED_RANKING_DIMS:
        assert 'Tooling' not in views._ranking_dims(level)
        assert 'Tool' not in views._ranking_dims(level)


def test_a_selected_part_has_nothing_left_to_rank():
    assert views._ranking_dims('part') == []
