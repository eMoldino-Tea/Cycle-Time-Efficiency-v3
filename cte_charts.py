"""
cte_charts.py
=============
Every chart v3 draws. Two trend graphs appear together at EVERY level:

  Trend Graph 1 -- ACT-Weighted Deviation. Reused unchanged from the Executive
                   dashboard (core.act_weighted_deviation_trend), including its
                   Month/Quarter toggle and its companion table.
  Trend Graph 2 -- CT Split & Shot Trend (new in v3): shot-volume bars plus
                   Faster / Within / Slower percentage lines, driven by
                   core.ct_split_shot_trend.

Both are scoped to whatever the current level is; the caller passes the
already-scoped, full-history frame.
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import cte_core as core
import cte_ui as ui

HOVERLABEL_LEFT = dict(align="left")

TREND2_FOOTNOTE = (
    "Fast / Within / Slow Shots = share of shots produced faster than, within "
    "(±tolerance of), or slower than the Approved Cycle Time · shot-weighted "
    "across all tools with cycle-time data · bars show all recorded shots. "
    "The Cycle Time Efficiency figure here = Fast Shots% + Within Shots% "
    "(share of shots at or better than the Approved Cycle Time) -- a "
    "DIFFERENT calculation from the Cycle Time Efficiency shown on tiles and "
    "tables elsewhere, which is a shot-share weighted average of each "
    "tier's own efficiency, not a share of shots."
)


def render_trend_block(trend_scope_df, trend_dim, keyns):
    """Both trend graphs + both companion tables, sharing one Month/Quarter toggle."""
    ui.section("Trend")
    gran_view = st.radio("View", ["Month to Month", "Quarter to Quarter"],
                         horizontal=True, key=f"gran_{keyns}")
    freq = 'M' if gran_view == "Month to Month" else 'Q'
    period_word = "Month" if freq == 'M' else "Quarter"

    _render_deviation_graph(trend_scope_df, trend_dim, freq, period_word, keyns)
    st.markdown("<hr style='border-color:#2d3748;margin:1.75rem 0;'>", unsafe_allow_html=True)
    _render_split_graph(trend_scope_df, freq, period_word, keyns)


# --------------------------------------------------------------------------
# Trend Graph 1 -- ACT-Weighted Deviation (unchanged from Executive)
# --------------------------------------------------------------------------
DIM_PLURAL = {
    'Supplier': 'Suppliers',
    'Tooling': 'Tools',
    'Tooling Type': 'Tooling Types',
    'Part': 'Parts',
    'Plant': 'Plants',
    'Project': 'Projects',
    'Region': 'Regions',
    'Country': 'Countries',
}


def _pluralize_dim(dim):
    """Pluralise a trend dimension name for the chart heading.

    A naive trailing-'s' pluraliser is wrong on two counts: it mangles a
    dimension ending in 'y' (e.g. 'Country' -> 'Countrys'), and for 'Tooling'
    it produces 'Toolings' while the rest of the app -- V3_DISPLAY_RENAME's
    'Total Toolings' -> 'Total Tools', the summary tiles, every table header
    -- says 'Tools'. An explicit mapping avoids both, and an unknown
    dimension fails loudly rather than silently producing a wrong word.
    """
    try:
        return DIM_PLURAL[dim]
    except KeyError:
        raise ValueError(f"_pluralize_dim: no plural mapping for dimension {dim!r}")


def _render_deviation_graph(df, dim, freq, period_word, keyns):
    # Finding 2: disclose which dimension this figure averages across, since
    # the same underlying data yields a different number at different levels
    # (each level averages across its own child entity -- see trend_dim in
    # cte_nav.LEVELS).
    ui.section(f"ACT-Weighted Deviation (averaged across {_pluralize_dim(dim)})",
               size="1.1rem")
    dev = core.act_weighted_deviation_trend(df, dim, freq)
    if dev.empty:
        st.info("Not enough dated data to plot a trend.")
        return
    dev = dev.copy()
    dev['label'] = dev['bucket'].apply(lambda x: ui.bucket_label(x, freq))

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dev['label'], y=dev['Weighted_Deviation'],
        mode="lines+markers", name="ACT-Weighted Deviation",
        line=dict(color=ui.WITHIN_COLOR, width=2.5), marker=dict(size=6),
        hovertemplate="<b>%{x}</b><br>Deviation: %{y:.2f}s<extra></extra>",
    ))
    fig.add_hline(y=0, line_dash="dash", line_color=ui.REFERENCE_LINE_COLOR,
                  annotation_text="On Target (ACT)", annotation_position="top left",
                  annotation_font_color="#94a3b8")
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        height=360, margin=dict(l=10, r=20, t=20, b=10),
        xaxis=dict(type='category', showgrid=False, tickfont=dict(color="#94a3b8")),
        yaxis=dict(showgrid=True, gridcolor="#334155",
                   title="ACT-Weighted Deviation (seconds)", tickfont=dict(color="#94a3b8")),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        font=dict(color="#e2e8f0"),
        hoverlabel=HOVERLABEL_LEFT,
    )
    st.plotly_chart(fig, use_container_width=True, key=f"tr1_{keyns}")

    t = dev.reset_index(drop=True)
    t['prev_dev'] = t['Weighted_Deviation'].shift(1)

    def _fmt_change(row):
        prev, curr = row['prev_dev'], row['Weighted_Deviation']
        if pd.isna(prev):
            return '—'
        diff = curr - prev
        if abs(diff) < 1e-9:
            return '→ 0.00s'
        return f"{'↑' if diff > 0 else '↓'} {abs(diff):.2f}s"

    t['Change vs Previous Period'] = t.apply(_fmt_change, axis=1)
    disp = t[['label', 'Weighted_Deviation', 'Change vs Previous Period']].copy()
    dev_col = f'{dim} ACT-Weighted Deviation (sec)'
    disp.columns = [period_word, dev_col, 'Change vs Previous Period']
    sty = (disp.style.format({dev_col: '{:.2f}'})
                    .map(ui.trend_change_css, subset=['Change vs Previous Period']))
    st.dataframe(sty, width="stretch", hide_index=True, column_config={
        dev_col: st.column_config.NumberColumn(
            help="Average seconds per shot vs the approved cycle time (ACT-weighted). "
                 "Negative = running faster than approved; positive = slower."),
        'Change vs Previous Period': st.column_config.TextColumn(
            help="Change in the deviation vs the prior period. ↓ (green) = deviation "
                 "shrank, moving toward the approved cycle time; ↑ (red) = it grew."),
    })


# --------------------------------------------------------------------------
# Trend Graph 2 -- CT Split & Shot Trend (new in v3)
# --------------------------------------------------------------------------
def _render_split_graph(df, freq, period_word, keyns):
    ui.section("Cycle Time Split & Shot Trend", size="1.1rem")
    split = core.ct_split_shot_trend(df, freq)
    if split.empty:
        st.info("Not enough dated data to plot a trend.")
        return
    summ = core.ct_split_summary(df, freq)
    bucket_word = "active months" if freq == 'M' else "active quarters"
    st.markdown(
        f'<div class="v3-statline">'
        f'<b>Cycle Time Efficiency {summ["ct_compliance"]:.0f}%</b> &nbsp;·&nbsp; '
        f'<span style="color:{ui.FAST_COLOR};">Fast Shots {summ["pct_fast"]:.0f}%</span> &nbsp;·&nbsp; '
        f'<span style="color:{ui.WITHIN_COLOR};">Within Shots {summ["pct_within"]:.0f}%</span> &nbsp;·&nbsp; '
        f'<span style="color:{ui.SLOW_COLOR};">Slow Shots {summ["pct_slow"]:.0f}%</span> &nbsp;·&nbsp; '
        f'{summ["total_shots"]:,} shots &nbsp;·&nbsp; '
        f'{summ["active_buckets"]} {bucket_word}</div>',
        unsafe_allow_html=True)

    s = split.copy()
    s['label'] = s['bucket'].apply(lambda x: ui.bucket_label(x, freq))

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=s['label'], y=s['Total Shots'], name="Shots",
        marker_color="#3f4757", yaxis="y",
        text=s['Total Shots'], texttemplate="%{text:.2s}", textposition="outside",
        textfont=dict(color="#94a3b8", size=10), cliponaxis=False,
        hovertemplate="<b>%{x}</b><br>Shots: %{y:,}<extra></extra>",
    ))
    # Data labels are staggered per series (top / right / bottom) so months with
    # close values never collide; exact figures are always in the unified hover.
    for col, name, color, symbol, textpos in [
        ('Fast Shots (%)',   'Faster',  ui.FAST_COLOR,   'circle',        'top center'),
        ('Within Shots (%)', 'Within',  ui.WITHIN_COLOR, 'square',        'middle right'),
        ('Slow Shots (%)',   'Slower',  ui.SLOW_COLOR,   'triangle-up',   'bottom center'),
    ]:
        fig.add_trace(go.Scatter(
            x=s['label'], y=s[col], name=name, yaxis="y2",
            mode="lines+markers+text", line=dict(color=color, width=2.5),
            marker=dict(size=8, symbol=symbol),
            text=s[col], texttemplate="%{text:.0f}%", textposition=textpos,
            textfont=dict(color=color, size=10), cliponaxis=False,
            hovertemplate="%{fullData.name}: %{y:.1f}%<extra></extra>",
        ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        height=440, margin=dict(l=10, r=20, t=30, b=10), hovermode="x unified",
        barmode="overlay",
        xaxis=dict(type='category', showgrid=False, tickfont=dict(color="#94a3b8")),
        yaxis=dict(title="Shots", showgrid=False, tickfont=dict(color="#94a3b8")),
        yaxis2=dict(title="Share of shots (%)", overlaying="y", side="right",
                    range=[0, 100], showgrid=True, gridcolor="#334155",
                    tickfont=dict(color="#94a3b8")),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        font=dict(color="#e2e8f0"),
        hoverlabel=HOVERLABEL_LEFT,
    )
    st.plotly_chart(fig, use_container_width=True, key=f"tr2_{keyns}")
    st.markdown(f'<div class="v3-footnote">{TREND2_FOOTNOTE}</div>', unsafe_allow_html=True)

    disp = s[['label'] + [c for c in core.CT_SPLIT_COLS if c != 'bucket']].copy()
    disp = disp.rename(columns={'label': period_word})
    st.dataframe(ui.style_table(ui.v3_display(disp), ui.TREND2_FMT),
                 width="stretch", hide_index=True)


# --------------------------------------------------------------------------
# Pies
# --------------------------------------------------------------------------
def _pie_figure(values, height=250):
    # Hover reads: tier name / "<n> tools" / percentage. The count is
    # pre-formatted per slice rather than interpolated with %{value} so a
    # single tool reads "1 tool" instead of "1 tools".
    counts = [f"{int(v):,} tool" if int(v) == 1 else f"{int(v):,} tools"
              for v in values]
    fig = go.Figure(go.Pie(
        labels=['Fast', 'Within', 'Slow'], values=values, hole=0.55,
        marker=dict(colors=[ui.FAST_COLOR, ui.WITHIN_COLOR, ui.SLOW_COLOR],
                    line=dict(color='#0f1117', width=2)),
        textinfo='percent', textfont=dict(color='#0f1117', size=12, weight="bold"),
        customdata=counts,
        hovertemplate=("<b>%{label}</b><br>Value: %{customdata}"
                       "<br>Percentage: %{percent}<extra></extra>"),
        sort=False,
    ))
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      height=height, margin=dict(l=6, r=6, t=6, b=6), showlegend=False,
                      font=dict(color="#e2e8f0"), hoverlabel=HOVERLABEL_LEFT)
    return fig


def small_multiple_pies(df, dim, tolerance_pct, keyns, max_pies=8):
    """One small pie per entity in `dim`, side by side — never one combined pie.

    Each pie is that entity's own Fast/Within/Slow split, counted over its
    tools (the same classification the summary tiles above use).

    Returns the entity whose caption was clicked this run, else None.
    """
    entities = sorted(df[dim].dropna().unique().tolist())
    if not entities:
        return None
    clicked = None
    shown = entities[:max_pies]
    cols = st.columns(len(shown), gap="small")
    for col, ent in zip(cols, shown):
        with col:
            sub = df[df[dim] == ent]
            s = core.fast_within_slow_summary(sub, 'Tooling', tolerance_pct)
            # `ent` is a real entity value (region / country / supplier
            # name, ...) that can originate from an operator-supplied CSV.
            st.markdown(f'<div style="text-align:center;color:#e2e8f0;font-size:.92rem;'
                        f'font-weight:600;margin-bottom:2px;">{ui.esc(ent)}</div>',
                        unsafe_allow_html=True)
            st.plotly_chart(_pie_figure([s['fast'], s['within'], s['slow']]),
                            use_container_width=True, key=f"pie_{keyns}_{dim}_{ent}")
            # The caption is the click target rather than the slice itself:
            # Streamlit's plotly selection API is built around cartesian
            # charts, so pie-slice clicks are not dependable. A button styled
            # as the caption keeps the pies visually untouched and the whole
            # affordance obvious.
            if st.button(f'{s["total"]} tools', key=f"piebtn_{keyns}_{dim}_{ent}",
                         help=f"View {ent} tools"):
                clicked = ent
    if len(entities) > max_pies:
        st.caption(f"Showing {max_pies} of {len(entities)} {dim.lower()}s — "
                   f"use the Master Filter to narrow further.")
    return clicked


def single_pie(df, tolerance_pct, keyns, title="Cycle Time Efficiency Split"):
    s = core.fast_within_slow_summary(df, 'Tooling', tolerance_pct)
    if s['total'] == 0:
        st.info("No data available for this metric.")
        return
    # `title` frequently embeds the caller's ctx.value (e.g. a supplier or
    # tooling-type name) -- escape it; the default literal escapes to itself.
    st.markdown(f'<div style="text-align:center;color:#e2e8f0;font-size:1.05rem;'
                f'font-weight:600;margin-bottom:4px;">{ui.esc(title)}</div>', unsafe_allow_html=True)
    st.plotly_chart(_pie_figure([s['fast'], s['within'], s['slow']], height=320),
                    use_container_width=True, key=f"pie1_{keyns}")


# --------------------------------------------------------------------------
# Rankings
# --------------------------------------------------------------------------
def ranking_bars(df, dims, tolerance_pct, keyns, top_n=10):
    """Saving-opportunity and loss rankings across one or more dimensions.

    `dims` is a list of record columns, e.g. ['Region', 'Country', 'Supplier',
    'Tooling', 'Part', 'Tooling Type'] for the Global Overview. Rendered as a
    dimension picker plus paired gain/loss bar charts, so all six rankings are
    available without six stacked charts.

    Returns (dimension, entity) for a clicked bar, else None.
    """
    dims = [d for d in dims if d in df.columns]
    if not dims:
        return
    pick = st.radio("Rank by", dims, horizontal=True, key=f"rankdim_{keyns}")
    gain = core.ranking_by_financial(df, pick, 'Financial Gained', top_n, tolerance_pct)
    loss = core.ranking_by_financial(df, pick, 'Financial Lost', top_n, tolerance_pct)
    if gain.empty:
        st.info("No data available for this ranking.")
        return None
    clicked = None

    left, right = st.columns(2)
    for col, data, metric, color, title in [
        (left, gain, 'Financial Gained', ui.FAST_COLOR, f"Top {pick}s — Saving Opportunity"),
        (right, loss, 'Financial Lost', ui.SLOW_COLOR, f"Top {pick}s — Loss"),
    ]:
        with col:
            st.markdown(f'<div style="color:#e2e8f0;font-size:1rem;font-weight:600;'
                        f'margin-bottom:4px;">{ui.esc(title)}</div>', unsafe_allow_html=True)
            d = data.sort_values(metric)
            fig = go.Figure(go.Bar(
                x=d[metric], y=d[pick].astype(str), orientation='h',
                marker_color=color, text=d[metric], texttemplate="$%{text:,.0f}",
                textposition="outside", cliponaxis=False,
                hovertemplate="<b>%{y}</b><br>$%{x:,.0f}<extra></extra>",
            ))
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                height=max(260, 34 * len(d)), margin=dict(l=10, r=60, t=10, b=10),
                xaxis=dict(showgrid=True, gridcolor="#334155", tickfont=dict(color="#94a3b8"),
                           title="US$"),
                yaxis=dict(type='category', showgrid=False, tickfont=dict(color="#e2e8f0")),
                font=dict(color="#e2e8f0"), showlegend=False,
                hoverlabel=HOVERLABEL_LEFT,
            )
            sel = st.plotly_chart(fig, use_container_width=True,
                                  key=f"rank_{keyns}_{metric}",
                                  on_select="rerun", selection_mode="points")
            # Bars are cartesian, where Streamlit's point selection works --
            # the y value of the clicked point is the entity name.
            pts = (sel or {}).get("selection", {}).get("points", [])
            if pts:
                clicked = (pick, pts[0].get("y"))
    return clicked


# --------------------------------------------------------------------------
# Detailed Analysis -- the selected-item summary shown at every tier below a
# root tab. Layout carried over from the Executive dashboard's report card
# (5 KPIs, then a trend/donut pair), so a reader moving between the two apps
# sees the same thing.
# --------------------------------------------------------------------------
def _weekly_efficiency_trend(df):
    """Weighted CT Efficiency % per week, for the Historical Trend panel.

    Weekly buckets (not the monthly/quarterly buckets the two big trend
    graphs use) because this panel is scoped to the selected item and the
    selected period, where weeks give a readable number of points.
    """
    if df is None or df.empty or 'Date' not in df.columns:
        return pd.DataFrame(columns=['bucket', 'Efficiency_%'])
    d = df.copy()
    d['bucket'] = d['Date'].dt.to_period('W').dt.start_time
    return (d.groupby('bucket')
             .apply(core.calc_weighted_eff)
             .reset_index(name='Efficiency_%')
             .dropna(subset=['Efficiency_%'])
             .sort_values('bucket'))


def render_detailed_analysis(scope, label, keyns, period_label, tolerance_pct,
                             group_col='Tooling ID'):
    """Selected-item summary: badge, 5 KPIs, then trend + distribution.

    Rendered for whatever is currently selected -- a region, country,
    supplier, plant, tooling type, project, part or tool -- with only the
    badge name and the underlying data changing. Every figure comes from
    compute_comprehensive_row on the selected scope, so this panel can never
    disagree with the tables below it.

    Zero-state is deliberate rather than collapsed: a selection with no
    records still renders its KPIs at 0/$0 with an explanatory message in
    each panel, so an empty result reads as "nothing here in this period"
    instead of a page that looks broken.
    """
    ui.entity_badge("Detailed Analysis:", label)

    empty = scope is None or scope.empty
    if empty:
        eff = gained = lost = saving = loss = 0.0
    else:
        row = core.compute_comprehensive_row(label, scope, group_col, period_label,
                                             tolerance_pct=tolerance_pct)
        eff = row['CT Weighted Average Efficiency']
        gained, lost = row['Hours Gained'], row['Hours Lost']
        saving, loss = row['Financial Gain'], row['Financial Loss']

    kpis = [
        ("Overall Cycle Time Efficiency %",
         "0%" if empty or pd.isna(eff) else f"{eff:.1f}%"),
        ("Total Hours Gained (Fast)", core.format_hm(gained)),
        ("Total Hours Lost (Slow)", core.format_hm(lost)),
        ("Saving Opportunity (from fast shots)", f"${saving:,.0f}"),
        ("Loss (from slow shots)", f"${loss:,.0f}"),
    ]
    for col, (klabel, kvalue) in zip(st.columns(5), kpis):
        with col:
            st.markdown(f'<div class="v3-kpi-label">{ui.esc(klabel)}</div>'
                        f'<div class="v3-kpi-value">{ui.esc(kvalue)}</div>',
                        unsafe_allow_html=True)

    st.markdown("<hr style='border-color:#2d3748;margin:1.5rem 0;'>", unsafe_allow_html=True)

    left, right = st.columns([1.4, 1])
    with left:
        ui.section("Historical Trend: Cycle Time Efficiency %", size="1.1rem")
        trend = pd.DataFrame() if empty else _weekly_efficiency_trend(scope)
        if trend.empty:
            st.info("No data for selected period.")
        else:
            lfig = go.Figure()
            lfig.add_trace(go.Scatter(
                x=trend['bucket'], y=trend['Efficiency_%'],
                mode="lines+markers", line=dict(color=ui.WITHIN_COLOR, width=2.5),
                marker=dict(size=6),
                hovertemplate="<b>%{x|%b %d, %Y}</b><br>Efficiency: %{y:.2f}%<extra></extra>",
            ))
            lfig.add_hline(y=100, line_dash="dash", line_color=ui.REFERENCE_LINE_COLOR)
            lfig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                height=380, margin=dict(l=10, r=20, t=20, b=10),
                xaxis=dict(showgrid=False, tickfont=dict(color="#94a3b8"), title="Date"),
                yaxis=dict(showgrid=True, gridcolor="#334155", title="Efficiency_%",
                           tickfont=dict(color="#94a3b8")),
                font=dict(color="#e2e8f0"), hoverlabel=HOVERLABEL_LEFT,
            )
            st.plotly_chart(lfig, use_container_width=True, key=f"da_trend_{keyns}")
    with right:
        ui.section("Efficiency Distribution", size="1.1rem")
        if empty:
            st.info("No data for selected period.")
        else:
            vals = [row.get('Fast Shots (%)', 0) or 0,
                    row.get('Within Shots (%)', 0) or 0,
                    row.get('Slow Shots (%)', 0) or 0]
            rpie = go.Figure(go.Pie(
                labels=['Fast', 'Within', 'Slow'], values=vals, hole=0.55,
                marker=dict(colors=[ui.FAST_COLOR, ui.WITHIN_COLOR, ui.SLOW_COLOR],
                            line=dict(color='#0f1117', width=2)),
                textinfo='percent',
                textfont=dict(color='#0f1117', size=13, weight="bold"),
                hovertemplate="<b>%{label}</b><br>Percentage: %{value:.1f}%<extra></extra>",
            ))
            rpie.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                height=380, margin=dict(l=10, r=10, t=10, b=10), showlegend=True,
                legend=dict(orientation="v", yanchor="middle", y=0.5,
                            xanchor="left", x=1.02,
                            font=dict(color="#e2e8f0", size=12)),
                font=dict(color="#e2e8f0"), hoverlabel=HOVERLABEL_LEFT,
            )
            st.plotly_chart(rpie, use_container_width=True, key=f"da_pie_{keyns}")
