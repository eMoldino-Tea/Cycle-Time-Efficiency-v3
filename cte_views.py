"""
cte_views.py
============
One renderer per v3 level. Every renderer receives the same Ctx and draws:
summary tiles -> pies -> rankings -> two trend graphs -> a drillable table.

Levels 1-3 (Global / Region / Country) are the same page with a different
child dimension, so they share render_scope_overview.
"""

from dataclasses import dataclass

import pandas as pd
import streamlit as st

import cte_charts as ch
import cte_core as core
import cte_nav as nav
import cte_ui as ui


@dataclass
class Ctx:
    """Everything a level renderer needs.

    scope: the current-period, master-filtered, level-scoped frame.
    trend: the same scope over the FULL history (ignores the sidebar Time
           Range) — both trend graphs use this.
    """
    scope: pd.DataFrame
    trend: pd.DataFrame
    level: str
    value: object
    tolerance_pct: float
    period_label: str
    keyns: str


def _drill(level, value):
    nav.push(level, value)
    st.rerun()


def _table_drill(df, label_col, level, keyns):
    """Render a table whose row click drills into `level`.

    The widget key folds in nav.nav_epoch() (in addition to keyns) so that
    every navigation event -- including navigating back to a previously
    visited page, where keyns() alone would reproduce an identical key --
    gets a fresh table with no inherited row selection. Without this, a
    stale selection surviving in session state would immediately re-fire
    _drill and bounce the user right back into the child level they just
    left. keyns() itself must stay untouched by the epoch: it also
    namespaces the granularity and Rank-by radios, which need to keep the
    user's choice across navigation rather than resetting every drill.
    """
    event = st.dataframe(
        ui.style_table(ui.v3_display(df), ui.DETAIL_FMT),
        width="stretch", hide_index=True,
        on_select="rerun", selection_mode="single-row",
        key=f"tbl_{keyns}_{nav.nav_epoch()}", column_config=ui.neg_help(df))
    if event and event.selection and event.selection.rows:
        idx = event.selection.rows[0]
        if idx < len(df):
            _drill(level, df.iloc[idx][label_col])


def render_scope_overview(ctx):
    """Global (level 1), Region (2) and Country (3) overviews.

    Child dimension drives the pies: Global -> one pie per Region, Region ->
    one pie per Country, Country -> one pie per Supplier. Always small
    multiples, never a single combined pie.
    """
    cfg = nav.LEVELS[ctx.level]
    child_dim = nav.LEVELS[cfg['child']]['col']

    # --- A. Summary ---
    ui.section("Summary")
    ui.summary_tiles(core.scope_summary(ctx.scope, ctx.tolerance_pct), cfg['entity_noun'])

    st.markdown("<br>", unsafe_allow_html=True)
    ui.section(f"Cycle Time Efficiency by {child_dim}", size="1.1rem")
    ch.small_multiple_pies(ctx.scope, child_dim, ctx.tolerance_pct, ctx.keyns)

    st.markdown("<br>", unsafe_allow_html=True)
    ui.section("Saving Opportunity & Loss Ranking", size="1.1rem")
    ch.ranking_bars(ctx.scope, _ranking_dims(ctx.level), ctx.tolerance_pct, ctx.keyns)

    # --- B. Trend ---
    st.markdown("<hr style='border-color:#2d3748;margin:1.75rem 0;'>", unsafe_allow_html=True)
    ch.render_trend_block(ctx.trend, cfg['trend_dim'], ctx.keyns)

    # --- Finding 1: child geography detail table -----------------------------
    # Global's child is Region and Region's child is Country -- neither was
    # ever reachable before, since the only clickable table on this shared
    # page was Supplier Detail below. Country's own child already IS
    # Supplier, so it just keeps that one table (no separate geography table
    # would add anything). Own widget-key prefix (keyed off the child level,
    # e.g. "region_"/"country_") so it can never collide with "sup_" below.
    if child_dim != 'Supplier':
        child_level = cfg['child']
        child_label = nav.LEVELS[child_level]['label']
        st.markdown("<hr style='border-color:#2d3748;margin:1.75rem 0;'>", unsafe_allow_html=True)
        ui.section(f"{child_label} Detail")
        st.caption(f"Select a row to open that {child_label.lower()}.")
        geo = core.entity_detail_table(ctx.scope, child_dim,
                                       period_label=ctx.period_label,
                                       tolerance_pct=ctx.tolerance_pct)
        if geo.empty:
            st.info(f"No {child_label.lower()} data for this scope.")
        else:
            geo_cols = [child_dim] + [c for c in core.V3_GEO_COLS if c in geo.columns]
            geo = geo[geo_cols]
            gtop = st.columns([3, 1])
            with gtop[0]:
                gview = ui.search_box(geo, f"{child_level}_{ctx.keyns}")
            with gtop[1]:
                st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
                ui.download_csv(ui.v3_display(gview), "Export CSV",
                                f"{ch.DIM_PLURAL[child_dim].lower()}.csv",
                                f"{child_level}_{ctx.keyns}")
            _table_drill(gview, child_dim, child_level, f"{child_level}_{ctx.keyns}")

    # --- Supplier detail table (click a supplier to drill in) ---
    st.markdown("<hr style='border-color:#2d3748;margin:1.75rem 0;'>", unsafe_allow_html=True)
    ui.section("Supplier Detail")
    st.caption("Select a row to open that supplier's tools.")
    sup = core.entity_detail_table(ctx.scope, 'Supplier', extra_cols=('Country',),
                                   period_label=ctx.period_label,
                                   tolerance_pct=ctx.tolerance_pct)
    if sup.empty:
        st.info("No supplier data for this scope.")
        return
    sup = sup[[c for c in core.V3_SUPPLIER_COLS if c in sup.columns]]
    top = st.columns([3, 1])
    with top[0]:
        view = ui.search_box(sup, f"sup_{ctx.keyns}")
    with top[1]:
        st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
        ui.download_csv(ui.v3_display(view), "Export CSV", "suppliers.csv", f"sup_{ctx.keyns}")
    _table_drill(view, 'Supplier', 'supplier', f"sup_{ctx.keyns}")


def _ranking_dims(level):
    """Part C's ranking dimensions per level.

    Global (D8) ranks by Region, Country, Supplier, Tool, Part AND Tooling
    Type; Region drops Region; Country drops Region and Country.
    """
    if level == 'global':
        return ['Region', 'Country', 'Supplier', 'Tooling', 'Part', 'Tooling Type']
    if level == 'region':
        return ['Country', 'Supplier', 'Tooling', 'Part']
    return ['Supplier', 'Tooling', 'Part']


def _tool_table(df, period_label, tolerance_pct):
    """Tool rows in v3's canonical tool-table shape (Part C decision 9)."""
    t = core.entity_detail_table(df, 'Tooling',
                                 extra_cols=('Region', 'Country', 'Plant'),
                                 period_label=period_label, tolerance_pct=tolerance_pct)
    if t.empty:
        return t
    t = t.rename(columns={'Tooling': 'Tooling ID'})
    return t[[c for c in core.V3_TOOL_COLS if c in t.columns]]


def render_entity_tools(ctx):
    """One entity that owns tools, plus its tool list.

    Serves `supplier` (spec 4), `type` and `plant`. Those three pages were
    line-for-line identical apart from the entity's label -- a duplication a
    review flagged as the leverage point to fix before another renderer was
    added, which is exactly what adding Plant would have been. The label and
    trend dimension come from the registry.
    """
    cfg = nav.LEVELS[ctx.level]
    if ctx.scope.empty:
        st.info("No data available for this selection.")
        return
    ui.entity_badge(f"{cfg['label']}:", ctx.value)

    ui.section("Summary")
    ui.summary_tiles(core.scope_summary(ctx.scope, ctx.tolerance_pct), "Tools")

    st.markdown("<br>", unsafe_allow_html=True)
    pie_col, rank_col = st.columns([1, 2])
    with pie_col:
        ch.single_pie(ctx.scope, ctx.tolerance_pct, ctx.keyns,
                      title=f"{ctx.value} — Fast / Within / Slow")
    with rank_col:
        ui.section("Saving Opportunity & Loss by Tool", size="1.1rem")
        ch.ranking_bars(ctx.scope, ['Tooling'], ctx.tolerance_pct, ctx.keyns)

    st.markdown("<hr style='border-color:#2d3748;margin:1.75rem 0;'>", unsafe_allow_html=True)
    ch.render_trend_block(ctx.trend, cfg['trend_dim'], ctx.keyns)

    st.markdown("<hr style='border-color:#2d3748;margin:1.75rem 0;'>", unsafe_allow_html=True)
    ui.section("Tool Detail")
    st.caption("Select a row to open that tool's report.")
    tools = _tool_table(ctx.scope, ctx.period_label, ctx.tolerance_pct)
    if tools.empty:
        st.info("No tool data for this selection.")
        return
    key = f"ent_{ctx.keyns}"
    top = st.columns([3, 1])
    with top[0]:
        view = ui.search_box(tools, key)
    with top[1]:
        st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
        ui.download_csv(ui.v3_display(view), "Export CSV",
                        f"{ctx.value}_tools.csv", key)
    _table_drill(view, 'Tooling ID', 'tool', key)


def render_tool(ctx):
    """Part C sections 6 / 7.1.a — the individual tool report page.

    Reachable from a supplier, a tooling type, or a part's tool list; the
    breadcrumb shows whichever path was taken.
    """
    if ctx.scope.empty:
        st.info("No data available for this tool.")
        return
    row = core.compute_comprehensive_row(ctx.value, ctx.scope, 'Tooling ID',
                                         ctx.period_label, tolerance_pct=ctx.tolerance_pct)
    ui.entity_badge("Tool:", ctx.value)

    parts = sorted(ctx.scope['Part'].dropna().unique().tolist())
    part_names = (ctx.scope[['Part', 'Part Name']].drop_duplicates()
                                                  .set_index('Part')['Part Name'].to_dict())

    a, b, c, d = st.columns(4)
    a.metric("Supplier", ", ".join(sorted(ctx.scope['Supplier'].unique())))
    b.metric("Plant", ", ".join(sorted(ctx.scope['Plant'].unique())))
    c.metric("Region", ", ".join(sorted(ctx.scope['Region'].unique())))
    d.metric("Country", ", ".join(sorted(ctx.scope['Country'].unique())))

    # Part C section 6: one part shows inline; more than one shows the count
    # and opens a dropdown listing them all.
    if len(parts) == 1:
        st.markdown(f'**Part:** {parts[0]} ({part_names.get(parts[0], "")})')
    else:
        part_options = [f"{p} ({part_names.get(p, '')})" for p in parts]
        st.selectbox(
            f"Parts ({len(parts)})",
            options=part_options,
            key=f"part_select_{ctx.keyns}"
        )

    e, f, g, h = st.columns(4)
    e.metric("Approved Cycle Time (ACT)", f"{row['ACT']:.2f}s")
    f.metric("WACT", f"{row['Actual Average CT (WACT)']:.2f}s")
    _eff = row['CT Weighted Average Efficiency']
    g.metric("Cycle Time Efficiency", f"{_eff:.1f}%" if pd.notna(_eff) else "N/A")
    h.metric("Net Financial", f"${row['Net Financial']:,.0f}",
             help="Saving Opportunity − Loss. Negative = net cost overrun for the period.")

    i, j, k, m, n = st.columns(5)
    i.metric("Fast Shots", f"{row['Fast Shots (%)']:.1f}%")
    j.metric("Within Shots", f"{row['Within Shots (%)']:.1f}%")
    k.metric("Slow Shots", f"{row['Slow Shots (%)']:.1f}%")
    m.metric("Saving Opportunity", f"${row['Financial Gain']:,.0f}")
    n.metric("Loss", f"${row['Financial Loss']:,.0f}")

    st.markdown("<hr style='border-color:#2d3748;margin:1.75rem 0;'>", unsafe_allow_html=True)
    ch.render_trend_block(ctx.trend, 'Tooling', ctx.keyns)


def _all_level_cols(entity_col):
    """Detail-table column set for an "all entities" page.

    Region, Country and Plant share the V3_GEO_COLS tail with their own
    entity column prepended; Supplier, Tooling Type and Part have their own
    spec'd column sets.
    """
    if entity_col == 'Supplier':
        return core.V3_SUPPLIER_COLS
    if entity_col == 'Tooling Type':
        return core.V3_TYPE_COLS
    if entity_col == 'Part':
        return core.V3_PART_COLS
    return [entity_col] + core.V3_GEO_COLS


def render_dimension_all(ctx):
    """The "all entities in one dimension" landing page behind each root tab.

    Serves region_all, country_all, supplier_all, plant_all, type_all and
    part_all: the same page over a different entity dimension, read from the
    registry. Adding a root tab is therefore a LEVELS entry plus a RENDERERS
    line, not another near-duplicate renderer.
    """
    cfg = nav.LEVELS[ctx.level]
    child_level = cfg['child']
    entity_col = nav.LEVELS[child_level]['col']

    ui.section("Summary")
    ui.summary_tiles(
        core.scope_summary(ctx.scope, ctx.tolerance_pct,
                           entity_dim=cfg.get('count_dim', 'Tooling')),
        cfg['entity_noun'])

    if cfg.get('show_pies', True):
        st.markdown("<br>", unsafe_allow_html=True)
        ui.section(f"Cycle Time Efficiency by {entity_col}", size="1.1rem")
        ch.small_multiple_pies(ctx.scope, entity_col, ctx.tolerance_pct, ctx.keyns)

    st.markdown("<br>", unsafe_allow_html=True)
    ui.section(f"Saving Opportunity & Loss by {entity_col}", size="1.1rem")
    ch.ranking_bars(ctx.scope, [entity_col], ctx.tolerance_pct, ctx.keyns)

    st.markdown("<hr style='border-color:#2d3748;margin:1.75rem 0;'>", unsafe_allow_html=True)
    ch.render_trend_block(ctx.trend, cfg['trend_dim'], ctx.keyns)

    st.markdown("<hr style='border-color:#2d3748;margin:1.75rem 0;'>", unsafe_allow_html=True)
    ui.section(f"{entity_col} Detail")
    st.caption(f"Select a row to open that {entity_col.lower()}.")
    if entity_col == 'Part':
        extra = ('Part Name',)
    elif entity_col == 'Supplier':
        extra = ('Country',)
    else:
        extra = ()
    t = core.entity_detail_table(ctx.scope, entity_col, extra_cols=extra,
                                 period_label=ctx.period_label,
                                 tolerance_pct=ctx.tolerance_pct)
    if t.empty:
        st.info(f"No {entity_col.lower()} data for this scope.")
        return
    t = t[[c for c in _all_level_cols(entity_col) if c in t.columns]]
    key = f"all_{ctx.keyns}"
    _table_drill(ui.search_box(t, key), entity_col, child_level, key)


def render_part(ctx):
    """One selected part's detail report."""
    if ctx.scope.empty:
        st.info("No data available for this part.")
        return
    names = sorted(ctx.scope['Part Name'].dropna().unique().tolist())
    ui.entity_badge("Part:", f"{ctx.value} — {', '.join(names)}" if names else str(ctx.value))

    row = core.compute_comprehensive_row(ctx.value, ctx.scope, 'Part', ctx.period_label,
                                         tolerance_pct=ctx.tolerance_pct)
    n_tools = core.tool_count(ctx.scope)

    a, b, c, d = st.columns(4)
    with a:
        st.metric("Total Tools", f"{n_tools:,}")
        if st.button("View tools →", key=f"parttools_{ctx.keyns}"):
            _drill('part_tools', None)
    _eff = row['CT Weighted Average Efficiency']
    b.metric("Cycle Time Efficiency", f"{_eff:.1f}%" if pd.notna(_eff) else "N/A")
    c.metric("Saving Opportunity", f"${row['Financial Gain']:,.0f}")
    d.metric("Loss", f"${row['Financial Loss']:,.0f}")

    e, f, g = st.columns(3)
    e.metric("Fast Shots", f"{row['Fast Shots (%)']:.1f}%")
    f.metric("Within Shots", f"{row['Within Shots (%)']:.1f}%")
    g.metric("Slow Shots", f"{row['Slow Shots (%)']:.1f}%")

    st.markdown("<hr style='border-color:#2d3748;margin:1.75rem 0;'>", unsafe_allow_html=True)
    ch.render_trend_block(ctx.trend, 'Tooling', ctx.keyns)


def render_part_tools(ctx):
    """Part C section 7.1 — the list of tools making the selected part.

    Deliberately exempt from Finding 2's exclusive-tool fix: this table is a
    breakdown OF the selected part, so its figures stay part-scoped even
    though the tool report you drill into from here shows whole-tool figures
    (scope_df drops the Part ancestor filter once you're actually on the
    'tool' level, since that level is marked exclusive).
    """
    ui.section("Tools Making This Part")
    st.caption("Select a row to open that tool's report.")
    st.caption("Figures below are scoped to this part only — a tool's own "
               "report (after you click through) shows that tool's whole-tool figures.")
    tools = _tool_table(ctx.scope, ctx.period_label, ctx.tolerance_pct)
    if tools.empty:
        st.info("No tools found for this part.")
        return
    _table_drill(ui.search_box(tools, f"pt_{ctx.keyns}"), 'Tooling ID', 'tool', f"pt_{ctx.keyns}")


RENDERERS = {
    'global': render_scope_overview,
    'region': render_scope_overview,
    'country': render_scope_overview,
    'region_all': render_dimension_all,
    'country_all': render_dimension_all,
    'supplier_all': render_dimension_all,
    'plant_all': render_dimension_all,
    'type_all': render_dimension_all,
    'part_all': render_dimension_all,
    'supplier': render_entity_tools,
    'type': render_entity_tools,
    'plant': render_entity_tools,
    'part': render_part,
    'part_tools': render_part_tools,
    'tool': render_tool,
}
