"""
cte_nav.py
==========
v3 navigation: the level registry and the session-state navigation stack that
generalizes the Executive dashboard's two-level drill-down to five.

A navigation stack is a list of (level_key, value) frames. The first frame is
always a ROOT (value None, no filter column); each later frame narrows the
scope by one dimension. The scope DataFrame for any page is produced by
applying every frame's filter column in order — which is why Tooling Type and
Part can be cross-cutting: their paths simply start from a different root and
never touch the geography columns.

The pure functions (scope_df, crumb_labels) take the stack explicitly so they
are testable without a Streamlit runtime.
"""

import hashlib

import streamlit as st

# label      : breadcrumb / heading wording for the level itself
# col        : the record column this level filters on (None = root, no filter)
# child      : the level a click drills into
# trend_dim  : the dimension passed to core.act_weighted_deviation_trend at
#              this level (the entity whose ACT-weighted deviations are
#              averaged). Chosen as the level's own child entity, so Global
#              through Country average across Suppliers, while Supplier / Type
#              / Part / Tool average across Toolings.
# entity_noun: what the six summary tiles are counting at this level
# exclusive  : (optional, default False) when True, this level's own filter
#              SUPERSEDES every ancestor frame's filter rather than adding to
#              it -- see scope_df(). Only 'tool' sets this: a tool belongs to
#              exactly one supplier, plant, region, country and tooling type,
#              so dropping those ancestor filters can never change a tool's
#              data, but Part is a cross-cutting dimension (Part C section
#              7.1) that a tool can share with sibling tools, and the product
#              owner ruled the tool report must always show whole-tool
#              figures regardless of which part (if any) was used to
#              navigate there.
LEVELS = {
    'global':     {'label': 'Global',       'col': None,           'child': 'region',
                   'trend_dim': 'Supplier',     'entity_noun': 'Tools'},
    'region':     {'label': 'Region',       'col': 'Region',       'child': 'country',
                   'trend_dim': 'Supplier',     'entity_noun': 'Tools'},
    'country':    {'label': 'Country',      'col': 'Country',      'child': 'supplier',
                   'trend_dim': 'Supplier',     'entity_noun': 'Tools'},
    'supplier':   {'label': 'Supplier',     'col': 'Supplier',     'child': 'tool',
                   'trend_dim': 'Tooling',      'entity_noun': 'Tools'},
    'type_all':   {'label': 'Tooling Type', 'col': None,           'child': 'type',
                   'trend_dim': 'Tooling Type', 'entity_noun': 'Tools'},
    'type':       {'label': 'Tooling Type', 'col': 'Tooling Type', 'child': 'tool',
                   'trend_dim': 'Tooling',      'entity_noun': 'Tools'},
    'part_all':   {'label': 'Part',         'col': None,           'child': 'part',
                   'trend_dim': 'Part',         'entity_noun': 'Parts'},
    'part':       {'label': 'Part',         'col': 'Part',         'child': 'part_tools',
                   'trend_dim': 'Tooling',      'entity_noun': 'Tools'},
    'part_tools': {'label': 'Tools',        'col': None,           'child': 'tool',
                   'trend_dim': 'Tooling',      'entity_noun': 'Tools'},
    'tool':       {'label': 'Tool',         'col': 'Tooling',      'child': None,
                   'trend_dim': 'Tooling',      'entity_noun': 'Tools', 'exclusive': True},
}

# Root tabs, in display order: (tab label, root level key)
ROOTS = [
    ("Global Overview", "global"),
    ("Tooling Type", "type_all"),
    ("Part", "part_all"),
]

_STACK_KEY = 'v3_nav_stack'
_EPOCH_KEY = 'v3_nav_epoch'


# ---- pure helpers (no Streamlit) -----------------------------------------
def scope_df(df, stack):
    """Filter `df` down to the scope described by `stack`.

    Frames whose level has no filter column (roots, part_tools) are skipped,
    as are frames naming a column the frame doesn't have.

    Exclusive levels are the one deviation from "apply every frame in order":
    if the CURRENT (last) frame's level is marked exclusive=True in LEVELS,
    every ancestor frame is ignored and only the last frame's own filter is
    applied. This keeps a tool report identical regardless of whether it was
    reached via Supplier or via the cross-cutting Part path -- see LEVELS'
    'exclusive' comment for the full reasoning.

    If the exclusive level's own filter can't actually be applied (its column
    is missing from the frame, or its value is None), there is nothing to
    supersede the ancestor filters with -- falling back to returning the
    whole, unfiltered frame would silently show MORE data than was asked for
    (the wrong direction of failure). Instead, fall through to the normal
    ancestor loop below, same as a non-exclusive level would.
    """
    if stack:
        last_level, last_value = stack[-1]
        if LEVELS[last_level].get('exclusive'):
            col = LEVELS[last_level]['col']
            if col is not None and last_value is not None and col in df.columns:
                return df[df[col] == last_value]
            # Fall through to the normal ancestor loop below instead of
            # returning the whole frame.

    out = df
    for level, value in stack:
        col = LEVELS[level]['col']
        if col is None or value is None or col not in out.columns:
            continue
        out = out[out[col] == value]
    return out


def crumb_labels(stack):
    """[(index, label)] for the breadcrumb: root uses its level label, every
    later frame uses its own value."""
    crumbs = []
    for i, (level, value) in enumerate(stack):
        crumbs.append((i, LEVELS[level]['label'] if value is None else str(value)))
    return crumbs


def child_of(level):
    return LEVELS[level]['child']


# ---- session-state bound --------------------------------------------------
def get_stack():
    if _STACK_KEY not in st.session_state:
        st.session_state[_STACK_KEY] = [("global", None)]
    return st.session_state[_STACK_KEY]


def nav_epoch():
    """A small integer bumped on every stack mutation (push / pop_to /
    set_root). Revisiting a previously-visited stack reproduces the same
    keyns() (by design -- see its docstring), but the epoch differs, so
    callers that need a fresh widget key per navigation event (rather than
    per distinct page) can fold this into their key instead of keyns()."""
    return st.session_state.get(_EPOCH_KEY, 0)


def _bump_epoch():
    st.session_state[_EPOCH_KEY] = st.session_state.get(_EPOCH_KEY, 0) + 1


def set_root(level):
    """Switch root tab: discard the stack and start fresh at `level`."""
    st.session_state[_STACK_KEY] = [(level, None)]
    _bump_epoch()


def push(level, value):
    get_stack().append((level, value))
    _bump_epoch()


def pop_to(index):
    """Truncate the stack to `index` inclusive. Never leaves the stack empty
    -- the root frame is always kept, even for out-of-range or negative
    indices."""
    stack = get_stack()
    frames = stack[:index + 1]
    if not frames:
        frames = stack[:1]
    st.session_state[_STACK_KEY] = frames
    _bump_epoch()


def current():
    """(level, value) of the page being viewed."""
    return get_stack()[-1]


def current_root():
    return get_stack()[0][0]


def keyns():
    """A stable widget-key namespace for the current page, so Streamlit
    widgets on different drill paths never collide.

    The readable "level-value_level-value..." prefix is kept for debugging,
    but uniqueness is guaranteed by a short hash of the full stack appended
    to it -- the prefix alone can alias (e.g. a value containing "-" or "_"
    can make a one-frame stack format identically to a two-frame stack), so
    the hash is what actually makes the collision-safety claim true. The
    hash uses hashlib (not the built-in `hash()`, which is salted per
    process and would make the namespace change across reruns/sessions) so
    the result is deterministic for a given stack."""
    stack = tuple(get_stack())
    prefix = "_".join(f"{lvl}-{val}" for lvl, val in stack).replace(" ", "")
    digest = hashlib.sha256(repr(stack).encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{digest}"
