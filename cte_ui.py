"""
cte_ui.py
=========
Presentation layer shared by every v3 view: theme CSS, colors, number
formats, table styling, and the small reusable blocks (summary tiles,
breadcrumb, section headings).

No business math lives here. Anything numeric comes from cte_core.
"""

import html
import string

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# Cycle Time Efficiency color tokens, per the MMS 2.0 design system's
# Cycle Time Efficiency application row. Fast is a warm red-toned "quality-
# risk flagged" token, not green: running faster than the Approved Cycle
# Time (ACT) can mean under-cured or otherwise out-of-spec parts, so the
# system deliberately does not treat "fast" as simply "good".
FAST_COLOR = "#B04A5E"            # Fast (Gain) -- quality-risk flagged
WITHIN_COLOR = "#5CA5FF"          # Within (Neutral) -- on-target / normal operation
SLOW_COLOR = "#F8A425"            # Slow (Loss) -- caution indicator
REFERENCE_LINE_COLOR = "#145741"  # Approved Cycle Time (ACT) baseline / target line
# Shot-volume bars (a plain count, not a Fast/Within/Slow state): the guide's
# own token, "Shot (line) -- Blue-900".
VOLUME_COLOR = "#002147"
# The system's Primary blue, used independently below for a few unrelated UI
# accents (light-mode links, chip borders, and the Within text-safe variant)
# that happened to reuse VOLUME_COLOR before it was pinned to Blue-900 --
# kept as their own literal now so changing the shot-bar color doesn't also
# darken those.
_PRIMARY = "#1663BB"
STATUS_COLORS = {"Within": WITHIN_COLOR, "Slow": SLOW_COLOR, "Fast": FAST_COLOR}

# ---- light/dark page chrome ------------------------------------------------
# FAST_COLOR / WITHIN_COLOR / SLOW_COLOR / REFERENCE_LINE_COLOR / VOLUME_COLOR
# above are NOT theme-dependent -- the design guide documents no light/dark
# variant for them, and every place they're used is a self-contained fill
# (a bar, a pie slice, a table badge) with its own already-verified text
# contrast, independent of the surrounding page background. What DOES need
# two versions is everything the page background touches: card fills, borders,
# body text, and chart axes/gridlines, all of which were designed against
# this app's original near-black canvas and would be washed out or invisible
# against a light one.
_DARK_THEME = {
    "page_bg": "#0f1117", "page_text": "#fff",
    "muted_text": "#94a3b8", "faint_text": "#64748b", "soft_text": "#e2e8f0",
    "card_bg": "#1a1d26", "card_bg_alt": "#151822",
    "border": "#2d3748", "border_strong": "#3a4a63",
    "chip_bg": "#1e293b", "chip_border": "#38bdf8",
    "link": "#7dd3fc", "link_hover": "#bae6fd",
    "badge_bg": "#1a2e22", "badge_text": "#4ade80",
    "note_text": "#475569",
    "chart_font": "#e2e8f0", "chart_tick": "#94a3b8", "chart_grid": "#334155",
    "chart_outline": "#0f1117",
    # Plain colored TEXT (no background of its own) for the Within/Slow
    # states -- the stat-line spans and the deviation-table trend arrows.
    # Unlike the fill tokens above, plain text sits directly on the page/card
    # background, so it DOES need a per-theme value. WITHIN_COLOR/SLOW_COLOR
    # themselves are light, saturated hues chosen to read on a near-black
    # canvas (that's also why their FILL usages -- pie slices, badges -- use
    # dark near-black text on top); as plain text they stay exactly those
    # colors here since dark-canvas contrast was already verified.
    "within_text": WITHIN_COLOR, "slow_text": SLOW_COLOR,
}
_LIGHT_THEME = {
    "page_bg": "#F7F8FA", "page_text": "#1F1F1F",  # #1F1F1F is the guide's own base "Black / Body text"
    "muted_text": "#5B6472", "faint_text": "#8A94A6", "soft_text": "#1F1F1F",
    "card_bg": "#FFFFFF", "card_bg_alt": "#EEF2F6",
    "border": "#E2E8F0", "border_strong": "#CBD5E1",
    "chip_bg": "#EFF6FF", "chip_border": _PRIMARY,
    "link": _PRIMARY, "link_hover": "#0D4A8F",
    "badge_bg": "#E6F4EA", "badge_text": "#1A7053",  # the guide's own "Fast Cycle/Gain" green -- a good fit for a plain positive/info badge here, just not for CTE's own Fast state (see FAST_COLOR)
    "note_text": "#94A3B8",
    "chart_font": "#1F1F1F", "chart_tick": "#5B6472", "chart_grid": "#D8DEE6",
    "chart_outline": "#FFFFFF",
    # WITHIN_COLOR (#5CA5FF) and SLOW_COLOR (#F8A425) both fail WCAG AA as
    # plain text on a light page (contrast ratios ~2.5:1 and ~2.0:1 against
    # white -- well under the 4.5:1 minimum). These are darkened, same-hue
    # stand-ins used ONLY for that plain-text case in light mode; every fill
    # usage (bars, pies, badges) keeps the exact brand hex in both themes.
    # within_text reuses the system's Primary blue (5.9:1 on white) -- a
    # sanctioned token rather than an invented blue. slow_text is a manually
    # darkened SLOW_COLOR (5.97:1 on white); the guide gives no darker step
    # for this hue, so this is an approximation, not a token.
    "within_text": _PRIMARY, "slow_text": "#885A14",
}


def get_theme():
    """The active light/dark palette dict, following Streamlit's own theme
    setting (its Settings menu, which itself can follow the OS) rather than
    a separate switch of this app's own.

    st.context.theme.type reflects Streamlit's underlying theme regardless
    of this app's own CSS overrides below, so detection isn't circular. It
    can be None briefly -- on a session's first script run, or mid-toggle
    right after the user changes it (see Streamlit issue #11920) -- in which
    case this defaults to dark, this app's original and most-tested design.
    """
    try:
        mode = st.context.theme.type
    except Exception:
        mode = None
    return _LIGHT_THEME if mode == "light" else _DARK_THEME


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


def scroll_to_top(nonce=0):
    """Put the viewport back at the top of the page.

    Drill tables sit at the bottom of a long page, so without this a click
    that opens a detail view leaves the reader stranded halfway down the new
    page, looking at whatever happens to occupy their old scroll offset.

    Streamlit 1.50 has no scroll API, and a <script> inside st.markdown is
    stripped, so this goes through a zero-height component iframe and reaches
    into the parent document. The scroll target is Streamlit's main section,
    which is the element that actually scrolls -- the window itself does not
    (document.body.scrollHeight is 0), so scrolling `window` is a no-op here.

    `nonce` must change per navigation (pass nav.nav_epoch()): Streamlit
    reuses a component iframe whose HTML is byte-identical, and a reused
    iframe does not re-execute its script, so two navigations in a row would
    scroll only the first time.
    """
    components.html(
        f"""<script>
        // nonce: {nonce}
        const doc = window.parent.document;
        const el = doc.querySelector('section[data-testid="stMain"]')
                || doc.querySelector('[data-testid="stAppViewContainer"]')
                || doc.scrollingElement;
        if (el) {{ el.scrollTop = 0; }}
        </script>""",
        height=0,
    )


def inject_theme():
    """Page-shell CSS, light or dark depending on Streamlit's own theme
    setting. Carried over from the Executive app's original dark design,
    plus v3's breadcrumb and summary-tile rules; the light variant is this
    app's own derivation (see get_theme())."""
    st.markdown(_theme_css(get_theme()), unsafe_allow_html=True)


def _theme_css(t):
    return _THEME_CSS_TEMPLATE.safe_substitute(t)


# _THEME_CSS_TEMPLATE started as a verbatim copy of the <style>...</style>
# block that used to live inline in Cycle-Time-Efficiency-v3.py, with the v3
# breadcrumb / summary-tile / stat-line rules appended, and every color
# literal since replaced with a ${token} filled in by _theme_css() from the
# active get_theme() dict. string.Template (${name}) rather than an f-string
# or str.format(): CSS is full of literal { and } (every rule body), which
# both of those would try to parse as substitution syntax; template syntax
# uses $ instead, which this stylesheet only ever contains inside one plain
# comment ("$27,3"), and safe_substitute() leaves that alone since a digit
# can't start a template identifier.
_THEME_CSS_TEMPLATE = string.Template("""
<style>
.stApp { background-color:${page_bg}; color:${page_text};
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }
#MainMenu {visibility:hidden;} footer {visibility:hidden;}
header {background-color:transparent !important;}
.block-container {padding-top:2rem !important; padding-bottom:2rem !important; max-width:1600px;}

.dash-header {font-size:1.85rem; font-weight:700; color:${page_text}; margin-bottom:.25rem; letter-spacing:.5px;}
.dash-sub {color:${muted_text}; font-size:.95rem; margin-bottom:1.5rem;}

.section-title {font-size:1.4rem; font-weight:600; color:${page_text}; margin-top:.5rem; margin-bottom:1rem;
  padding-bottom:.5rem; border-bottom:1px solid ${border};}

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
  background-color:transparent !important; border:none !important; color:${page_text} !important;
  border-bottom:4px solid #d9534f !important; border-radius:0 !important; box-shadow:none !important;
}
.st-key-toptabs button[kind="primary"]:hover {
  background-color:rgba(217,83,79,.08) !important; color:${page_text} !important;
}
.st-key-toptabs button[kind="secondary"] {
  background-color:transparent !important; border:none !important;
  border-bottom:4px solid transparent !important; color:${faint_text} !important; border-radius:0 !important;
}
.st-key-toptabs button[kind="secondary"]:hover {
  color:${soft_text} !important; background-color:rgba(255,255,255,.03) !important;
}
.st-key-toptabs {
  border-bottom:1px solid ${border}; margin-bottom:1.75rem; padding-bottom:0;
}
/* Streamlit's st.columns grows each column to fill its weighted share of the
   row, then left-aligns the button inside it -- so the visual gap between
   two tabs is "leftover column width" plus the fixed inter-column gap, and
   that leftover varies per label in a way plain character-count weighting
   can't predict (fixed button padding doesn't scale with label length the
   same way rendered text width does), producing uneven spacing. Forcing
   every column to shrink-to-fit its own button removes the leftover
   entirely, so the row's own `gap` becomes the ONLY space between tabs --
   which is uniform by construction. */
.st-key-toptabs [data-testid="stColumn"] {flex:0 0 auto !important; width:auto !important;}

.st-key-subtabs {
  background-color:${card_bg} !important; border:1px solid ${border} !important;
  border-radius:10px !important; padding:4px !important; margin-top:.25rem; margin-bottom:1.5rem;
}
.st-key-subtabs button {
  font-size:.85rem !important; font-weight:600 !important; padding:.4rem 1rem !important;
  background-color:transparent !important; border:none !important;
  border-radius:7px !important; box-shadow:none !important;
}
.st-key-subtabs button[kind="primary"] {
  background-color:${border} !important; color:${page_text} !important;
}
.st-key-subtabs button[kind="primary"]:hover {
  background-color:${border_strong} !important;
}
.st-key-subtabs button[kind="secondary"] {
  color:${muted_text} !important;
}
.st-key-subtabs button[kind="secondary"]:hover {
  color:${soft_text} !important; background-color:rgba(255,255,255,.04) !important;
}

/* KPI scorecard */
.kpi {background-color:${card_bg}; border-radius:18px; padding:32px 30px; border:1px solid ${border};
  box-shadow:0 8px 16px -4px rgba(0,0,0,.3); height:100%; margin-bottom:20px;}
.kpi-top {display:flex; justify-content:space-between; align-items:center; margin-bottom:22px;}
.kpi-name {font-size:1.4rem; font-weight:700; color:${page_text}; letter-spacing:.3px;}
.legend-note {color:${faint_text}; font-size:.82rem; margin-top:6px;}

/* Hero total number + Fast/Within/Slow tier grid inside the dimension card */
.kpi-hero {text-align:center; margin-bottom:26px; padding-bottom:24px; border-bottom:1px solid ${border};}
.kpi-hero-num {font-size:3.4rem; font-weight:800; line-height:1; color:${page_text};}
.kpi-hero-label {font-size:1rem; color:${muted_text}; margin-top:8px; text-transform:uppercase; letter-spacing:.6px;}
.tier-grid {display:flex; gap:14px;}
.tier-card {flex:1; border-radius:14px; padding:18px 10px; text-align:center;}
.tier-label {font-size:.85rem; color:${muted_text}; margin-bottom:10px; font-weight:700;
  text-transform:uppercase; letter-spacing:.5px;}
.tier-num {font-size:2rem; font-weight:800; line-height:1;}
.tier-pct {font-size:.95rem; color:${muted_text}; margin-top:6px;}
.tier-trend {font-size:.78rem; margin-top:10px; font-weight:600; line-height:1.3;}

/* Bigger, more prominent "View all" buttons */
.stButton > button {font-size:1.05rem; font-weight:600; padding:.65rem 1rem; border-radius:10px;}

/* Entity "report card" badge (Detailed Analysis: <entity>) */
.entity-badge {background:${badge_bg}; color:${badge_text}; font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
  padding:3px 12px; border-radius:6px; font-size:.95rem; font-weight:600; letter-spacing:.3px;}

/* v3 breadcrumb */
.st-key-breadcrumb button {
  font-size:.9rem !important; font-weight:600 !important; padding:.25rem .6rem !important;
  background-color:transparent !important; border:none !important; box-shadow:none !important;
  white-space:nowrap !important;
}
/* Same shrink-to-fit treatment as the root tab bar, for the same reason and
   with one extra: entity names vary wildly in length ("APAC" vs "New Era
   Molds"), and an equal-weight column narrower than its label wraps the
   crumb onto two lines, which then sits vertically misaligned against its
   single-line neighbours. Sizing each column to its own crumb makes the
   row's `gap` the only spacing and keeps every crumb on one line. */
.st-key-breadcrumb [data-testid="stColumn"] {flex:0 0 auto !important; width:auto !important;}
.st-key-breadcrumb [data-testid="stHorizontalBlock"] {align-items:center !important;}
.st-key-breadcrumb button[kind="primary"] { color:${page_text} !important; }
.st-key-breadcrumb button[kind="secondary"] { color:${link} !important; }
.st-key-breadcrumb button[kind="secondary"]:hover { color:${link_hover} !important; text-decoration:underline; }
/* Frames stepped back from: visible so the path forward isn't lost, but
   muted and inert -- only the next one is re-enterable in a single click. */
.v3-crumb-ahead {font-size:.9rem; font-weight:600; color:${note_text}; padding:.25rem .6rem;
  white-space:nowrap;}

/* v3 six-tile summary strip */
.v3-tile {background:${card_bg};border:1px solid ${border};border-radius:14px;
  padding:18px 20px;height:100%;box-sizing:border-box;
  display:flex;flex-direction:column;}
/* min-height on the label and sub rows reserves enough room for TWO lines
   of each at all times, regardless of which is actually rendered -- the six
   tiles' label lengths vary a lot ("Loss" vs "Within Tools (Neutral)") and
   so do their sub-lines ("32.1%" vs "from fast shots" vs Total's none at
   all), so at a narrow tile width some wrap and some don't. Reserving fixed
   space rather than trying to make Streamlit's row stretch every tile to
   match keeps this fix entirely inside this component's own CSS. */
.v3-tile-label {font-size:.85rem;color:${muted_text};line-height:1.3;min-height:2.3rem;
  letter-spacing:.1px;font-weight:700;margin-bottom:8px;}
/* nowrap + clamp: a dollar figure must never break mid-number ($27,3 / 93),
   so it stays on one line and scales down instead when the tile is narrow. */
.v3-tile-num {font-size:clamp(1.15rem, 2.1vw, 1.9rem);font-weight:800;
  line-height:1.1;white-space:nowrap;}
.v3-tile-sub {font-size:.82rem;color:${faint_text};line-height:1.3;min-height:2.2rem;margin-top:4px;}

/* Clickable summary cards. The card itself is an HTML div and Streamlit can
   attach no handler to that, so each card renders a real st.button which is
   pulled up over the card it follows and made fully transparent: the card
   keeps its exact appearance, and the whole card area is the click target.
   The negative margin is the card's own height, so the button covers it. */
[class*="st-key-v3cards"] [data-testid="stColumn"] {position:relative;}
/* The button is rendered after its card, so it is the column's LAST element
   container -- position THAT, not the inner .stButton: Streamlit collapses
   the container to 16x0, so an absolutely-positioned child inside it has
   nothing to stretch against and inset:0 does nothing. */
[class*="st-key-v3cards"] [data-testid="stElementContainer"]:last-child {
  position:absolute; inset:0; z-index:3; margin:0 !important; width:auto !important;
}
[class*="st-key-v3cards"] [data-testid="stElementContainer"]:last-child [data-testid="stButton"] {
  height:100% !important; width:100% !important; margin:0 !important;
}
/* Position the button itself against the (absolute) container rather than
   relying on height:100% cascading through Streamlit's wrapper divs -- the
   wrapper keeps its natural 28px button height, so a percentage height
   resolves to 28px and the overlay covers only the card's top strip. */
[class*="st-key-v3cards"] [data-testid="stElementContainer"]:last-child button {
  position:absolute !important; inset:0 !important;
  width:100% !important; height:auto !important; margin:0 !important; padding:0 !important;
  background:transparent !important; border:1px solid transparent !important;
  box-shadow:none !important; color:transparent !important; font-size:0 !important;
  border-radius:14px !important; min-height:0 !important;
}
[class*="st-key-v3cards"] [data-testid="stElementContainer"]:last-child button:hover {
  background:rgba(255,255,255,.04) !important; border:1px solid ${border_strong} !important;
}

/* Detailed Analysis: label-over-value KPI row, no card borders. */
.v3-kpi-label {font-size:.85rem;color:${muted_text};font-weight:600;margin-bottom:4px;line-height:1.3;
  min-height:2.3rem;}
.v3-kpi-value {font-size:2.1rem;font-weight:700;color:${page_text};line-height:1.1;white-space:nowrap;}

/* "N tools" caption under each small-multiple pie */
.v3-pie-count {text-align:center; color:${soft_text}; font-size:1rem; font-weight:700;
  margin-top:8px;}

/* v3 stat line above Trend Graph 2 */
.v3-statline {background:${card_bg_alt};border:1px solid ${border};border-radius:10px;
  padding:10px 16px;margin-bottom:10px;color:${soft_text};font-size:.95rem;}
.v3-footnote {color:${faint_text};font-size:.78rem;margin-top:6px;line-height:1.5;}
</style>
""")

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
    "CT Efficiency %": "Cycle Time Efficiency %",
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
    # Same fill colors as the charts (FAST_COLOR/WITHIN_COLOR/SLOW_COLOR), so
    # a table badge and a pie slice for the same state always agree. Text
    # color is picked per background for contrast: WITHIN_COLOR and
    # SLOW_COLOR are light enough that white text fails WCAG AA (2.5:1 and
    # 2.0:1), so both use the same dark near-black already proven legible on
    # these fills by the pie/donut slice labels; FAST_COLOR is dark enough
    # that white text is the better contrast (5.3:1 vs 3.6:1 for dark text).
    return {"Fast": f"background-color:{FAST_COLOR};color:#fff;",
            "Slow": f"background-color:{SLOW_COLOR};color:#0f1117;",
            "Within": f"background-color:{WITHIN_COLOR};color:#0f1117;"}.get(v, "")


def trend_change_css(v):
    # This column tracks ACT-Weighted Deviation (seconds off the Approved
    # Cycle Time), so an increase (↑) is drift AWAY from target -- the same
    # direction as the Slow/caution state -- and a decrease (↓) is movement
    # TOWARD target, the Within/on-target state. Reuses those two tokens
    # rather than inventing a separate generic good/bad pair.
    #
    # Plain text with no background of its own, so (unlike the fill colors
    # in _status_css above) it needs the theme's text-safe variant: on a
    # light page, WITHIN_COLOR/SLOW_COLOR's bright dark-canvas hues fail
    # contrast as plain text (see get_theme()'s within_text / slow_text).
    t = get_theme()
    if not isinstance(v, str) or v == '—':
        return f'color:{t["muted_text"]};'
    if v.startswith('↑'):
        return f'color:{t["slow_text"]};'
    if v.startswith('↓'):
        return f'color:{t["within_text"]};'
    return f'color:{t["muted_text"]};'


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


def hr(margin="1.75rem 0"):
    """A theme-aware divider -- every `<hr>` in the app goes through this
    rather than a literal border-color, so it never falls out of sync with
    the page's active light/dark theme the way ~20 hand-written copies of
    the same hex value inevitably would."""
    st.markdown(f"<hr style='border-color:{get_theme()['border']};margin:{margin};'>",
                unsafe_allow_html=True)


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
  <span style="font-size:1.3rem;font-weight:700;color:{get_theme()['page_text']};">{esc(prefix)}</span>
  <span class="entity-badge">{esc(label)}</span>
</div>""", unsafe_allow_html=True)


def _tile(label, value, color, sub=""):
    # The sub-line div is always rendered, even when `sub` is empty (the
    # Total tile has none) -- CSS reserves fixed vertical space for it via
    # min-height, so an absent sub-line doesn't make that one tile shorter
    # than its five siblings. Reserving space this way, rather than trying
    # to make Streamlit's row stretch the tile to match, is what actually
    # works: an earlier attempt at the latter forced every stElementContainer
    # in the whole app to flex-grow, which produced 500-700px tiles instead
    # of fixing anything -- Streamlit's internal DOM is not a stable target
    # for cross-tile height coordination, so this fix lives entirely in this
    # component's own CSS and doesn't touch Streamlit's containers at all.
    return (f'<div class="v3-tile"><div class="v3-tile-label">{esc(label)}</div>'
            f'<div class="v3-tile-num" style="color:{color};">{esc(value)}</div>'
            f'<div class="v3-tile-sub">{esc(sub)}</div></div>')


# Stable identifiers for the six cards, in render order -- what a click
# returns, so callers switch on these rather than on display text that the
# entity_noun changes ("Total Tools" vs "Total Parts").
TILE_KEYS = ['total', 'fast', 'within', 'slow', 'saving', 'loss']


def summary_tiles(summary, entity_noun="Tools", keyns=None):
    """The six v3 summary tiles: total / fast / within / slow / saving / loss.

    `summary` is a cte_core.scope_summary() dict. Applies at every level, so
    the tile row is identical from Global down to a single supplier.

    Pass `keyns` to make the cards clickable; returns the TILE_KEYS entry of
    whichever card was clicked this run, else None.
    """
    def _pct(p):
        return f"{p:.1f}%" if p is not None else "—"

    tiles = [
        # Total isn't a Fast/Within/Slow state, so it gets the page's own
        # primary text color rather than a semantic token -- hardcoded white
        # here would vanish on a light-mode card's white background.
        ("Total " + entity_noun, f"{summary['total']:,}", get_theme()["page_text"], ""),
        (f"Fast {entity_noun} (Gain)", f"{summary['fast']:,}", FAST_COLOR, _pct(summary['pct_fast'])),
        (f"Within {entity_noun} (Neutral)", f"{summary['within']:,}", WITHIN_COLOR, _pct(summary['pct_within'])),
        (f"Slow {entity_noun} (Loss)", f"{summary['slow']:,}", SLOW_COLOR, _pct(summary['pct_slow'])),
        ("Saving Opportunity", f"${summary['saving_opportunity']:,.0f}", FAST_COLOR, "from fast shots"),
        ("Loss", f"${summary['loss']:,.0f}", SLOW_COLOR, "from slow shots"),
    ]
    # `keyns` opts the row into click-to-drill: each card gets a transparent
    # button laid over it (see the .st-key-v3cards CSS), so the card keeps its
    # exact appearance and the whole card is the click target. Returns the key
    # of the clicked card, or None. Without a keyns the row is inert, exactly
    # as before.
    if keyns is None:
        c = st.columns(6, gap="small")
        for col, (label, value, color, sub) in zip(c, tiles):
            with col:
                st.markdown(_tile(label, value, color, sub), unsafe_allow_html=True)
        return None

    clicked = None
    with st.container(key=f"v3cards_{keyns}"):
        c = st.columns(6, gap="small")
        for col, (card_key, (label, value, color, sub)) in zip(c, zip(TILE_KEYS, tiles)):
            with col:
                st.markdown(_tile(label, value, color, sub), unsafe_allow_html=True)
                if st.button(label, key=f"card_{card_key}_{keyns}", help=f"View {label}"):
                    clicked = card_key
    return clicked


def render_breadcrumb(frames, on_click, forward=None, on_forward=None):
    """Clickable breadcrumb for the nav stack, with forward history.

    frames: list of (index, display_label) — the last one is the current page
    and is rendered inert. on_click(index) is called when an earlier crumb is
    clicked; the caller pops the stack and reruns.

    forward: labels of frames a back-step trimmed but which are still
    re-reachable, outermost first. They render greyed-out after the current
    page, and the first one is a button calling on_forward() — so stepping
    back never destroys where you were, and the path forward stays visible
    rather than silently vanishing.

    A lone frame with nothing parked forward is a bare root page (e.g. just
    "Country"), which only repeats the label the root tab bar already shows
    immediately above it -- render nothing rather than that redundant
    one-crumb line. The breadcrumb earns its place once there is an actual
    path to show.
    """
    forward = forward or []
    if len(frames) < 2 and not forward:
        return
    n = len(frames) + len(forward)
    with st.container(key="breadcrumb"):
        cols = st.columns([1] * n + [max(1, 9 - n)])
        for col, (idx, label) in zip(cols, frames):
            with col:
                is_last = idx == frames[-1][0]
                if st.button(label if is_last else f"{label}  ›", key=f"crumb_{idx}_{label}",
                             type="primary" if is_last else "secondary"):
                    if not is_last:
                        on_click(idx)
        for offset, label in enumerate(forward):
            with cols[len(frames) + offset]:
                # Only the immediately-next frame is re-enterable in one
                # click; the rest are shown for context so the reader can see
                # the whole path they stepped back along.
                if offset == 0 and on_forward is not None:
                    if st.button(f"›  {label}", key=f"fwd_{offset}_{label}",
                                 type="secondary", help="Go forward"):
                        on_forward()
                else:
                    st.markdown(
                        f'<div class="v3-crumb-ahead">›&nbsp;&nbsp;{esc(label)}</div>',
                        unsafe_allow_html=True)
