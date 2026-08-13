import os
import re
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import cte_nav as nav


# ---- Finding 1: reachability -----------------------------------------------
# 81 tests were green while 'region' and 'country' were declared in LEVELS,
# wired into RENDERERS and _ranking_dims, yet had no drill affordance
# anywhere -- the shipped app only ever pushed 'supplier', 'tool', 'type',
# 'part', 'part_tools'. This test reads cte_views.py's actual source text (no
# Streamlit runtime needed) and fails if any future level is added to LEVELS
# without also adding a way to reach it.
#
# The fix for 'region'/'country' is deliberately registry-driven (never
# hardcoded -- see render_scope_overview), so a plain "does the literal
# string 'region' appear next to a push call" grep can't see it: the level
# argument at that call site is a variable resolved from
# `cfg['child']`, not a quoted literal. So this parses each RENDERERS-mapped
# function body and resolves both forms: a quoted literal, or a variable
# assigned from the registry-driven `cfg['child']` (in which case the
# reachable level is looked up from nav.LEVELS itself, not hardcoded here
# either).
def _split_top_level_args(s):
    """Split a call's argument-list text on top-level commas, respecting
    nested parens/brackets/braces and quoted strings (so an argument like
    `ui.search_box(t, f"type_{ctx.keyns}")` -- which contains its own comma
    -- is not mistaken for two arguments)."""
    args, current, depth, quote = [], [], 0, None
    i = 0
    while i < len(s):
        ch = s[i]
        if quote:
            current.append(ch)
            if ch == quote and s[i - 1] != '\\':
                quote = None
        elif ch in '"\'':
            quote = ch
            current.append(ch)
        elif ch in '([{':
            depth += 1
            current.append(ch)
        elif ch in ')]}':
            depth -= 1
            current.append(ch)
        elif ch == ',' and depth == 0:
            args.append(''.join(current))
            current = []
        else:
            current.append(ch)
        i += 1
    if current:
        args.append(''.join(current))
    return [a.strip() for a in args]


def _extract_call_arglists(src, func_name):
    """The raw argument-list text of every call to `func_name(...)` in `src`
    (multi-line safe, paren-balance aware). Skips matches that are actually
    the tail of a longer identifier -- e.g. "_drill(" inside "_table_drill("."""
    marker = func_name + "("
    out, start = [], 0
    while True:
        idx = src.find(marker, start)
        if idx == -1:
            break
        if idx > 0 and (src[idx - 1].isalnum() or src[idx - 1] == '_'):
            start = idx + len(marker)
            continue
        depth, j = 1, idx + len(marker)
        while depth > 0 and j < len(src):
            if src[j] == '(':
                depth += 1
            elif src[j] == ')':
                depth -= 1
            j += 1
        out.append(src[idx + len(marker):j - 1])
        start = j
    return out


def _get_renderers_mapping(src):
    """level_key -> function_name, parsed from the RENDERERS = {...} dict
    literal at the bottom of cte_views.py."""
    m = re.search(r"RENDERERS\s*=\s*\{(.*?)\n\}", src, re.S)
    assert m, "could not find the RENDERERS dict in cte_views.py"
    return dict(re.findall(r"['\"](\w+)['\"]\s*:\s*(\w+)", m.group(1)))


def _get_function_bodies(src):
    """function_name -> its source text, split on top-level `def name(`."""
    chunks = re.split(r"\ndef (\w+)\(", src)
    bodies = {}
    for i in range(1, len(chunks), 2):
        bodies[chunks[i]] = "def " + chunks[i] + "(" + chunks[i + 1]
    return bodies


def _resolve_level_literal(level_arg, body, level_key):
    level_arg = level_arg.strip()
    lit = re.fullmatch(r"['\"](\w+)['\"]", level_arg)
    if lit:
        return lit.group(1)
    if re.fullmatch(r"cfg\[['\"]child['\"]\]", level_arg):
        return nav.LEVELS[level_key]['child']
    if re.fullmatch(r"\w+", level_arg):
        if re.search(rf"\b{re.escape(level_arg)}\s*=\s*cfg\[['\"]child['\"]\]", body):
            return nav.LEVELS[level_key]['child']
    return None


def _pushed_levels_in_views_source():
    with open(os.path.join(ROOT, "cte_views.py")) as f:
        src = f.read()

    renderers = _get_renderers_mapping(src)
    bodies = _get_function_bodies(src)

    pushed = set()

    # Literal pushes from ANY function in the module, not just the
    # RENDERERS-mapped ones: drill clicks are routed through a shared helper
    # (_handle_clicks), so restricting the scan to renderer bodies would miss
    # every level reachable that way and wrongly call it unreachable.
    for body in bodies.values():
        for raw in (_extract_call_arglists(body, "_drill")
                    + _extract_call_arglists(body, "nav.push")):
            args = _split_top_level_args(raw)
            if args:
                lit = re.fullmatch(r"['\"](\w+)['\"]", args[0])
                if lit:
                    pushed.add(lit.group(1))

    for level_key, func_name in renderers.items():
        body = bodies.get(func_name, "")

        # _drill(level, value) and nav.push(level, value) -- level is the
        # first quoted-literal argument.
        for raw in (_extract_call_arglists(body, "_drill")
                    + _extract_call_arglists(body, "nav.push")):
            args = _split_top_level_args(raw)
            if args:
                lit = re.fullmatch(r"['\"](\w+)['\"]", args[0])
                if lit:
                    pushed.add(lit.group(1))

        # _table_drill(df, label_col, level, keyns) -- level is the third
        # positional argument.
        for raw in _extract_call_arglists(body, "_table_drill"):
            args = _split_top_level_args(raw)
            if len(args) >= 3:
                resolved = _resolve_level_literal(args[2], body, level_key)
                if resolved:
                    pushed.add(resolved)
    return pushed


def test_navigating_requests_a_scroll_to_top(session_state):
    for mutate in (lambda: nav.push("region", "APAC"),
                   lambda: nav.pop_to(0),
                   lambda: nav.set_root("plant_all")):
        nav.consume_scroll_request()          # clear any prior request
        mutate()
        assert nav.consume_scroll_request() is True, mutate


def test_the_scroll_request_is_one_shot(session_state):
    """An ordinary rerun must not yank the reader back to the top.

    Only a stack change may request a scroll; moving the tolerance slider or
    typing in a table's search box reruns the script without navigating, and
    those must leave the scroll position alone.
    """
    nav.push("region", "APAC")
    assert nav.consume_scroll_request() is True
    assert nav.consume_scroll_request() is False
    assert nav.consume_scroll_request() is False


def test_no_scroll_is_requested_before_any_navigation(session_state):
    assert nav.consume_scroll_request() is False


def test_root_tabs_are_the_requested_dimensions_in_order():
    """The root tab bar's labels and order are a product requirement.
    Project sits immediately before Part, as specified."""
    assert [label for label, _ in nav.ROOTS] == [
        "Global Overview", "Region", "Country", "Supplier", "Plant",
        "Tooling Type", "Project", "Part",
    ]


def test_every_root_tab_points_at_a_real_level_with_no_filter_column():
    for label, level in nav.ROOTS:
        assert level in nav.LEVELS, f"root tab {label} points at unknown level {level}"
        assert nav.LEVELS[level]['col'] is None, \
            f"root {level} must not filter on its own column"
        child = nav.LEVELS[level]['child']
        assert child in nav.LEVELS, f"root {level}'s child {child} is not a level"


def test_plant_sits_in_the_geography_chain_and_also_has_its_own_root():
    """Plant is reachable two ways, by explicit product decision.

    It sits in the drill chain between Supplier and Tool (so a breadcrumb can
    read Global > APAC > China > Supplier X > Plant Y > Tool Z) AND keeps its
    own root tab, so it can be entered directly without going through a
    supplier. A Plant page therefore has two possible parents depending on
    the route taken; the nav stack records which one was used.
    """
    assert nav.LEVELS['plant']['col'] == 'Plant'
    assert nav.LEVELS['plant']['child'] == 'tool'
    assert nav.LEVELS['plant_all']['child'] == 'plant'
    assert ('Plant', 'plant_all') in nav.ROOTS

    chain = []
    lvl = 'global'
    while lvl:
        chain.append(lvl)
        lvl = nav.LEVELS[lvl]['child']
    assert chain == ['global', 'region', 'country', 'supplier', 'plant', 'tool']

def test_every_non_root_level_is_reachable_somewhere_in_production_source():
    root_levels = {level for _, level in nav.ROOTS}
    non_root_levels = set(nav.LEVELS) - root_levels
    pushed = _pushed_levels_in_views_source()

    missing = non_root_levels - pushed
    assert not missing, (
        f"levels declared in nav.LEVELS but never pushed anywhere in "
        f"cte_views.py, i.e. unreachable dead ends: {sorted(missing)}"
    )


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
    assert nav.LEVELS["supplier"]["child"] == "plant"
    assert nav.LEVELS["plant"]["child"] == "tool"
    assert nav.LEVELS["tool"]["child"] is None
    assert nav.LEVELS["part"]["child"] == "part_tools"
    assert nav.LEVELS["part_tools"]["child"] == "tool"


def test_every_level_declares_the_exact_required_trend_dim():
    expected_trend_dim = {
        "global": "Supplier",
        "region": "Supplier",
        "country": "Supplier",
        "supplier": "Tooling",
        # Per-dimension root tabs average across their own entity, matching
        # type_all/part_all; the entity pages below them average across Tools.
        "region_all": "Region",
        "country_all": "Country",
        "supplier_all": "Supplier",
        "plant_all": "Plant",
        "plant": "Tooling",
        "type_all": "Tooling Type",
        "project_all": "Project",
        "project": "Tooling",
        "type": "Tooling",
        "part_all": "Part",
        "part": "Tooling",
        "part_tools": "Tooling",
        "tool_list": "Tooling",
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


@pytest.fixture
def shot_frame():
    """Multiple records for the same tool spread across different parts --
    the shape that exposes the path-dependent tool report bug (Finding 2):
    TL-001 has rows under both Part-001 and Part-009."""
    return pd.DataFrame({
        "Tooling": ["TL-001", "TL-001", "TL-002"],
        "Part": ["Part-001", "Part-009", "Part-001"],
        "Supplier": ["Foxconn", "Foxconn", "Foxconn"],
        "Region": ["APAC", "APAC", "APAC"],
        "Country": ["China", "China", "China"],
    })


def test_tool_level_is_marked_exclusive_and_others_are_not():
    assert nav.LEVELS["tool"].get("exclusive") is True
    for level, cfg in nav.LEVELS.items():
        if level == "tool":
            continue
        assert not cfg.get("exclusive"), f"{level} should not be exclusive"


def test_scope_df_tool_reached_via_part_path_matches_tool_reached_via_supplier_path(shot_frame):
    """The whole point of Finding 2: same tool, different navigation path,
    same rows -- not a Part-scoped subset."""
    stack_via_part = [("part_all", None), ("part", "Part-001"),
                       ("part_tools", None), ("tool", "TL-001")]
    stack_via_supplier = [("global", None), ("supplier", "Foxconn"), ("tool", "TL-001")]

    out_part = nav.scope_df(shot_frame, stack_via_part)
    out_supplier = nav.scope_df(shot_frame, stack_via_supplier)

    # Without the exclusive-level fix, out_part would be filtered to Part-001
    # AND Tooling==TL-001 (just row 0), while out_supplier would be filtered
    # to Supplier==Foxconn AND Tooling==TL-001 (rows 0 and 1) -- two
    # different answers for the same tool. Both must now return every row
    # belonging to TL-001.
    assert sorted(out_part.index.tolist()) == [0, 1]
    assert sorted(out_supplier.index.tolist()) == [0, 1]
    assert sorted(out_part.index) == sorted(out_supplier.index)


def test_scope_df_exclusive_level_drops_an_ancestor_filter_that_would_exclude_it(shot_frame):
    # Part-002 has no rows at all in this fixture; if the Part ancestor
    # filter were still applied, this would return zero rows for TL-001.
    stack = [("part_all", None), ("part", "Part-002"),
             ("part_tools", None), ("tool", "TL-001")]
    out = nav.scope_df(shot_frame, stack)
    assert sorted(out.index.tolist()) == [0, 1]


def test_scope_df_non_exclusive_levels_still_apply_every_ancestor_frame(frame):
    """Control case: supplier (not exclusive) must still be narrowed by its
    geography ancestors, unlike tool."""
    stack = [("global", None), ("region", "APAC"), ("country", "China"), ("supplier", "Foxconn")]
    out = nav.scope_df(frame, stack)
    assert sorted(out["Tooling"]) == ["TL-001"]

    # Bosch Tooling never appears in APAC/China, so the ancestor frames must
    # still filter it out even though it IS Bosch Tooling's own frame.
    stack_mismatch = [("global", None), ("region", "APAC"), ("country", "China"),
                       ("supplier", "Bosch Tooling")]
    out_mismatch = nav.scope_df(frame, stack_mismatch)
    assert out_mismatch.empty


def test_scope_df_exclusive_level_with_missing_column_falls_through_to_ancestors():
    """If the exclusive ('tool') level's own filter column isn't present in
    the frame, there is nothing to supersede the ancestor filters with --
    the pre-fix code returned the WHOLE frame in that case (3 of 3 rows
    below), discarding the Supplier ancestor filter entirely and silently
    widening scope instead of narrowing it. The fix falls through to the
    normal ancestor loop, so Supplier="A" still applies and only the two
    rows belonging to Supplier A come back."""
    frame = pd.DataFrame({
        "Supplier": ["A", "A", "B"],
        "Part": ["P1", "P2", "P1"],
    })
    stack = [("global", None), ("supplier", "A"), ("tool", "T1")]
    out = nav.scope_df(frame, stack)
    assert sorted(out.index.tolist()) == [0, 1]


def test_scope_df_exclusive_level_with_none_value_falls_through_to_ancestors():
    """Same fallback, triggered by the exclusive frame's value being None
    instead of its column being missing."""
    frame = pd.DataFrame({
        "Supplier": ["A", "A", "B"],
        "Tooling": ["T1", "T2", "T1"],
    })
    stack = [("global", None), ("supplier", "A"), ("tool", None)]
    out = nav.scope_df(frame, stack)
    assert sorted(out.index.tolist()) == [0, 1]


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


# ---- nav epoch (defeats stale table selection on revisit) -----------------
def test_epoch_starts_at_zero(session_state):
    assert nav.nav_epoch() == 0


def test_epoch_increments_on_push(session_state):
    start = nav.nav_epoch()
    nav.push("region", "APAC")
    assert nav.nav_epoch() == start + 1
    nav.push("country", "China")
    assert nav.nav_epoch() == start + 2


def test_epoch_increments_on_pop_to(session_state):
    nav.push("region", "APAC")
    nav.push("country", "China")
    before = nav.nav_epoch()
    nav.pop_to(1)
    assert nav.nav_epoch() == before + 1


def test_epoch_increments_on_set_root(session_state):
    nav.push("region", "APAC")
    before = nav.nav_epoch()
    nav.set_root("type_all")
    assert nav.nav_epoch() == before + 1


def test_navigating_away_and_back_keeps_keyns_but_bumps_epoch(session_state):
    """The whole point of the fix: revisiting the same page produces the
    same widget-key namespace (unchanged behavior) but a different epoch,
    so drill tables get a fresh key that carries no stale selection."""
    nav.push("region", "APAC")
    key_first = nav.keyns()
    epoch_first = nav.nav_epoch()

    nav.push("country", "China")
    nav.pop_to(1)  # back to ("global", None), ("region", "APAC") -- same stack

    assert nav.get_stack() == [("global", None), ("region", "APAC")]
    key_second = nav.keyns()
    epoch_second = nav.nav_epoch()

    assert key_second == key_first
    assert epoch_second != epoch_first


def test_keyns_is_unaffected_by_epoch(session_state):
    stack = [("global", None), ("region", "APAC")]
    session_state[nav._STACK_KEY] = list(stack)
    session_state[nav._EPOCH_KEY] = 0
    key_at_epoch_0 = nav.keyns()

    session_state[nav._EPOCH_KEY] = 99
    key_at_epoch_99 = nav.keyns()

    assert key_at_epoch_0 == key_at_epoch_99
