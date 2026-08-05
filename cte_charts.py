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

TREND2_FOOTNOTE = (
    "Faster / Within / Slower = share of shots produced faster than, within "
    "(±tolerance of), or slower than the Approved Cycle Time · shot-weighted "
    "across all tools with cycle-time data · bars show all recorded shots. "
    "At or Better Than ACT = Faster% + Within%; it is a different measure "
    "from the Cycle Time Efficiency shown elsewhere, which is the shot-share "
    "weighted average of the three category efficiencies."
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
    # Not among trend_dim's current values (Global/Region/Country's own
    # trend_dim is 'Supplier'), but kept ready for future use.
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
        line=dict(color=ui.GREY, width=2.5), marker=dict(size=6),
        hovertemplate="<b>%{x}</b><br>Deviation: %{y:.2f}s<extra></extra>",
    ))
    fig.add_hline(y=0, line_dash="dash", line_color="#475569",
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
    ui.section("CT Split & Shot Trend", size="1.1rem")
    split = core.ct_split_shot_trend(df, freq)
    if split.empty:
        st.info("Not enough dated data to plot a trend.")
        return
    summ = core.ct_split_summary(df, freq)
    bucket_word = "active months" if freq == 'M' else "active quarters"
    st.markdown(
        f'<div class="v3-statline">'
        f'<b>At or Better Than ACT {summ["ct_compliance"]:.0f}%</b> &nbsp;·&nbsp; '
        f'<span style="color:{ui.RED};">Faster {summ["pct_fast"]:.0f}%</span> &nbsp;·&nbsp; '
        f'<span style="color:{ui.GREEN};">Within {summ["pct_within"]:.0f}%</span> &nbsp;·&nbsp; '
        f'<span style="color:{ui.YELLOW};">Slower {summ["pct_slow"]:.0f}%</span> &nbsp;·&nbsp; '
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
        ('Fast Shots (%)',   'Faster',  ui.RED,    'circle',        'top center'),
        ('Within Shots (%)', 'Within',  ui.GREEN,  'square',        'middle right'),
        ('Slow Shots (%)',   'Slower',  ui.YELLOW, 'triangle-up',   'bottom center'),
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
    )
    st.plotly_chart(fig, use_container_width=True, key=f"tr2_{keyns}")
    st.markdown(f'<div class="v3-footnote">{TREND2_FOOTNOTE}</div>', unsafe_allow_html=True)

    disp = s[['label'] + [c for c in core.CT_SPLIT_COLS if c != 'bucket']].copy()
    disp = disp.rename(columns={'label': period_word})
    st.dataframe(ui.style_table(disp, ui.TREND2_FMT), width="stretch", hide_index=True)


# --------------------------------------------------------------------------
# Pies
# --------------------------------------------------------------------------
def _pie_figure(values, height=250):
    fig = go.Figure(go.Pie(
        labels=['Fast', 'Within', 'Slow'], values=values, hole=0.55,
        marker=dict(colors=[ui.RED, ui.GREEN, ui.YELLOW],
                    line=dict(color='#0f1117', width=2)),
        textinfo='percent', textfont=dict(color='#0f1117', size=12, weight="bold"),
        hovertemplate="<b>%{label}</b><br>Tools: %{value}<br>%{percent}<extra></extra>",
        sort=False,
    ))
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      height=height, margin=dict(l=6, r=6, t=6, b=6), showlegend=False,
                      font=dict(color="#e2e8f0"))
    return fig


def small_multiple_pies(df, dim, tolerance_pct, keyns, max_pies=8):
    """One small pie per entity in `dim`, side by side — never one combined pie.

    Each pie is that entity's own Fast/Within/Slow split, counted over its
    tools (the same classification the summary tiles above use).
    """
    entities = sorted(df[dim].dropna().unique().tolist())
    if not entities:
        return
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
            st.markdown(f'<div style="text-align:center;color:#64748b;font-size:.78rem;">'
                        f'{s["total"]} tools</div>', unsafe_allow_html=True)
    if len(entities) > max_pies:
        st.caption(f"Showing {max_pies} of {len(entities)} {dim.lower()}s — "
                   f"use the Master Filter to narrow further.")


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
    """
    dims = [d for d in dims if d in df.columns]
    if not dims:
        return
    pick = st.radio("Rank by", dims, horizontal=True, key=f"rankdim_{keyns}")
    gain = core.ranking_by_financial(df, pick, 'Financial Gained', top_n, tolerance_pct)
    loss = core.ranking_by_financial(df, pick, 'Financial Lost', top_n, tolerance_pct)
    if gain.empty:
        st.info("No data available for this ranking.")
        return

    left, right = st.columns(2)
    for col, data, metric, color, title in [
        (left, gain, 'Financial Gained', ui.GREEN, f"Top {pick}s — Saving Opportunity"),
        (right, loss, 'Financial Lost', ui.YELLOW, f"Top {pick}s — Loss"),
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
            )
            st.plotly_chart(fig, use_container_width=True, key=f"rank_{keyns}_{metric}")
