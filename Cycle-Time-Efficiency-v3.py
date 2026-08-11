"""
Cycle-Time-Efficiency-v3.py
===========================
Cycle Time Efficiency -- v3 DRILL-DOWN DASHBOARD

Same feature, same math, new information architecture. The Executive
dashboard's two flat tabs are replaced by a hierarchical drill-down:

    Global -> Region -> Country -> Supplier -> Tool

plus two cross-cutting parallel views (Tooling Type and Part) over the same
flat Tool table. Every calculation is reused from cte_core.py unchanged.

This file is intentionally thin: settings -> data -> filters -> dispatch.
Rendering lives in cte_views / cte_charts / cte_ui; navigation in cte_nav.

Three tiers, driven by the sidebar tolerance band (default +/-5%):
  Fast   : CT Efficiency > 100 + tolerance
  Within : 100 - tolerance ... 100 + tolerance
  Slow   : CT Efficiency < 100 - tolerance
"""

import pandas as pd
import streamlit as st

import cte_core as core
import cte_nav as nav
import cte_ui as ui
import cte_views as views
import sample_data_loader

st.set_page_config(
    page_title="Cycle Time Efficiency — v3",
    layout="wide",
    initial_sidebar_state="expanded",
)
ui.inject_theme()

# ==========================================================================
# DATA
# ==========================================================================
base_df = core.load_base_data(version=11)

_sample = sample_data_loader.load_sample_data_if_present()
if _sample is not None:
    base_df, _sample_filename = _sample
    st.sidebar.success(f"Using sample data: {_sample_filename}")

# Guarantee explicit geography even for a sample CSV that predates v3.
base_df = core.ensure_geo_columns(base_df)

# ==========================================================================
# SETTINGS (sidebar)
# ==========================================================================
st.sidebar.markdown("### Classification Tolerance")
tolerance_pct = st.sidebar.slider(
    "Tolerance band (± % around ACT)",
    min_value=1.0, max_value=10.0, value=core.DEFAULT_TOLERANCE_PCT, step=0.5,
    help="Records within this band of the approved cycle time count as Within. "
         "Also sets the Fast/Slow performance thresholds at 100 ± tolerance.",
)
base_df = core.apply_tolerance(base_df, tolerance_pct)

min_date, max_date = base_df['Date'].min(), base_df['Date'].max()

st.sidebar.markdown("---")
st.sidebar.markdown("### Time Range")
time_range = st.sidebar.radio("Select range", core.TIME_RANGE_PRESETS, index=1)
if time_range == "Custom Range":
    c1, c2 = st.sidebar.columns(2)
    s_in = c1.date_input("Start", min_date.date(), max_value=max_date.date())
    e_in = c2.date_input("End", max_date.date(), max_value=max_date.date())
    start_date = pd.to_datetime(s_in)
    end_date = pd.to_datetime(e_in) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
else:
    start_date, end_date = core.resolve_time_range(time_range, max_date)

st.sidebar.markdown("---")
st.sidebar.markdown("### Financial Parameters")
labor_rate = st.sidebar.number_input("Labor Rate ($/hour)", min_value=0.0, value=40.0, step=1.0)
machine_rate = st.sidebar.number_input("Machine Rate ($/hour)", min_value=0.0, value=180.0, step=1.0)

# ==========================================================================
# HIGH-RUNNER TOOL FILTER
# ==========================================================================
# Restricts the whole dashboard to tools whose average daily parts output
# reaches a configured threshold. Its evaluation period is deliberately
# separate from the Time Range above: "is this a high-volume tool" is a
# property of the tool, so you may well want to judge it over 12 months
# while looking at last week's cycle-time performance.
st.sidebar.markdown("---")
st.sidebar.markdown("### High-Runner Tool Filter")
hr_min_avg = st.sidebar.number_input(
    "Min. average parts produced per day",
    min_value=core.HIGH_RUNNER_MIN_AVG_PARTS,
    value=core.HIGH_RUNNER_MIN_AVG_PARTS,
    step=50,
    help="A tool counts as a high runner when its parts produced per day, "
         "averaged over the evaluation period below, reaches this number. "
         "Parts Produced = shots × mold cavities.",
)
hr_period = st.sidebar.radio("Evaluation period", core.TIME_RANGE_PRESETS,
                             index=1, key="hr_period")
if hr_period == "Custom Range":
    _hc1, _hc2 = st.sidebar.columns(2)
    _hr_s = _hc1.date_input("Start", min_date.date(), max_value=max_date.date(),
                            key="hr_custom_start")
    _hr_e = _hc2.date_input("End", max_date.date(), max_value=max_date.date(),
                            key="hr_custom_end")
    hr_start = pd.to_datetime(_hr_s)
    hr_end = pd.to_datetime(_hr_e) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
else:
    hr_start, hr_end = core.resolve_time_range(hr_period, max_date)
hr_display = st.sidebar.radio("Display", core.HIGH_RUNNER_DISPLAY_OPTIONS,
                              index=1, key="hr_display")


def date_slice(df, s, e):
    return df[(df['Date'] >= s) & (df['Date'] <= e)].copy()


current_raw = core.apply_financials(date_slice(base_df, start_date, end_date),
                                    labor_rate, machine_rate)

# ==========================================================================
# MASTER FILTER (global, cascading)
# ==========================================================================
st.sidebar.markdown("---")
st.sidebar.markdown("### Master Filter")
MASTER_FILTER_COLS = [
    "OEM Business Division", "Region", "Country", "Supplier", "Toolmaker", "Plant",
    "Tooling Type", "Product", "Project", "Part", "Tooling",
]
_casc = current_raw.copy()
master_selections = {}
for _col in MASTER_FILTER_COLS:
    if _col not in _casc.columns:
        continue
    _opts = sorted(_casc[_col].dropna().unique().tolist())
    _sel = st.sidebar.multiselect(_col, options=_opts, key=f"mf_{_col}")
    master_selections[_col] = _sel
    if _sel:
        _casc = _casc[_casc[_col].isin(_sel)]


def apply_master_filters(df):
    for _c, _v in master_selections.items():
        if _v:
            df = df[df[_c].isin(_v)]
    return df


current_df = apply_master_filters(current_raw)
# Full history for both trend graphs -- deliberately ignores the Time Range.
trend_all_df = apply_master_filters(core.apply_financials(base_df, labor_rate, machine_rate))

# High-Runner filter, applied to both frames so the entire feature set --
# tiles, pies, rankings, tables AND both trend graphs -- covers only the
# qualifying tools. Evaluated against the unfiltered base_df so a tool's
# high-runner status is a fact about the tool, not about the Time Range or
# the Master Filter selections currently narrowing the view.
if hr_display == "High-Runner Tools Only":
    _hr_tools = core.high_runner_tools(base_df, hr_min_avg, hr_start, hr_end)
    current_df = current_df[current_df['Tooling'].isin(_hr_tools)]
    trend_all_df = trend_all_df[trend_all_df['Tooling'].isin(_hr_tools)]

period_label = f"{pd.to_datetime(start_date).date()} to {pd.to_datetime(end_date).date()}"

# ==========================================================================
# HEADER
# ==========================================================================
st.markdown('<div class="dash-header">Cycle Time Efficiency</div>', unsafe_allow_html=True)
_fast_thr, _slow_thr = 100 + tolerance_pct, 100 - tolerance_pct
st.markdown(
    f'<div class="dash-sub">'
    f'Fast (Gain): &gt;{_fast_thr:g}% Cycle Time Efficiency &nbsp;|&nbsp; '
    f'Within (Neutral): {_slow_thr:g}%–{_fast_thr:g}% Cycle Time Efficiency &nbsp;|&nbsp; '
    f'Slow (Loss): &lt;{_slow_thr:g}% Cycle Time Efficiency &nbsp;|&nbsp; '
    f'Tolerance: ±{tolerance_pct:g}%</div>',
    unsafe_allow_html=True,
)

_active = {k: v for k, v in master_selections.items() if v}
# Finding 3: `v` is the operator's selected values for a master-filter
# dimension (Supplier, Tooling, Part, Tooling Type, ...) -- real entity names
# that can originate from an operator-supplied CSV -- so each one is escaped
# before landing in this unsafe_allow_html markdown block. `k` is always one
# of our own static MASTER_FILTER_COLS literals, not data, so it is left as-is.
_chip_html = "".join(
    f'<span style="background:#1e293b;border:1px solid #38bdf8;border-radius:6px;'
    f'padding:3px 12px;font-size:.85rem;color:#e2e8f0;white-space:nowrap;">'
    f'<b>{k}:</b> {", ".join(ui.esc(item) for item in v)}</span> ' for k, v in _active.items())
# Built outside the f-string below: Python 3.9 forbids backslashes (and here,
# nested quote escaping) inside f-string expressions.
_no_filters = '<span style="color:#475569;font-size:.85rem;">None applied</span>'
_filters_row = _chip_html if _chip_html else _no_filters
st.markdown(
    f'<div style="background:#1a1d26;border:1px solid #2d3748;border-radius:10px;'
    f'padding:12px 20px;margin-bottom:18px;">'
    f'<div style="display:flex;flex-wrap:wrap;gap:24px;margin-bottom:6px;">'
    f'<span style="color:#94a3b8;font-size:.88rem;"><b>Date Range:</b> {period_label}</span>'
    f'<span style="color:#94a3b8;font-size:.88rem;"><b>Financial Parameters:</b> '
    f'Labor ${labor_rate:.2f}/hr &nbsp;|&nbsp; Machine ${machine_rate:.2f}/hr</span></div>'
    f'<div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;">'
    f'<span style="color:#64748b;font-size:.88rem;margin-right:8px;">Filters:</span>'
    f'{_filters_row}'
    f'</div></div>',
    unsafe_allow_html=True,
)

# ==========================================================================
# ROOT TABS + BREADCRUMB
# ==========================================================================
with st.container(key="toptabs"):
    # Equal column weights don't matter here: cte_ui's CSS forces every
    # column in this row to shrink-to-fit its own button (flex:0 0 auto)
    # rather than grow to its weighted share, so column width is exactly the
    # button's own width and the row's `gap` is the only space between tabs
    # -- uniform by construction, unlike weighting columns by label length,
    # which produced visibly uneven gaps (see that CSS rule's comment).
    _cols = st.columns(len(nav.ROOTS), gap="large")
    for _col, (_label, _root) in zip(_cols, nav.ROOTS):
        with _col:
            if st.button(_label, key=f"root_{_root}",
                         type="primary" if nav.current_root() == _root else "secondary"):
                nav.set_root(_root)
                st.rerun()


def _crumb_click(index):
    nav.pop_to(index)
    st.rerun()


ui.render_breadcrumb(nav.crumb_labels(nav.get_stack()), _crumb_click)

# Land the reader at the top of a page they just navigated to. One-shot, so
# ordinary reruns (tolerance slider, table search) leave their scroll alone.
if nav.consume_scroll_request():
    ui.scroll_to_top(nav.nav_epoch())

# ==========================================================================
# DISPATCH
# ==========================================================================
if current_df.empty:
    st.warning("No data available for the selected time range / filters.")
    st.stop()

level, value = nav.current()
ctx = views.Ctx(
    scope=nav.scope_df(current_df, nav.get_stack()),
    trend=nav.scope_df(trend_all_df, nav.get_stack()),
    level=level,
    value=value,
    tolerance_pct=tolerance_pct,
    period_label=period_label,
    keyns=nav.keyns(),
)

if ctx.scope.empty:
    st.warning("No data at this level for the selected time range / filters.")
    if st.button("← Back to Global Overview"):
        nav.set_root("global")
        st.rerun()
    st.stop()

views.RENDERERS[level](ctx)

st.sidebar.markdown("---")
st.sidebar.markdown('<div style="color:#475569; font-size:.8rem; text-align:center;">v3.0.0</div>',
                    unsafe_allow_html=True)
