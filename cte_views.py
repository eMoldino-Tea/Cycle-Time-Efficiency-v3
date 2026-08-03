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
        use_container_width=True, hide_index=True,
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


def render_supplier(ctx):
    """Part C section 4 — individual supplier overview."""
    ui.entity_badge("Supplier:", ctx.value)

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
    ch.render_trend_block(ctx.trend, nav.LEVELS['supplier']['trend_dim'], ctx.keyns)

    st.markdown("<hr style='border-color:#2d3748;margin:1.75rem 0;'>", unsafe_allow_html=True)
    ui.section("Tool Detail")
    st.caption("Select a row to open that tool's report.")
    tools = _tool_table(ctx.scope, ctx.period_label, ctx.tolerance_pct)
    if tools.empty:
        st.info("No tool data for this supplier.")
        return
    top = st.columns([3, 1])
    with top[0]:
        view = ui.search_box(tools, f"tool_{ctx.keyns}")
    with top[1]:
        st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
        ui.download_csv(ui.v3_display(view), "Export CSV",
                        f"{ctx.value}_tools.csv", f"tool_{ctx.keyns}")
    _table_drill(view, 'Tooling ID', 'tool', f"tool_{ctx.keyns}")


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
