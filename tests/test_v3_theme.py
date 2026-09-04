"""Tests for the app's light/dark theming.

get_theme() follows Streamlit's own theme setting (st.context.theme.type)
rather than a switch of this app's own, so these tests fake that attribute
directly on cte_ui.st.context instead of driving a real AppTest session --
AppTest has no supported way to set the simulated browser's theme.
"""
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import cte_ui as ui  # noqa: E402


class _FakeTheme:
    def __init__(self, type_):
        self.type = type_


class _FakeContext:
    def __init__(self, type_):
        self.theme = _FakeTheme(type_)


class _ContextWithNoTheme:
    """Simulates st.context existing but .theme raising -- the real
    ContextProxy can do this when there's no active script run context."""
    @property
    def theme(self):
        raise RuntimeError("no script run context")


@pytest.fixture
def fake_theme(monkeypatch):
    def _set(type_):
        monkeypatch.setattr(ui.st, "context", _FakeContext(type_))
    return _set


@pytest.fixture
def session_state(monkeypatch):
    """A plain dict standing in for st.session_state -- get_theme() only
    ever calls .get() on it, which a dict supports directly."""
    state = {}
    monkeypatch.setattr(ui.st, "session_state", state)
    return state


# ---- get_theme() dispatch ---------------------------------------------

def test_get_theme_returns_light_dict_when_streamlit_reports_light(fake_theme):
    fake_theme("light")
    assert ui.get_theme() is ui._LIGHT_THEME


def test_get_theme_returns_dark_dict_when_streamlit_reports_dark(fake_theme):
    fake_theme("dark")
    assert ui.get_theme() is ui._DARK_THEME


def test_get_theme_defaults_to_dark_when_type_is_none(fake_theme):
    """None is Streamlit's documented transient state -- first script run in
    a session, or mid-toggle right after the user changes it."""
    fake_theme(None)
    assert ui.get_theme() is ui._DARK_THEME


def test_get_theme_defaults_to_dark_when_context_is_unreadable(monkeypatch):
    """Any failure reading st.context.theme (e.g. no active script run
    context) must fail safe to dark, this app's original, fully-verified
    design -- not raise and break every page."""
    monkeypatch.setattr(ui.st, "context", _ContextWithNoTheme())
    assert ui.get_theme() is ui._DARK_THEME


def test_get_theme_ignores_unrecognised_type_strings(fake_theme):
    """Only the literal 'light' switches modes; anything else (a future
    Streamlit theme type, a typo) falls back to dark rather than crashing."""
    fake_theme("solarized")
    assert ui.get_theme() is ui._DARK_THEME


# ---- theme dict completeness -------------------------------------------

# Every key _theme_css's template actually substitutes. Keeping this list
# explicit (rather than deriving it from the template) means a theme dict
# missing one of these keys fails LOUDLY here rather than silently leaving
# a literal "${page_bg}" string in rendered HTML.
REQUIRED_CSS_KEYS = {
    "page_bg", "page_text", "muted_text", "faint_text", "soft_text",
    "card_bg", "card_bg_alt", "border", "border_strong",
    "chip_bg", "chip_border", "link", "link_hover",
    "badge_bg", "badge_text", "note_text",
}


@pytest.mark.parametrize("theme", [ui._DARK_THEME, ui._LIGHT_THEME], ids=["dark", "light"])
def test_theme_dict_has_every_key_the_css_template_needs(theme):
    assert REQUIRED_CSS_KEYS <= set(theme)


@pytest.mark.parametrize("theme", [ui._DARK_THEME, ui._LIGHT_THEME], ids=["dark", "light"])
def test_theme_css_leaves_no_placeholder_unfilled(theme):
    css = ui._theme_css(theme)
    assert not re.search(r"\$\{[a-zA-Z_]+\}", css), \
        "a ${token} survived substitution -- theme dict is missing a key the template needs"
    assert "<style>" in css and "</style>" in css


def test_theme_css_differs_between_light_and_dark():
    """A sanity check against the two dicts silently converging to the
    same rendered stylesheet, which would defeat the whole feature."""
    assert ui._theme_css(ui._DARK_THEME) != ui._theme_css(ui._LIGHT_THEME)


# ---- design decisions worth pinning -------------------------------------

def test_semantic_fill_tokens_are_identical_across_themes():
    """FAST/WITHIN/SLOW/REFERENCE/VOLUME are fills (bars, pies, badges) with
    their own self-contained contrast -- the design guide documents no
    light/dark variant for them, so they must NOT vary with get_theme()."""
    # These live as plain module-level constants, not theme-dict entries --
    # get_theme() never touches them, so they're theme-independent by
    # construction. Pinned here so a future refactor that folds them into
    # the theme dicts (making them vary by accident) fails loudly.
    assert ui.FAST_COLOR == "#B04A5E"
    assert ui.WITHIN_COLOR == "#5CA5FF"
    assert ui.SLOW_COLOR == "#F8A425"


def test_status_badge_fills_are_identical_across_themes(fake_theme):
    """_status_css colors a table badge's own background -- unlike plain
    text, it carries its own contrast regardless of the page theme."""
    fake_theme("dark")
    dark = {v: ui._status_css(v) for v in ("Fast", "Within", "Slow")}
    fake_theme("light")
    light = {v: ui._status_css(v) for v in ("Fast", "Within", "Slow")}
    assert dark == light


def test_trend_arrow_colors_differ_between_themes(fake_theme):
    """Unlike badges, trend_change_css colors plain text with no background
    of its own, so (per get_theme()'s within_text/slow_text) it DOES need
    to change between themes -- WITHIN_COLOR/SLOW_COLOR fail contrast as
    plain text on a light page."""
    fake_theme("dark")
    dark_up = ui.trend_change_css("↑ 0.03s")
    dark_down = ui.trend_change_css("↓ 0.03s")
    fake_theme("light")
    light_up = ui.trend_change_css("↑ 0.03s")
    light_down = ui.trend_change_css("↓ 0.03s")
    assert dark_up != light_up
    assert dark_down != light_down
    # And each still names the color it claims to.
    assert ui.SLOW_COLOR in dark_up
    assert ui.WITHIN_COLOR in dark_down
    assert ui._LIGHT_THEME["slow_text"] in light_up
    assert ui._LIGHT_THEME["within_text"] in light_down


def test_trend_arrow_dash_and_other_values_use_muted_text(fake_theme):
    fake_theme("dark")
    assert ui._DARK_THEME["muted_text"] in ui.trend_change_css("—")
    assert ui._DARK_THEME["muted_text"] in ui.trend_change_css(None)


def test_summary_tile_total_uses_page_text_not_hardcoded_white():
    """Regression guard: the Total tile's number color used to be a bare
    "#ffffff" literal, which is invisible on a light-mode card's white
    background. summary_tiles() now passes get_theme()["page_text"] as
    that tile's color instead -- checked here directly against the _tile()
    helper that actually places it in the HTML, since summary_tiles() itself
    only has a side effect (st.markdown) and no return value to inspect."""
    light_html = ui._tile("Total Tools", "78", ui._LIGHT_THEME["page_text"])
    assert "#ffffff" not in light_html.lower()
    assert ui._LIGHT_THEME["page_text"] in light_html

    dark_html = ui._tile("Total Tools", "78", ui._DARK_THEME["page_text"])
    assert ui._DARK_THEME["page_text"] in dark_html


def test_hr_helper_does_not_raise_in_either_theme(fake_theme):
    """ui.hr() replaced ~20 hand-written <hr> literals; it has no return
    value to inspect (st.markdown is a side effect), so this just confirms
    the one surviving call path runs clean in both themes rather than
    hitting a missing theme key."""
    fake_theme("dark")
    ui.hr()
    fake_theme("light")
    ui.hr("1.5rem 0")


# ---- sidebar toggle overrides Streamlit's own detected theme -----------

def test_explicit_light_override_wins_over_a_dark_browser(fake_theme, session_state):
    """The sidebar toggle exists specifically to let a reader pick a theme
    Streamlit itself isn't reporting (e.g. its own Settings menu is hidden
    -- see inject_theme's #MainMenu rule) -- so an explicit choice must beat
    whatever st.context.theme.type says, not just supplement it."""
    fake_theme("dark")
    session_state[ui._THEME_OVERRIDE_KEY] = "light"
    assert ui.get_theme() is ui._LIGHT_THEME


def test_explicit_dark_override_wins_over_a_light_browser(fake_theme, session_state):
    fake_theme("light")
    session_state[ui._THEME_OVERRIDE_KEY] = "dark"
    assert ui.get_theme() is ui._DARK_THEME


def test_auto_override_falls_back_to_detected_theme(fake_theme, session_state):
    """"Auto" is the toggle's way of clearing its own override, not a third
    palette -- it must defer back to st.context.theme.type exactly as if no
    override had ever been set."""
    fake_theme("light")
    session_state[ui._THEME_OVERRIDE_KEY] = "auto"
    assert ui.get_theme() is ui._LIGHT_THEME


def test_no_override_present_falls_back_to_detected_theme(fake_theme, session_state):
    """The common case: a reader who has never touched the toggle."""
    fake_theme("light")
    assert ui._THEME_OVERRIDE_KEY not in session_state
    assert ui.get_theme() is ui._LIGHT_THEME


def test_garbage_override_value_is_ignored(fake_theme, session_state):
    """Only the literal 'light'/'dark' strings the toggle itself writes
    count as an override; anything else (a stale value from a future
    version of this app, session_state tampering) falls through to
    detection rather than crashing or silently defaulting to one theme."""
    fake_theme("light")
    session_state[ui._THEME_OVERRIDE_KEY] = "solarized"
    assert ui.get_theme() is ui._LIGHT_THEME
