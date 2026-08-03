"""
cte_ui.py
=========
Presentation layer shared by every v3 view: theme CSS, colors, number
formats, table styling, and the small reusable blocks (summary tiles,
breadcrumb, section headings).

No business math lives here. Anything numeric comes from cte_core.
"""

import html

import pandas as pd
import streamlit as st

GREEN, YELLOW, RED, GREY = "#5cb85c", "#eab308", "#d9534f", "#94a3b8"
STATUS_COLORS = {"Within": GREEN, "Slow": YELLOW, "Fast": RED}


def esc(value):
    """Escape a value before it is interpolated into an
    st.markdown(..., unsafe_allow_html=True) string.

    Finding 3: several presentation helpers interpolate caller-supplied text
    (supplier / tool / part / tooling-type names, master-filter selections)
    into raw HTML. In production those names can come from an
    operator-supplied CSV, so anything that isn't OUR OWN static markup
    string must be escaped here rather than trusted. Safe (and a no-op in
    practice) on values that are already plain numbers or text with no HTML
    metacharacters.
    """
    return html.escape(str(value))


def inject_theme():
    """Enterprise dark theme. Carried over verbatim from the Executive app,
    plus v3's breadcrumb and summary-tile rules."""
    st.markdown(_THEME_CSS, unsafe_allow_html=True)


# _THEME_CSS is copied verbatim from the <style>...</style> block that lives
# inline in Cycle-Time-Efficiency-v3.py (currently lines 48-143), with the
# v3 breadcrumb / summary-tile / stat-line rules appended. This is a move,
# not a permanent duplication: Task 13 rewrites Cycle-Time-Efficiency-v3.py
# as a thin entry point that calls inject_theme(), at which point the
# original inline block is deleted from that file.
_THEME_CSS = """
<style>
.stApp { background-color:#0f1117; color:#fff;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }
#MainMenu {visibility:hidden;} footer {visibility:hidden;}
header {background-color:transparent !important;}
.block-container {padding-top:2rem !important; padding-bottom:2rem !important; max-width:1600px;}

.dash-header {font-size:1.85rem; font-weight:700; color:#fff; margin-bottom:.25rem; letter-spacing:.5px;}
.dash-sub {color:#94a3b8; font-size:.95rem; margin-bottom:1.5rem;}

.section-title {font-size:1.4rem; font-weight:600; color:#fff; margin-top:.5rem; margin-bottom:1rem;
  padding-bottom:.5rem; border-bottom:1px solid #2d3748;}

/* Session-state-driven tab bar (buttons, not st.tabs). Scoped to the
   st.container(key="toptabs"/"subtabs") wrappers via Streamlit's
   auto-generated st-key-<key> class, so this never affects any other
   button (View all, download, etc.) elsewhere in the app.

   Visual hierarchy: main tabs are a bold underline style (classic
   primary-navigation pattern, larger text). Sub-tabs are a grouped
   "segmented control" — one contained pill housing all three options
   with the active one shown as a filled chip inside it — a distinct
   shape/pattern (not just a smaller copy of the main tabs) that reads
   as secondary navigation nested underneath. */
.st-key-toptabs button {
  font-size:1.2rem !important; font-weight:700 !important; padding:.55rem .3rem !important;
  letter-spacing:.2px !important;
}
.st-key-toptabs button[kind="primary"] {
  background-color:transparent !important; border:none !important; color:#fff !important;
  border-bottom:4px solid #d9534f !important; border-radius:0 !important; box-shadow:none !important;
}
.st-key-toptabs button[kind="primary"]:hover {
  background-color:rgba(217,83,79,.08) !important; color:#fff !important;
}
.st-key-toptabs button[kind="secondary"] {
  background-color:transparent !important; border:none !important;
  border-bottom:4px solid transparent !important; color:#64748b !important; border-radius:0 !important;
}
.st-key-toptabs button[kind="secondary"]:hover {
  color:#cbd5e1 !important; background-color:rgba(255,255,255,.03) !important;
}
.st-key-toptabs {
  border-bottom:1px solid #2d3748; margin-bottom:1.75rem; padding-bottom:0;
}

.st-key-subtabs {
  background-color:#1a1d26 !important; border:1px solid #2d3748 !important;
  border-radius:10px !important; padding:4px !important; margin-top:.25rem; margin-bottom:1.5rem;
}
.st-key-subtabs button {
  font-size:.85rem !important; font-weight:600 !important; padding:.4rem 1rem !important;
  background-color:transparent !important; border:none !important;
  border-radius:7px !important; box-shadow:none !important;
}
.st-key-subtabs button[kind="primary"] {
  background-color:#2d3748 !important; color:#fff !important;
}
.st-key-subtabs button[kind="primary"]:hover {
  background-color:#3a4a63 !important;
}
.st-key-subtabs button[kind="secondary"] {
  color:#94a3b8 !important;
}
.st-key-subtabs button[kind="secondary"]:hover {
  color:#e2e8f0 !important; background-color:rgba(255,255,255,.04) !important;
}

/* KPI scorecard */
.kpi {background-color:#1a1d26; border-radius:18px; padding:32px 30px; border:1px solid #2d3748;
  box-shadow:0 8px 16px -4px rgba(0,0,0,.3); height:100%; margin-bottom:20px;}
.kpi-top {display:flex; justify-content:space-between; align-items:center; margin-bottom:22px;}
.kpi-name {font-size:1.4rem; font-weight:700; color:#fff; letter-spacing:.3px;}
.legend-note {color:#64748b; font-size:.82rem; margin-top:6px;}

/* Hero total number + Fast/Within/Slow tier grid inside the dimension card */
.kpi-hero {text-align:center; margin-bottom:26px; padding-bottom:24px; border-bottom:1px solid #2d3748;}
.kpi-hero-num {font-size:3.4rem; font-weight:800; line-height:1; color:#fff;}
.kpi-hero-label {font-size:1rem; color:#94a3b8; margin-top:8px; text-transform:uppercase; letter-spacing:.6px;}
.tier-grid {display:flex; gap:14px;}
.tier-card {flex:1; border-radius:14px; padding:18px 10px; text-align:center;}
.tier-label {font-size:.85rem; color:#94a3b8; margin-bottom:10px; font-weight:700;
  text-transform:uppercase; letter-spacing:.5px;}
.tier-num {font-size:2rem; font-weight:800; line-height:1;}
.tier-pct {font-size:.95rem; color:#94a3b8; margin-top:6px;}
.tier-trend {font-size:.78rem; margin-top:10px; font-weight:600; line-height:1.3;}

/* Bigger, more prominent "View all" buttons */
.stButton > button {font-size:1.05rem; font-weight:600; padding:.65rem 1rem; border-radius:10px;}

/* Entity "report card" badge (Detailed Analysis: <entity>) */
.entity-badge {background:#1a2e22; color:#4ade80; font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
  padding:3px 12px; border-radius:6px; font-size:.95rem; font-weight:600; letter-spacing:.3px;}

/* v3 breadcrumb */
.st-key-breadcrumb button {
  font-size:.9rem !important; font-weight:600 !important; padding:.25rem .6rem !important;
  background-color:transparent !important; border:none !important; box-shadow:none !important;
}
.st-key-breadcrumb button[kind="primary"] { color:#fff !important; }
.st-key-breadcrumb button[kind="secondary"] { color:#7dd3fc !important; }
.st-key-breadcrumb button[kind="secondary"]:hover { color:#bae6fd !important; text-decoration:underline; }

/* v3 six-tile summary strip */
.v3-tile {background:#1a1d26;border:1px solid #2d3748;border-radius:14px;
  padding:18px 20px;height:100%;}
.v3-tile-label {font-size:.8rem;color:#94a3b8;text-transform:uppercase;
  letter-spacing:.5px;font-weight:700;margin-bottom:8px;}
.v3-tile-num {font-size:1.9rem;font-weight:800;line-height:1.1;}
.v3-tile-sub {font-size:.82rem;color:#64748b;margin-top:4px;}

/* v3 stat line above Trend Graph 2 */
.v3-statline {background:#151822;border:1px solid #2d3748;border-radius:10px;
  padding:10px 16px;margin-bottom:10px;color:#e2e8f0;font-size:.95rem;}
.v3-footnote {color:#64748b;font-size:.78rem;margin-top:6px;line-height:1.5;}
</style>
"""

# ---- number formats (verbatim from the Executive app) ---------------------
RANK_FMT = {
    "Hours Gained": "{:.2f}", "Hours Lost": "{:.2f}", "Net Hours": "{:.2f}",
    "Shots Gained": "{:,.0f}", "Shots Lost": "{:,.0f}", "Net Shots": "{:,.0f}",
    "Financial Gained": "${:,.0f}", "Financial Lost": "${:,.0f}", "Net Financial": "${:,.0f}",
    "Overall Efficiency %": "{:.2f}%", "Total Toolings": "{:,.0f}", "Rank": "{:.0f}",
}
DETAIL_FMT = {
    "Hourly Rate": "${:,.0f}",
    "Total Shots": "{:,.0f}", "Parts Produced": "{:,.0f}", "ACT": "{:.2f}",
    "Actual Average CT (WACT)": "{:.2f}", "CT Difference": "{:.2f}",
    "Total Expected Hours": "{:.2f}", "Total Actual Hours": "{:.2f}",
    "Fast Shots (%)": "{:.2f}%", "Slow Shots (%)": "{:.2f}%", "Within Shots (%)": "{:.2f}%",
    "WACT (Fast)": "{:.2f}", "WACT (Slow)": "{:.2f}",
    "Expected Hours (Fast)": "{:.2f}", "Expected Hours (Slow)": "{:.2f}",
    "Actual Hours (Fast)": "{:.2f}", "Actual Hours (Slow)": "{:.2f}",
    "Hours Gained": "{:.2f}", "Hours Lost": "{:.2f}",
    "Shots Gained": "{:,.0f}", "Shots Lost": "{:,.0f}",
    "Financial Gain": "${:,.0f}", "Financial Loss": "${:,.0f}", "Net Financial": "${:,.0f}",
    "CT Efficiency of Fast Hours": "{:.2f}%", "CT Efficiency of Slow Hours": "{:.2f}%",
    "CT Weighted Average Efficiency": "{:.2f}%",
    "Total Toolings": "{:,.0f}",
}
TREND2_FMT = {
    "Total Shots": "{:,.0f}", "CT Efficiency %": "{:.2f}%",
    "Fast Shots (%)": "{:.2f}%", "Within Shots (%)": "{:.2f}%", "Slow Shots (%)": "{:.2f}%",
    "Saving Opportunity ($)": "${:,.0f}", "Loss ($)": "${:,.0f}",
}

# Core column names stay canonical; only the DISPLAY labels use the v3 wording.
V3_DISPLAY_RENAME = {
    "CT Weighted Average Efficiency": "Cycle Time Efficiency",
    "Financial Gain": "Saving Opportunity",
    "Financial Loss": "Loss",
    "Financial Gained": "Saving Opportunity",
    "Financial Lost": "Loss",
    "Actual Average CT (WACT)": "WACT",
    "Total Toolings": "Total Tools",
}


def v3_display(df):
    """Apply the v3 display labels to a table built from core column names."""
    return df.rename(columns={k: v for k, v in V3_DISPLAY_RENAME.items() if k in df.columns})


def _v3_fmt(fmt_map):
    """Same format map, keyed by the v3 display labels as well as the core ones."""
    out = dict(fmt_map)
    for core_name, label in V3_DISPLAY_RENAME.items():
        if core_name in fmt_map:
            out[label] = fmt_map[core_name]
    return out


NEG_COL_HELP = {
    "CT Difference": st.column_config.NumberColumn(
        help="ACT − Actual Average CT (seconds). Negative = running slower than approved."),
    "Net Hours": st.column_config.NumberColumn(
        help="Hours Gained − Hours Lost. Negative = more machine time lost to slow shots "
             "than gained from fast ones."),
    "Net Shots": st.column_config.NumberColumn(
        help="Shots Gained − Shots Lost. Negative = more shots ran slow than fast."),
    "Net Financial": st.column_config.NumberColumn(
        help="Saving Opportunity − Loss. Negative = net cost overrun for the period."),
}


def neg_help(df):
    return {k: v for k, v in NEG_COL_HELP.items() if k in df.columns}


def _status_css(v):
    return {"Fast": "background-color:#7f1d1d;color:#fff;",
            "Slow": "background-color:#854d0e;color:#fff;",
            "Within": "background-color:#14532d;color:#fff;"}.get(v, "")


def trend_change_css(v):
    if not isinstance(v, str) or v == '—':
        return 'color:#94a3b8;'
    if v.startswith('↑'):
        return 'color:#d9534f;'
    if v.startswith('↓'):
        return 'color:#5cb85c;'
    return 'color:#94a3b8;'


def style_table(df, fmt_map):
    """Format + conditional-colour a table. Accepts core or v3 display labels."""
    full = _v3_fmt(fmt_map)
    fmt = {k: v for k, v in full.items() if k in df.columns}
    sty = df.style.format(fmt, na_rep="N/A")
    if "Performance Status" in df.columns:
        sty = sty.map(_status_css, subset=["Performance Status"])
    return sty


def search_box(df, key):
    q = st.text_input("Search table", key=f"search_{key}",
                      placeholder="Type to filter rows (matches any text column)…")
    if q:
        mask = pd.Series(False, index=df.index)
        for c in df.select_dtypes(include="object").columns:
            mask |= df[c].astype(str).str.contains(q, case=False, na=False)
        df = df[mask]
    return df


def download_csv(df, label, fname, key):
    st.download_button(f"⬇ {label}", data=df.to_csv(index=False).encode("utf-8"),
                       file_name=fname, mime="text/csv", key=f"dl_{key}")


def bucket_label(bucket_ts, freq):
    if freq == 'M':
        return bucket_ts.strftime('%b %Y')
    return f"Q{(bucket_ts.month - 1) // 3 + 1} {bucket_ts.year}"


def section(title, size="1.4rem"):
    # `size` is always one of our own static CSS-length literals passed by
    # call sites in this codebase, not caller/CSV data -- only `title` (which
    # can be built from a dynamic dimension name) needs escaping.
    st.markdown(f'<div class="section-title" style="font-size:{size};">{esc(title)}</div>',
                unsafe_allow_html=True)


def entity_badge(prefix, label):
    # `label` is a real entity value (supplier / tool / part / tooling-type
    # name) that can originate from an operator-supplied CSV -- escape it.
    st.markdown(f"""<div style="display:flex;align-items:center;gap:12px;margin-bottom:1.25rem;">
  <span style="font-size:1.3rem;font-weight:700;color:#fff;">{esc(prefix)}</span>
  <span class="entity-badge">{esc(label)}</span>
</div>""", unsafe_allow_html=True)


def _tile(label, value, color, sub=""):
    sub_html = f'<div class="v3-tile-sub">{esc(sub)}</div>' if sub else ""
    return (f'<div class="v3-tile"><div class="v3-tile-label">{esc(label)}</div>'
            f'<div class="v3-tile-num" style="color:{color};">{esc(value)}</div>{sub_html}</div>')


def summary_tiles(summary, entity_noun="Tools"):
    """The six v3 summary tiles: total / fast / within / slow / saving / loss.

    `summary` is a cte_core.scope_summary() dict. Applies at every level, so
    the tile row is identical from Global down to a single supplier.
    """
    def _pct(p):
        return f"{p:.1f}%" if p is not None else "—"

    c = st.columns(6, gap="small")
    tiles = [
        ("Total " + entity_noun, f"{summary['total']:,}", "#ffffff", ""),
        (f"Fast {entity_noun} (Gain)", f"{summary['fast']:,}", RED, _pct(summary['pct_fast'])),
        (f"Within {entity_noun} (Neutral)", f"{summary['within']:,}", GREEN, _pct(summary['pct_within'])),
        (f"Slow {entity_noun} (Loss)", f"{summary['slow']:,}", YELLOW, _pct(summary['pct_slow'])),
        ("Saving Opportunity", f"${summary['saving_opportunity']:,.0f}", GREEN, "from fast shots"),
        ("Loss", f"${summary['loss']:,.0f}", YELLOW, "from slow shots"),
    ]
    for col, (label, value, color, sub) in zip(c, tiles):
        with col:
            st.markdown(_tile(label, value, color, sub), unsafe_allow_html=True)


def render_breadcrumb(frames, on_click):
    """Clickable breadcrumb for the nav stack.

    frames: list of (index, display_label) — the last one is the current page
    and is rendered inert. on_click(index) is called when an earlier crumb is
    clicked; the caller is responsible for popping the stack and rerunning.
    """
    if not frames:
        return
    with st.container(key="breadcrumb"):
        cols = st.columns([1] * len(frames) + [max(1, 8 - len(frames))])
        for col, (idx, label) in zip(cols, frames):
            with col:
                is_last = idx == frames[-1][0]
                if st.button(label if is_last else f"{label}  ›", key=f"crumb_{idx}_{label}",
                             type="primary" if is_last else "secondary"):
                    if not is_last:
                        on_click(idx)
