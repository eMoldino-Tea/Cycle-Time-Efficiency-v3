"""Tests for the app's (dark-only) theme system.

The app renders exactly one palette -- get_theme() always returns
_DARK_THEME, and .streamlit/config.toml locks Streamlit's own native
rendering (the canvas-rendered dataframe grid, sliders, scrollbars --
everything this app's own CSS can't reach) to dark too, so there is no
reader-facing switch and no browser/OS setting to detect.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import cte_ui as ui  # noqa: E402


def test_get_theme_always_returns_the_dark_theme():
    """No override, no detection -- there is exactly one palette."""
    assert ui.get_theme() is ui._DARK_THEME


def test_light_theme_and_toggle_do_not_exist():
    """Regression guard: neither the light palette nor the sidebar toggle
    remain as removable state a future change could accidentally re-enable
    halfway (e.g. restoring the toggle without restoring the palette it
    would try to switch to)."""
    assert not hasattr(ui, "_LIGHT_THEME")
    assert not hasattr(ui, "render_theme_toggle")
    assert not hasattr(ui, "_THEME_RADIO_KEY")


# ---- theme dict completeness -------------------------------------------

# Every key _theme_css's template actually substitutes. Keeping this list
# explicit (rather than deriving it from the template) means the theme dict
# missing one of these keys fails LOUDLY here rather than silently leaving
# a literal "${page_bg}" string in rendered HTML.
REQUIRED_CSS_KEYS = {
    "page_bg", "page_text", "muted_text", "faint_text", "soft_text",
    "card_bg", "card_bg_alt", "border", "border_strong",
    "chip_bg", "chip_border", "link", "link_hover",
    "badge_bg", "badge_text", "note_text",
}


def test_theme_dict_has_every_key_the_css_template_needs():
    assert REQUIRED_CSS_KEYS <= set(ui._DARK_THEME)


def test_theme_css_leaves_no_placeholder_unfilled():
    css = ui._theme_css(ui._DARK_THEME)
    assert not re.search(r"\$\{[a-zA-Z_]+\}", css), \
        "a ${token} survived substitution -- theme dict is missing a key the template needs"
    assert "<style>" in css and "</style>" in css


# ---- design decisions worth pinning -------------------------------------

def test_semantic_fill_tokens_are_pinned():
    """FAST/WITHIN/SLOW are fills (bars, pies, badges) with their own
    self-contained contrast, independent of the page theme -- pinned here
    so a future change touching them fails loudly rather than silently."""
    assert ui.FAST_COLOR == "#FB6A87"  # Red-500, a deliberate override of the guide's Red-700
    assert ui.WITHIN_COLOR == "#5CA5FF"
    assert ui.SLOW_COLOR == "#F8A425"


def test_status_badge_fills_use_the_semantic_colors():
    """_status_css colors a table badge's own background -- unlike plain
    text, it carries its own contrast regardless of the page theme."""
    badges = {v: ui._status_css(v) for v in ("Fast", "Within", "Slow")}
    assert ui.FAST_COLOR in badges["Fast"]
    assert ui.WITHIN_COLOR in badges["Within"]
    assert ui.SLOW_COLOR in badges["Slow"]


def test_trend_arrow_colors():
    """trend_change_css colors plain text with no background of its own --
    it reads get_theme()'s within_text/slow_text, which equal WITHIN_COLOR/
    SLOW_COLOR themselves in the one dark theme."""
    up = ui.trend_change_css("↑ 0.03s")
    down = ui.trend_change_css("↓ 0.03s")
    assert ui.SLOW_COLOR in up
    assert ui.WITHIN_COLOR in down


def test_trend_arrow_dash_and_other_values_use_muted_text():
    assert ui._DARK_THEME["muted_text"] in ui.trend_change_css("—")
    assert ui._DARK_THEME["muted_text"] in ui.trend_change_css(None)


def test_summary_tile_total_uses_page_text_not_hardcoded_white():
    """Regression guard: the Total tile's number color used to be a bare
    "#ffffff" literal. summary_tiles() passes get_theme()["page_text"] as
    that tile's color instead -- checked here directly against the _tile()
    helper that actually places it in the HTML, since summary_tiles() itself
    only has a side effect (st.markdown) and no return value to inspect."""
    html = ui._tile("Total Tools", "78", ui._DARK_THEME["page_text"])
    assert ui._DARK_THEME["page_text"] in html


def test_hr_helper_does_not_raise():
    """ui.hr() replaced ~20 hand-written <hr> literals; it has no return
    value to inspect (st.markdown is a side effect), so this just confirms
    the one surviving call path runs clean."""
    ui.hr()
    ui.hr("1.5rem 0")
