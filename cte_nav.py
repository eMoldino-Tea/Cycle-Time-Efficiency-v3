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
                   'trend_dim': 'Tooling',      'entity_noun': 'Tools'},
}

# Root tabs, in display order: (tab label, root level key)
ROOTS = [
    ("Global Overview", "global"),
    ("Tooling Type", "type_all"),
    ("Part", "part_all"),
]

_STACK_KEY = 'v3_nav_stack'


# ---- pure helpers (no Streamlit) -----------------------------------------
def scope_df(df, stack):
    """Filter `df` down to the scope described by `stack`.

    Frames whose level has no filter column (roots, part_tools) are skipped,
    as are frames naming a column the frame doesn't have.
    """
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


def set_root(level):
    """Switch root tab: discard the stack and start fresh at `level`."""
    st.session_state[_STACK_KEY] = [(level, None)]


def push(level, value):
    get_stack().append((level, value))


def pop_to(index):
    st.session_state[_STACK_KEY] = get_stack()[:index + 1]


def current():
    """(level, value) of the page being viewed."""
    return get_stack()[-1]


def current_root():
    return get_stack()[0][0]


def keyns():
    """A stable widget-key namespace for the current page, so Streamlit
    widgets on different drill paths never collide."""
    return "_".join(f"{lvl}-{val}" for lvl, val in get_stack()).replace(" ", "")
