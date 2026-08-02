# Cycle Time Efficiency v3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Executive dashboard's flat 2-tab structure with a 5-level hierarchical drill-down (Global → Region → Country → Supplier → Tool) plus parallel Tooling Type and Part views, reusing every existing calculation in `cte_core.py` unchanged.

**Architecture:** One flat Tool-record table; every view is that same table filtered/grouped differently. A session-state **navigation stack** (`cte_nav.py`) generalizes Executive's 2-level drill-down to N levels — each stack frame is `(level, value)`, and the scope DataFrame is produced by applying each frame's filter column in order. Business math stays in `cte_core.py` (extended, never rewritten); rendering splits into `cte_ui.py` (theme/tiles/tables), `cte_charts.py` (both trend graphs, pies, ranking bars), and `cte_views.py` (one renderer per level). The entry-point script becomes a thin shell: settings → data → filters → dispatch.

**Tech Stack:** Python 3, Streamlit 1.50, pandas 2.3, numpy, Plotly 6.8, pytest (new).

## Global Constraints

- **The math must not change.** `calc_weighted_eff`, `apply_tolerance`, `apply_financials`, `compute_comprehensive_row`, `generate_ranking_table_data`, `entity_efficiency`, `fast_within_slow_summary`, `act_weighted_deviation_trend`, `performance_status_from_eff`, `format_hm` are reused **verbatim**. New functions may *call* them; no formula is ever re-derived in the UI layer.
- **Aggregation rule:** never average per-tool efficiency scores. Pool raw bucket hours/shots across the group first, then apply `calc_weighted_eff` once. Every new aggregation in this plan obeys this.
- Exactly three tiers: **Fast / Within / Slow**. No "At Risk" concept anywhere.
- Colors are the existing convention, unchanged: `GREEN="#5cb85c"` (Within), `YELLOW="#eab308"` (Slow), `RED="#d9534f"` (Fast), `GREY="#94a3b8"`.
- Tolerance default **5.0%** (`core.DEFAULT_TOLERANCE_PCT`), slider range 1.0–10.0 step 0.5.
- Labor rate default **$40/hr**, machine rate default **$180/hr**, `BASELINE_RATE = 220.0`.
- Time Range presets, exactly these five: `Last 7 Days`, `Last 30 Days`, `Last Quarter`, `Last 12 Months`, `Custom Range`. **No "Last 90 Days".** "Last Quarter" = the previous *complete* calendar quarter.
- Master Filter columns, in this order: `OEM Business Division, Region, Country, Supplier, Toolmaker, Plant, Tooling Type, Product, Part, Tooling`.
- Region values: `APAC, Europe, North America, LATAM` (never "South America").
- **Both trend graphs use the full data history** at every level, ignoring the sidebar Time Range (matches Executive's existing `trend_df` behaviour; Graph 2's "{M} active months" stat requires it).
- `CT Compliance` on Graph 2 = `Faster% + Within%`. This is deliberately a *different* metric from `calc_weighted_eff`. Every place it appears must carry the footnote defined in Task 9 so the two are never confused.
- Region and Country are **explicit DataFrame columns**, never parsed from the Plant string at the point of use.
- **Runtime is Python 3.9.6.** No backslashes inside f-string expressions, no PEP 604 (`str | None`) unions, no PEP 585 builtin generics (`dict[str, int]`) in annotations. Build any escaped HTML fragment in a plain variable *before* interpolating it.

---

## File Structure

| File | Responsibility |
|---|---|
| `cte_core.py` (modify) | ALL business math. Gains: `PLANT_META`, `ensure_geo_columns`, multi-part demo data, `resolve_time_range`, `ct_split_shot_trend`, `ct_split_summary`, `scope_summary`, `ranking_by_financial`, `entity_detail_table`, v3 column constants. |
| `cte_nav.py` (create) | Level registry (`LEVELS`), nav-stack session state, `scope_df()`, breadcrumb model. No rendering. |
| `cte_ui.py` (create) | Theme CSS, colors, number formats, `style_table`, `search_box`, `download_csv`, `neg_help`, `_bucket_label`, summary tiles, breadcrumb rendering, display-name renaming. |
| `cte_charts.py` (create) | `render_trend_block` (Graph 1 + Graph 2 + both companion tables), `small_multiple_pies`, `single_pie`, `ranking_bars`. |
| `cte_views.py` (create) | One renderer per level: scope overview (global/region/country), supplier, tool detail, tooling-type all/one, part all/one, part-tools. |
| `Cycle-Time-Efficiency-v3.py` (rewrite) | Entry point: page config, sidebar settings, data load + tolerance + financials + master filter, root tabs, dispatch to `cte_views`. |
| `generate_sample_data.py` (modify) | Country column + multi-part tools, matching the app schema. |
| `tests/test_cte_core.py` (create) | pytest coverage of all core math, incl. a golden regression lock. |
| `requirements-dev.txt` (create) | `pytest>=8.0`. |

---

### Task 1: Test harness + math baseline lock

Nothing in this plan may change an existing number. This task installs pytest and pins the current demo-data math so every later task proves it stayed identical.

**Files:**
- Create: `requirements-dev.txt`
- Create: `tests/test_cte_core.py`

**Interfaces:**
- Produces: `raw_load()` test helper (bypasses `@st.cache_data`), used by every later test.

- [ ] **Step 1: Create the dev requirements file**

`requirements-dev.txt`:
```
pytest>=8.0
```

Install it:

```bash
python3 -m pip install -r requirements-dev.txt
```

- [ ] **Step 2: Write the baseline lock test**

`tests/test_cte_core.py`:
```python
"""Regression + unit tests for cte_core.

The BASELINE_* constants below were measured from the shipped demo data
generator BEFORE any v3 change. They exist so that adding Country and
multi-part tools can be proven not to have moved a single number.
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cte_core as core


def raw_load(**kwargs):
    """Call load_base_data without Streamlit's cache wrapper."""
    fn = getattr(core.load_base_data, "__wrapped__", core.load_base_data)
    return fn(**kwargs)


BASELINE_ROWS = 8121
BASELINE_SHOTS = 21185467
BASELINE_USED_HOURS = 22439.685969
BASELINE_EXPECTED_HOURS = 21206.694132
BASELINE_WEIGHTED_EFF = 94.4717757403
BASELINE_TOOLS = 78
BASELINE_SUPPLIERS = 14


@pytest.fixture(scope="module")
def demo():
    return raw_load(version=11)


def test_demo_data_shape_is_unchanged(demo):
    assert len(demo) == BASELINE_ROWS
    assert demo["Tooling"].nunique() == BASELINE_TOOLS
    assert demo["Supplier"].nunique() == BASELINE_SUPPLIERS


def test_demo_data_math_is_unchanged(demo):
    assert int(demo["Total_Shots"].sum()) == BASELINE_SHOTS
    assert demo["Used_Hours"].sum() == pytest.approx(BASELINE_USED_HOURS, abs=1e-6)
    assert demo["Expected_Hours"].sum() == pytest.approx(BASELINE_EXPECTED_HOURS, abs=1e-6)
    assert core.calc_weighted_eff(demo) == pytest.approx(BASELINE_WEIGHTED_EFF, abs=1e-9)


def test_regions_are_the_four_canonical_values(demo):
    assert set(demo["Region"].unique()) == {"APAC", "Europe", "North America", "LATAM"}
```

- [ ] **Step 3: Run the tests — they must pass immediately**

```bash
python3 -m pytest tests/test_cte_core.py -v
```
Expected: 3 passed. (This test locks *current* behaviour, so it is green from the start. If it fails, stop — the environment differs from the one the plan was written against.)

- [ ] **Step 4: Commit**

```bash
git add requirements-dev.txt tests/test_cte_core.py
git commit -m "test: lock demo-data math baseline before v3 changes"
```

---

### Task 2: Explicit Country + Region geo columns

**Files:**
- Modify: `cte_core.py` (replace the `plant_to_region` block at lines 268–278; add `PLANT_META` + `ensure_geo_columns` near the top)
- Modify: `generate_sample_data.py:55-59,138`
- Test: `tests/test_cte_core.py`

**Interfaces:**
- Produces: `core.PLANT_META: dict[str, tuple[str, str]]` mapping Plant → (Country, Region); `core.ensure_geo_columns(df) -> pd.DataFrame` adding `Country` and `Region` when absent.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cte_core.py`:
```python
def test_ensure_geo_columns_adds_country_and_region():
    df = pd.DataFrame({"Plant": ["Plant 5 (CN)", "Plant 3 (DE)", "Plant 7 (BR)"]})
    out = core.ensure_geo_columns(df)
    assert out["Country"].tolist() == ["China", "Germany", "Brazil"]
    assert out["Region"].tolist() == ["APAC", "Europe", "LATAM"]


def test_ensure_geo_columns_is_idempotent_and_non_destructive():
    df = pd.DataFrame({"Plant": ["Plant 5 (CN)"], "Country": ["Custom"], "Region": ["Custom"]})
    out = core.ensure_geo_columns(df)
    assert out["Country"].tolist() == ["Custom"]
    assert out["Region"].tolist() == ["Custom"]


def test_unknown_plant_falls_back_without_raising():
    out = core.ensure_geo_columns(pd.DataFrame({"Plant": ["Plant 99 (ZZ)"]}))
    assert out["Country"].tolist() == ["Unknown"]
    assert out["Region"].tolist() == ["Other"]


def test_demo_data_has_country_column(demo):
    assert "Country" in demo.columns
    assert set(demo["Country"].unique()) == {
        "Mexico", "United States", "Germany", "Poland", "China", "Vietnam", "Brazil",
    }


def test_a_supplier_can_span_multiple_countries(demo):
    spans = demo.groupby("Supplier")["Country"].nunique()
    assert (spans > 1).any(), "Supplier→Country must not be modelled as a strict tree"
```

- [ ] **Step 2: Run them and confirm they fail**

```bash
python3 -m pytest tests/test_cte_core.py -v
```
Expected: FAIL with `AttributeError: module 'cte_core' has no attribute 'ensure_geo_columns'`.

- [ ] **Step 3: Add `PLANT_META` and `ensure_geo_columns` to cte_core.py**

Insert immediately after the `BASELINE_RATE = 220.0` line (currently `cte_core.py:37`):

```python
# ==========================================================================
# GEOGRAPHY (v3)
# ==========================================================================
# v3 treats Region AND Country as explicit data fields rather than parsing the
# country code out of the Plant name. This dict is the placeholder data layer:
# when the feature connects to the platform backend, both fields will arrive
# derived from Plant + Supplier information and this mapping goes away.
# Plant -> (Country, Region)
PLANT_META = {
    'Plant 1 (MX)': ('Mexico',        'North America'),
    'Plant 2 (US)': ('United States', 'North America'),
    'Plant 3 (DE)': ('Germany',       'Europe'),
    'Plant 4 (PL)': ('Poland',        'Europe'),
    'Plant 5 (CN)': ('China',         'APAC'),
    'Plant 6 (VN)': ('Vietnam',       'APAC'),
    'Plant 7 (BR)': ('Brazil',        'LATAM'),
}
UNKNOWN_GEO = ('Unknown', 'Other')


def ensure_geo_columns(df):
    """Guarantee explicit `Country` and `Region` columns on a record frame.

    Existing columns are left untouched, so a backend feed (or a sample CSV)
    that already carries real geography wins over this placeholder mapping.
    """
    out = df.copy()
    if 'Plant' not in out.columns:
        return out
    if 'Country' not in out.columns:
        out['Country'] = out['Plant'].map(lambda p: PLANT_META.get(p, UNKNOWN_GEO)[0])
    if 'Region' not in out.columns:
        out['Region'] = out['Plant'].map(lambda p: PLANT_META.get(p, UNKNOWN_GEO)[1])
    return out
```

- [ ] **Step 4: Replace the derived-Region block in `load_base_data`**

Delete `cte_core.py:268-278` (the `# ---- DERIVED (display-only) Region ----` comment, the `plant_to_region` dict, and the `data['Region'] = ...` line) and replace with:

```python
    # ---- EXPLICIT geography (v3): Country + Region --------------------------
    # See PLANT_META at the top of this module. Both fields are real columns,
    # not string-parsed at point of use.
    data = ensure_geo_columns(data)
```

- [ ] **Step 5: Mirror the change in `generate_sample_data.py`**

Replace `PLANT_TO_REGION` (`generate_sample_data.py:55-59`) with:
```python
# Plant -> (Country, Region); mirrors cte_core.PLANT_META.
PLANT_META = {
    'Plant 1 (MX)': ('Mexico',        'North America'),
    'Plant 2 (US)': ('United States', 'North America'),
    'Plant 3 (DE)': ('Germany',       'Europe'),
    'Plant 4 (PL)': ('Poland',        'Europe'),
    'Plant 5 (CN)': ('China',         'APAC'),
    'Plant 6 (VN)': ('Vietnam',       'APAC'),
    'Plant 7 (BR)': ('Brazil',        'LATAM'),
}
```

Replace `generate_sample_data.py:138` (`data['Region'] = data['Plant'].map(PLANT_TO_REGION).fillna('Other')`) with:
```python
    data['Country'] = data['Plant'].map(lambda p: PLANT_META.get(p, ('Unknown', 'Other'))[0])
    data['Region'] = data['Plant'].map(lambda p: PLANT_META.get(p, ('Unknown', 'Other'))[1])
```

- [ ] **Step 6: Run the full test file — baseline lock must still be green**

```bash
python3 -m pytest tests/test_cte_core.py -v
```
Expected: all pass, including `test_demo_data_math_is_unchanged`.

- [ ] **Step 7: Verify the sample-data generator still runs**

```bash
python3 generate_sample_data.py --num-tools 5 --weeks 4 --seed 1 --output _smoke.csv && python3 -c "import pandas as pd; d=pd.read_csv('sample_data/_smoke.csv'); print(sorted(d['Country'].unique()), sorted(d['Region'].unique()))" && rm sample_data/_smoke.csv
```
Expected: country and region lists print with no traceback.

- [ ] **Step 8: Commit**

```bash
git add cte_core.py generate_sample_data.py tests/test_cte_core.py
git commit -m "feat: explicit Country + Region columns via PLANT_META"
```

---

### Task 3: Multi-part tools in the demo data

Part C section 6 requires a part dropdown when a tool makes more than one part. Today every tool makes exactly one. `Part` is already a per-record column, so this is a data-generation change only — no schema or math change.

The extra part draws come from a **separate** `numpy` Generator so the existing `np.random` call sequence — and therefore every efficiency, hour, and shot value — is bit-identical. Only some `Part` *labels* change. The tuned scenario dynamics (`part_slopes`, `part_dyn`, `part_slow_bump`) stay keyed to each tool's **primary** part.

**Files:**
- Modify: `cte_core.py` (`load_base_data`, the per-tool loop around lines 170–241)
- Modify: `generate_sample_data.py` (`generate`, lines 86–132)
- Test: `tests/test_cte_core.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: demo data where `df.groupby('Tooling')['Part'].nunique().max() >= 2`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cte_core.py`:
```python
def test_some_tools_make_more_than_one_part(demo):
    parts_per_tool = demo.groupby("Tooling")["Part"].nunique()
    multi = int((parts_per_tool > 1).sum())
    assert multi >= 10, f"expected ~20-30% of {len(parts_per_tool)} tools multi-part, got {multi}"
    assert parts_per_tool.max() >= 3, "expected at least one three-part tool"


def test_multi_part_tools_did_not_disturb_the_math(demo):
    # Identical assertions to the baseline lock: Part labels moved, numbers did not.
    assert demo["Used_Hours"].sum() == pytest.approx(BASELINE_USED_HOURS, abs=1e-6)
    assert core.calc_weighted_eff(demo) == pytest.approx(BASELINE_WEIGHTED_EFF, abs=1e-9)
```

- [ ] **Step 2: Run and confirm the new test fails**

```bash
python3 -m pytest tests/test_cte_core.py -k multi -v
```
Expected: FAIL — `expected ~20-30% of 78 tools multi-part, got 0`.

- [ ] **Step 3: Add the secondary-part generator to `load_base_data`**

In `cte_core.py`, immediately before `records = []` (currently line 168), insert:

```python
    # Multi-part tools (v3): real client data has tools that mould more than one
    # part. Draws come from a DEDICATED generator so the global np.random
    # sequence — and therefore every hour / shot / efficiency value below — is
    # unchanged; only some Part *labels* differ. Scenario dynamics
    # (part_slopes / part_dyn / part_slow_bump) stay keyed to the tool's
    # PRIMARY part, which is what those scenarios were tuned against.
    part_rng = np.random.default_rng(2026)
```

Then inside the per-tool loop, immediately after the existing `part = np.random.choice(part_pools[t])` line (currently line 178), insert:

```python
            _r = part_rng.random()
            _n_extra = 2 if _r < 0.08 else (1 if _r < 0.28 else 0)
            tool_parts = [str(part)]
            if _n_extra:
                _pool = [p for p in part_pools[t] if p != part]
                tool_parts += [str(p) for p in part_rng.choice(_pool, size=min(_n_extra, len(_pool)),
                                                               replace=False)]
```

Finally, in the `records.append({...})` dict (currently line 238), replace:
```python
                        'Part': part, 'Tooling': tool_id, 'Date': date,
```
with:
```python
                        'Part': (tool_parts[0] if len(tool_parts) == 1
                                 else str(part_rng.choice(tool_parts))),
                        'Tooling': tool_id, 'Date': date,
```

- [ ] **Step 4: Run the tests**

```bash
python3 -m pytest tests/test_cte_core.py -v
```
Expected: all pass — the multi-part assertions AND the untouched baseline lock.

- [ ] **Step 5: Mirror it in `generate_sample_data.py`**

In `generate`, after `part = rng.choice(PARTS)` (line 92), insert:
```python
        _r = rng.random()
        _n_extra = 2 if _r < 0.08 else (1 if _r < 0.28 else 0)
        tool_parts = [str(part)]
        if _n_extra:
            _pool = [p for p in PARTS if p != part]
            tool_parts += [str(p) for p in rng.choice(_pool, size=_n_extra, replace=False)]
```
and in the `records.append({...})` dict replace `'Part': part,` with:
```python
                    'Part': (tool_parts[0] if len(tool_parts) == 1
                             else str(rng.choice(tool_parts))),
```

- [ ] **Step 6: Smoke-test the generator**

```bash
python3 generate_sample_data.py --num-tools 40 --weeks 4 --seed 3 --output _smoke.csv && python3 -c "import pandas as pd; d=pd.read_csv('sample_data/_smoke.csv'); print('multi-part tools:', int((d.groupby('Tooling')['Part'].nunique()>1).sum()))" && rm sample_data/_smoke.csv
```
Expected: a non-zero count.

- [ ] **Step 7: Commit**

```bash
git add cte_core.py generate_sample_data.py tests/test_cte_core.py
git commit -m "feat: multi-part tools in placeholder data (math unchanged)"
```

---

### Task 4: Time-range presets incl. "Last Quarter"

**Files:**
- Modify: `cte_core.py` (append to section 6)
- Test: `tests/test_cte_core.py`

**Interfaces:**
- Produces: `core.TIME_RANGE_PRESETS: list[str]` and `core.resolve_time_range(preset, max_date) -> (pd.Timestamp, pd.Timestamp)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cte_core.py`:
```python
def test_time_range_presets_have_no_last_90_days():
    assert core.TIME_RANGE_PRESETS == [
        "Last 7 Days", "Last 30 Days", "Last Quarter", "Last 12 Months", "Custom Range",
    ]


def test_last_quarter_is_the_previous_complete_calendar_quarter():
    # 2026-07-06 sits in Q3 2026, so "Last Quarter" is Q2 2026 (Apr-Jun).
    start, end = core.resolve_time_range("Last Quarter", pd.Timestamp("2026-07-06"))
    assert start == pd.Timestamp("2026-04-01")
    assert end.date() == pd.Timestamp("2026-06-30").date()
    assert end > pd.Timestamp("2026-06-30 23:00:00")


def test_last_quarter_wraps_across_the_year_boundary():
    start, end = core.resolve_time_range("Last Quarter", pd.Timestamp("2026-01-15"))
    assert start == pd.Timestamp("2025-10-01")
    assert end.date() == pd.Timestamp("2025-12-31").date()


def test_rolling_presets():
    mx = pd.Timestamp("2026-07-06")
    assert core.resolve_time_range("Last 7 Days", mx)[0] == pd.Timestamp("2026-06-29")
    assert core.resolve_time_range("Last 30 Days", mx)[0] == pd.Timestamp("2026-06-06")
    assert core.resolve_time_range("Last 12 Months", mx)[0] == pd.Timestamp("2025-07-06")
    assert core.resolve_time_range("Last 7 Days", mx)[1] == mx


def test_unknown_preset_raises():
    with pytest.raises(ValueError):
        core.resolve_time_range("Last 90 Days", pd.Timestamp("2026-07-06"))
```

- [ ] **Step 2: Run and confirm failure**

```bash
python3 -m pytest tests/test_cte_core.py -k time_range -v
```
Expected: FAIL — `module 'cte_core' has no attribute 'TIME_RANGE_PRESETS'`.

- [ ] **Step 3: Implement**

Append to `cte_core.py` at the end of section 6 (after `act_weighted_deviation_trend`):

```python
# --------------------------------------------------------------------------
# TIME RANGE PRESETS (v3)
# --------------------------------------------------------------------------
TIME_RANGE_PRESETS = [
    "Last 7 Days", "Last 30 Days", "Last Quarter", "Last 12 Months", "Custom Range",
]


def resolve_time_range(preset, max_date):
    """Resolve a v3 Time Range preset to a (start, end) timestamp pair.

    "Last Quarter" is the previous COMPLETE calendar quarter relative to
    max_date — the quarter currently in progress is excluded entirely.
    Calendar quarters are Jan-Mar / Apr-Jun / Jul-Sep / Oct-Dec, matching the
    app's existing quarter bucketing.
    """
    mx = pd.Timestamp(max_date)
    if preset == "Last 7 Days":
        return mx - pd.Timedelta(days=7), mx
    if preset == "Last 30 Days":
        return mx - pd.Timedelta(days=30), mx
    if preset == "Last Quarter":
        curr_q_start = mx.to_period('Q').start_time
        prev_q = (curr_q_start - pd.Timedelta(days=1)).to_period('Q')
        return prev_q.start_time, prev_q.end_time
    if preset == "Last 12 Months":
        return mx - pd.DateOffset(months=12), mx
    raise ValueError(f"Unknown time-range preset: {preset!r}")
```

- [ ] **Step 4: Run the tests**

```bash
python3 -m pytest tests/test_cte_core.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add cte_core.py tests/test_cte_core.py
git commit -m "feat: v3 time-range presets with previous-complete-quarter logic"
```

---

### Task 5: CT Split & Shot Trend aggregation (Trend Graph 2 data)

The one genuinely new aggregation in v3: shot-share Fast/Within/Slow **per time bucket**. It reuses the per-record `Shots_Gained` / `Shots_Lost` / `Total_Shots` columns that `apply_tolerance` already classifies, grouped by month/quarter instead of by entity, and calls `calc_weighted_eff` per bucket (pooling first — never averaging tool scores).

**Files:**
- Modify: `cte_core.py` (new section 6b)
- Test: `tests/test_cte_core.py`

**Interfaces:**
- Produces:
  - `core.ct_split_shot_trend(df, freq='M') -> DataFrame[bucket, Total Shots, Fast Shots (%), Within Shots (%), Slow Shots (%), CT Efficiency %, Saving Opportunity ($), Loss ($)]`
  - `core.ct_split_summary(df, freq='M') -> dict{pct_fast, pct_within, pct_slow, ct_compliance, total_shots, active_buckets}`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cte_core.py`:
```python
def _two_bucket_frame():
    """Hand-built frame: Jan = 1 fast + 1 within record, Feb = 1 slow record."""
    return pd.DataFrame([
        # Jan: fast, 3000 shots, 100 used hours vs 110 expected -> eff 110%
        dict(Date=pd.Timestamp("2026-01-10"), Tolerance_Status="Fast",
             Total_Shots=3000, Shots_Gained=3000, Shots_Lost=0,
             Used_Hours=100.0, Expected_Hours=110.0,
             Financial_Gain=2200.0, Financial_Loss=0.0, Tooling="T1"),
        # Jan: within, 1000 shots
        dict(Date=pd.Timestamp("2026-01-20"), Tolerance_Status="Within",
             Total_Shots=1000, Shots_Gained=0, Shots_Lost=0,
             Used_Hours=50.0, Expected_Hours=50.0,
             Financial_Gain=0.0, Financial_Loss=0.0, Tooling="T2"),
        # Feb: slow, 2000 shots, 100 used vs 80 expected -> eff 80%
        dict(Date=pd.Timestamp("2026-02-05"), Tolerance_Status="Slow",
             Total_Shots=2000, Shots_Gained=0, Shots_Lost=2000,
             Used_Hours=100.0, Expected_Hours=80.0,
             Financial_Gain=0.0, Financial_Loss=4400.0, Tooling="T1"),
    ])


def test_ct_split_shot_trend_monthly_shares():
    t = core.ct_split_shot_trend(_two_bucket_frame(), freq="M")
    assert len(t) == 2
    jan, feb = t.iloc[0], t.iloc[1]
    assert jan["Total Shots"] == 4000
    assert jan["Fast Shots (%)"] == pytest.approx(75.0)
    assert jan["Within Shots (%)"] == pytest.approx(25.0)
    assert jan["Slow Shots (%)"] == pytest.approx(0.0)
    # pooled weighted eff, not an average of the two records
    assert jan["CT Efficiency %"] == pytest.approx(110.0 * 0.75 + 100.0 * 0.25)
    assert jan["Saving Opportunity ($)"] == pytest.approx(2200.0)
    assert feb["Slow Shots (%)"] == pytest.approx(100.0)
    assert feb["CT Efficiency %"] == pytest.approx(80.0)
    assert feb["Loss ($)"] == pytest.approx(4400.0)


def test_ct_split_shot_trend_quarterly_pools_months_together():
    t = core.ct_split_shot_trend(_two_bucket_frame(), freq="Q")
    assert len(t) == 1
    assert t.iloc[0]["Total Shots"] == 6000
    assert t.iloc[0]["Fast Shots (%)"] == pytest.approx(50.0)
    assert t.iloc[0]["Slow Shots (%)"] == pytest.approx(2000 / 6000 * 100)


def test_ct_split_shot_trend_empty_frame_returns_empty_with_columns():
    t = core.ct_split_shot_trend(pd.DataFrame(), freq="M")
    assert t.empty
    assert "Fast Shots (%)" in t.columns


def test_ct_split_summary_compliance_is_fast_plus_within():
    s = core.ct_split_summary(_two_bucket_frame(), freq="M")
    assert s["total_shots"] == 6000
    assert s["active_buckets"] == 2
    assert s["pct_fast"] == pytest.approx(50.0)
    assert s["pct_slow"] == pytest.approx(2000 / 6000 * 100)
    assert s["pct_within"] == pytest.approx(1000 / 6000 * 100)
    assert s["ct_compliance"] == pytest.approx(s["pct_fast"] + s["pct_within"])


def test_bucket_shares_always_sum_to_100(demo):
    t = core.ct_split_shot_trend(demo, freq="M")
    total = t["Fast Shots (%)"] + t["Within Shots (%)"] + t["Slow Shots (%)"]
    assert np.allclose(total.values, 100.0)
```

- [ ] **Step 2: Run and confirm failure**

```bash
python3 -m pytest tests/test_cte_core.py -k ct_split -v
```
Expected: FAIL — `module 'cte_core' has no attribute 'ct_split_shot_trend'`.

- [ ] **Step 3: Implement**

Append to `cte_core.py` after `resolve_time_range`:

```python
# ==========================================================================
# 6b. CT SPLIT & SHOT TREND  (v3 -- Trend Graph 2)
# ==========================================================================
# Shot-share Fast/Within/Slow per time bucket. Reuses the per-record
# Shots_Gained / Shots_Lost / Total_Shots columns that apply_tolerance already
# classifies at the active tolerance band -- this only regroups them by
# month/quarter instead of by entity. Efficiency per bucket pools the bucket's
# raw hours and calls calc_weighted_eff ONCE (never an average of tool scores).
CT_SPLIT_COLS = [
    'bucket', 'Total Shots', 'CT Efficiency %',
    'Fast Shots (%)', 'Within Shots (%)', 'Slow Shots (%)',
    'Saving Opportunity ($)', 'Loss ($)',
]


def ct_split_shot_trend(df, freq='M'):
    """Per-bucket shot split + efficiency + financials for Trend Graph 2.

    freq: 'M' (month) or 'Q' (calendar quarter), matching the app's existing
    Month-to-Month / Quarter-to-Quarter toggle.

    Returns a DataFrame with CT_SPLIT_COLS. Buckets with zero shots are
    dropped so an idle month never renders a 0/0/0 split.
    """
    if df is None or df.empty or 'Date' not in df.columns:
        return pd.DataFrame(columns=CT_SPLIT_COLS)
    d = df.copy()
    d['bucket'] = d['Date'].dt.to_period(freq).dt.start_time

    rows = []
    for bucket, g in d.groupby('bucket'):
        tot = g['Total_Shots'].sum()
        if tot <= 0:
            continue
        fast_pct = g['Shots_Gained'].sum() / tot * 100.0
        slow_pct = g['Shots_Lost'].sum() / tot * 100.0
        rows.append({
            'bucket': bucket,
            'Total Shots': int(tot),
            'CT Efficiency %': calc_weighted_eff(g),
            'Fast Shots (%)': fast_pct,
            'Slow Shots (%)': slow_pct,
            'Within Shots (%)': 100.0 - fast_pct - slow_pct,
            'Saving Opportunity ($)': float(g['Financial_Gain'].sum()) if 'Financial_Gain' in g else 0.0,
            'Loss ($)': float(g['Financial_Loss'].sum()) if 'Financial_Loss' in g else 0.0,
        })
    if not rows:
        return pd.DataFrame(columns=CT_SPLIT_COLS)
    return (pd.DataFrame(rows)[CT_SPLIT_COLS]
              .sort_values('bucket')
              .reset_index(drop=True))


def ct_split_summary(df, freq='M'):
    """Headline stat line above Trend Graph 2.

    NOTE ON NAMING: `ct_compliance` here is Faster% + Within% -- the share of
    shots produced at or better than the approved cycle time. It is a
    DIFFERENT metric from the app's canonical Weighted CT Efficiency
    (calc_weighted_eff) and from the backend spec's own within-band-only
    `ct_compliance`. Always render it with the Graph 2 footnote so the three
    are never confused.

    Returns dict: pct_fast, pct_within, pct_slow, ct_compliance, total_shots,
    active_buckets. Percentages are 0.0 when there are no shots.
    """
    empty = {'pct_fast': 0.0, 'pct_within': 0.0, 'pct_slow': 0.0,
             'ct_compliance': 0.0, 'total_shots': 0, 'active_buckets': 0}
    if df is None or df.empty:
        return empty
    tot = df['Total_Shots'].sum()
    if tot <= 0:
        return empty
    pct_fast = df['Shots_Gained'].sum() / tot * 100.0
    pct_slow = df['Shots_Lost'].sum() / tot * 100.0
    pct_within = 100.0 - pct_fast - pct_slow
    return {
        'pct_fast': float(pct_fast),
        'pct_within': float(pct_within),
        'pct_slow': float(pct_slow),
        'ct_compliance': float(pct_fast + pct_within),
        'total_shots': int(tot),
        'active_buckets': int(len(ct_split_shot_trend(df, freq))),
    }
```

- [ ] **Step 4: Run the tests**

```bash
python3 -m pytest tests/test_cte_core.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add cte_core.py tests/test_cte_core.py
git commit -m "feat: ct_split_shot_trend + ct_split_summary for Trend Graph 2"
```

---

### Task 6: Scope summary, financial rankings, generic detail table

Three assembly helpers every v3 level needs. All numbers come from existing functions.

**Files:**
- Modify: `cte_core.py` (new section 6c + v3 column constants)
- Test: `tests/test_cte_core.py`

**Interfaces:**
- Produces:
  - `core.scope_summary(df, tolerance_pct=DEFAULT_TOLERANCE_PCT, entity_dim='Tooling') -> dict{total, fast, within, slow, pct_fast, pct_within, pct_slow, saving_opportunity, loss, net}`
  - `core.ranking_by_financial(df, col, metric='Financial Gained', top_n=None, tolerance_pct=...) -> DataFrame`
  - `core.entity_detail_table(df, dim, extra_cols=(), period_label='', tolerance_pct=...) -> DataFrame`
  - `core.V3_SUPPLIER_COLS`, `core.V3_TOOL_COLS`, `core.V3_TYPE_COLS`, `core.V3_PART_COLS`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cte_core.py`:
```python
@pytest.fixture(scope="module")
def priced(demo):
    return core.apply_financials(core.apply_tolerance(demo, 5.0), 40.0, 180.0)


def test_scope_summary_counts_tools_and_sums_dollars(priced):
    s = core.scope_summary(priced, 5.0)
    assert s["total"] == priced["Tooling"].nunique()
    assert s["fast"] + s["within"] + s["slow"] == s["total"]
    assert s["saving_opportunity"] == pytest.approx(priced["Financial_Gain"].sum())
    assert s["loss"] == pytest.approx(priced["Financial_Loss"].sum())
    assert s["net"] == pytest.approx(s["saving_opportunity"] - s["loss"])


def test_scope_summary_can_count_parts_instead_of_tools(priced):
    s = core.scope_summary(priced, 5.0, entity_dim="Part")
    assert s["total"] == priced["Part"].nunique()


def test_scope_summary_matches_fast_within_slow_summary(priced):
    a = core.scope_summary(priced, 5.0)
    b = core.fast_within_slow_summary(priced, "Tooling", 5.0)
    assert (a["fast"], a["within"], a["slow"]) == (b["fast"], b["within"], b["slow"])


def test_ranking_by_financial_sorts_descending_and_reranks(priced):
    r = core.ranking_by_financial(priced, "Supplier", "Financial Gained", top_n=5)
    assert len(r) == 5
    assert r["Rank"].tolist() == [1, 2, 3, 4, 5]
    assert r["Financial Gained"].is_monotonic_decreasing


def test_ranking_by_financial_loss_variant(priced):
    r = core.ranking_by_financial(priced, "Country", "Financial Lost")
    assert r["Financial Lost"].is_monotonic_decreasing
    assert set(r["Country"]) <= set(priced["Country"].unique())


def test_entity_detail_table_collapses_extra_cols(priced):
    t = core.entity_detail_table(priced, "Supplier", extra_cols=("Country",))
    assert len(t) == priced["Supplier"].nunique()
    assert "Country" in t.columns
    # a supplier spanning two countries renders both, comma-joined
    assert t["Country"].str.contains(",").any()
    assert "CT Weighted Average Efficiency" in t.columns


def test_entity_detail_table_efficiency_matches_calc_weighted_eff(priced):
    t = core.entity_detail_table(priced, "Supplier")
    for sup in t["Supplier"].head(3):
        expected = core.calc_weighted_eff(priced[priced["Supplier"] == sup])
        got = t.loc[t["Supplier"] == sup, "CT Weighted Average Efficiency"].iloc[0]
        assert got == pytest.approx(expected, abs=1e-9)


def test_v3_column_constants_exist():
    for const in ("V3_SUPPLIER_COLS", "V3_TOOL_COLS", "V3_TYPE_COLS", "V3_PART_COLS"):
        assert isinstance(getattr(core, const), list)
    assert "Tooling ID" in core.V3_TOOL_COLS
    assert "Country" in core.V3_TOOL_COLS
```

- [ ] **Step 2: Run and confirm failure**

```bash
python3 -m pytest tests/test_cte_core.py -k "scope_summary or ranking_by or entity_detail or v3_column" -v
```
Expected: FAIL — `module 'cte_core' has no attribute 'scope_summary'`.

- [ ] **Step 3: Implement**

Append to `cte_core.py` after the `ct_split_summary` function:

```python
# ==========================================================================
# 6c. V3 SCOPE HELPERS  (assembly only -- every number comes from the
#     existing functions above)
# ==========================================================================
def scope_summary(df, tolerance_pct=DEFAULT_TOLERANCE_PCT, entity_dim='Tooling'):
    """The six summary tiles shared by every v3 level.

    Counts are per-entity classifications from fast_within_slow_summary
    (default entity = Tooling; pass entity_dim='Part' for the Part Overview).
    Dollars are pooled record sums, so they are independent of the entity
    classification and never double-count.
    """
    s = fast_within_slow_summary(df, entity_dim, tolerance_pct)
    gain = float(df['Financial_Gain'].sum()) if not df.empty and 'Financial_Gain' in df else 0.0
    loss = float(df['Financial_Loss'].sum()) if not df.empty and 'Financial_Loss' in df else 0.0
    s['saving_opportunity'] = gain
    s['loss'] = loss
    s['net'] = gain - loss
    return s


def ranking_by_financial(df, col, metric='Financial Gained',
                         top_n=None, tolerance_pct=DEFAULT_TOLERANCE_PCT):
    """Ranking list ordered by dollars rather than efficiency.

    Thin wrapper over generate_ranking_table_data (whose math is unchanged);
    it only re-sorts and re-numbers. metric is 'Financial Gained' (saving
    opportunity) or 'Financial Lost'.
    """
    agg = generate_ranking_table_data(df, col, tolerance_pct)
    if agg.empty or metric not in agg.columns:
        return agg
    out = agg.sort_values(metric, ascending=False)
    if top_n:
        out = out.head(top_n)
    out = out.reset_index(drop=True)
    out['Rank'] = range(1, len(out) + 1)
    return out


def entity_detail_table(df, dim, extra_cols=(), period_label="",
                        tolerance_pct=DEFAULT_TOLERANCE_PCT):
    """One comprehensive row per entity in `dim`, plus descriptive columns.

    Each row is compute_comprehensive_row (unchanged math) for that entity's
    pooled slice. `extra_cols` are descriptive dimensions (Country, Region,
    Plant, ...) collapsed to the distinct values present for that entity and
    comma-joined -- so a supplier operating in two countries shows both,
    rather than silently dropping one.
    """
    if df.empty:
        return pd.DataFrame()
    rows = []
    for name, g in df.groupby(dim):
        row = compute_comprehensive_row(name, g, dim, period_label,
                                        tolerance_pct=tolerance_pct)
        for c in extra_cols:
            if c in g.columns:
                row[c] = ", ".join(sorted(str(v) for v in g[c].dropna().unique()))
        row['Total Toolings'] = g['Tooling'].nunique()
        rows.append(row)
    out = pd.DataFrame(rows)
    return out.sort_values('CT Weighted Average Efficiency').reset_index(drop=True)


# ---- v3 display column sets (see cte_ui.V3_DISPLAY_RENAME for the labels) --
V3_SUPPLIER_COLS = [
    'Supplier', 'Country', 'Total Toolings', 'Total Shots',
    'CT Weighted Average Efficiency', 'Financial Gain', 'Financial Loss',
    'Fast Shots (%)', 'Within Shots (%)', 'Slow Shots (%)',
]
V3_TOOL_COLS = [
    'Tooling ID', 'Region', 'Country', 'Plant', 'ACT', 'Actual Average CT (WACT)',
    'CT Weighted Average Efficiency', 'Fast Shots (%)', 'Within Shots (%)',
    'Slow Shots (%)', 'Financial Gain', 'Financial Loss', 'Net Financial',
]
V3_TYPE_COLS = [
    'Tooling Type', 'Total Toolings', 'Total Shots',
    'CT Weighted Average Efficiency', 'Fast Shots (%)', 'Within Shots (%)',
    'Slow Shots (%)', 'Financial Gain', 'Financial Loss',
]
V3_PART_COLS = [
    'Part', 'Part Name', 'Total Toolings', 'Total Shots',
    'CT Weighted Average Efficiency', 'Fast Shots (%)', 'Within Shots (%)',
    'Slow Shots (%)', 'Financial Gain', 'Financial Loss',
]
```

Note: `compute_comprehensive_row` only injects `Supplier`/`Plant` for `group_col == 'Tooling ID'`. `entity_detail_table` is therefore always called with `extra_cols` naming whatever descriptive columns that view needs — including for the tool table, where `dim='Tooling'` and the row's own key column must be renamed to `Tooling ID` by the caller (Task 11).

- [ ] **Step 4: Run the tests**

```bash
python3 -m pytest tests/test_cte_core.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add cte_core.py tests/test_cte_core.py
git commit -m "feat: v3 scope summary, financial rankings, generic detail table"
```

---

### Task 7: `cte_ui.py` — theme, tiles, table helpers

Extract everything presentational from the current app file so the view modules can share it. This task changes no behaviour; the existing app keeps running because nothing imports the new module yet.

**Files:**
- Create: `cte_ui.py`
- Test: manual import check (this module is Streamlit-bound; its logic is covered by the app run in Task 14).

**Interfaces:**
- Produces: `GREEN, YELLOW, RED, GREY, STATUS_COLORS`, `inject_theme()`, `RANK_FMT`, `DETAIL_FMT`, `V3_DISPLAY_RENAME`, `style_table(df, fmt_map)`, `neg_help(df)`, `search_box(df, key)`, `download_csv(df, label, fname, key)`, `bucket_label(ts, freq)`, `summary_tiles(summary, entity_noun='Tools')`, `section(title, size='1.4rem')`, `entity_badge(prefix, label)`, `render_breadcrumb(frames, on_click)`, `v3_display(df)`, `trend_change_css(v)`, `TREND2_FMT`.

- [ ] **Step 1: Create the module**

`cte_ui.py`:
```python
"""
cte_ui.py
=========
Presentation layer shared by every v3 view: theme CSS, colors, number
formats, table styling, and the small reusable blocks (summary tiles,
breadcrumb, section headings).

No business math lives here. Anything numeric comes from cte_core.
"""

import pandas as pd
import streamlit as st

GREEN, YELLOW, RED, GREY = "#5cb85c", "#eab308", "#d9534f", "#94a3b8"
STATUS_COLORS = {"Within": GREEN, "Slow": YELLOW, "Fast": RED}


def inject_theme():
    """Enterprise dark theme. Carried over verbatim from the Executive app,
    plus v3's breadcrumb and summary-tile rules."""
    st.markdown(_THEME_CSS, unsafe_allow_html=True)
```

Then set `_THEME_CSS` to the **entire** `<style>...</style>` block currently at `Cycle-Time-Efficiency-v3.py:48-143`, copied verbatim into a triple-quoted string, with these additions appended inside the `<style>` block before `</style>`:

```css
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
```

Then append the rest of the module:

```python
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
    st.markdown(f'<div class="section-title" style="font-size:{size};">{title}</div>',
                unsafe_allow_html=True)


def entity_badge(prefix, label):
    st.markdown(f"""<div style="display:flex;align-items:center;gap:12px;margin-bottom:1.25rem;">
  <span style="font-size:1.3rem;font-weight:700;color:#fff;">{prefix}</span>
  <span class="entity-badge">{label}</span>
</div>""", unsafe_allow_html=True)


def _tile(label, value, color, sub=""):
    sub_html = f'<div class="v3-tile-sub">{sub}</div>' if sub else ""
    return (f'<div class="v3-tile"><div class="v3-tile-label">{label}</div>'
            f'<div class="v3-tile-num" style="color:{color};">{value}</div>{sub_html}</div>')


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
```

- [ ] **Step 2: Verify the module imports cleanly**

```bash
python3 -c "import cte_ui; print(len(cte_ui._THEME_CSS), 'css chars;', cte_ui.RED, cte_ui.V3_DISPLAY_RENAME['Financial Gain'])"
```
Expected: a css char count > 3000, `#d9534f`, `Saving Opportunity`.

- [ ] **Step 3: Commit**

```bash
git add cte_ui.py
git commit -m "feat: cte_ui presentation layer extracted for v3"
```

---

### Task 8: `cte_nav.py` — level registry and navigation stack

This is the heart of the new information architecture: Executive's two hard-coded levels become an N-frame stack.

**Files:**
- Create: `cte_nav.py`
- Test: `tests/test_cte_nav.py`

**Interfaces:**
- Produces:
  - `LEVELS: dict[str, dict]` with keys `label`, `col`, `child`, `trend_dim`, `entity_noun`
  - `ROOTS: list[tuple[str, str]]` — (tab label, root level key)
  - `scope_df(df, stack) -> DataFrame` (pure — testable without Streamlit)
  - `crumb_labels(stack) -> list[tuple[int, str]]` (pure)
  - `get_stack()`, `set_root(level)`, `push(level, value)`, `pop_to(index)`, `current()` — session-state bound

- [ ] **Step 1: Write the failing tests**

`tests/test_cte_nav.py`:
```python
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cte_nav as nav


@pytest.fixture
def frame():
    return pd.DataFrame({
        "Region": ["APAC", "APAC", "Europe", "APAC"],
        "Country": ["China", "Vietnam", "Germany", "China"],
        "Supplier": ["Foxconn", "Foxconn", "Bosch Tooling", "Jabil"],
        "Tooling": ["TL-001", "TL-002", "TL-003", "TL-004"],
        "Tooling Type": ["Injection Molding"] * 4,
        "Part": ["Part-001", "Part-002", "Part-003", "Part-001"],
    })


def test_level_registry_chain_is_complete():
    assert nav.LEVELS["global"]["child"] == "region"
    assert nav.LEVELS["region"]["child"] == "country"
    assert nav.LEVELS["country"]["child"] == "supplier"
    assert nav.LEVELS["supplier"]["child"] == "tool"
    assert nav.LEVELS["tool"]["child"] is None
    assert nav.LEVELS["part"]["child"] == "part_tools"
    assert nav.LEVELS["part_tools"]["child"] == "tool"


def test_every_level_declares_a_trend_dim():
    for key, cfg in nav.LEVELS.items():
        assert cfg["trend_dim"] in {"Supplier", "Tooling", "Tooling Type", "Part"}, key


def test_scope_df_applies_each_frame_in_order(frame):
    stack = [("global", None), ("region", "APAC"), ("country", "China")]
    out = nav.scope_df(frame, stack)
    assert sorted(out["Tooling"]) == ["TL-001", "TL-004"]


def test_scope_df_root_frames_do_not_filter(frame):
    assert len(nav.scope_df(frame, [("global", None)])) == 4
    assert len(nav.scope_df(frame, [("part_all", None)])) == 4


def test_scope_df_down_to_a_single_tool(frame):
    stack = [("global", None), ("region", "APAC"), ("country", "China"),
             ("supplier", "Foxconn"), ("tool", "TL-001")]
    out = nav.scope_df(frame, stack)
    assert out["Tooling"].tolist() == ["TL-001"]


def test_scope_df_cross_cutting_part_path_ignores_geography(frame):
    stack = [("part_all", None), ("part", "Part-001")]
    out = nav.scope_df(frame, stack)
    assert sorted(out["Tooling"]) == ["TL-001", "TL-004"]


def test_crumb_labels_uses_values_after_the_root():
    stack = [("global", None), ("region", "APAC"), ("supplier", "Foxconn")]
    assert nav.crumb_labels(stack) == [(0, "Global"), (1, "APAC"), (2, "Foxconn")]


def test_scope_df_on_missing_column_is_a_no_op(frame):
    out = nav.scope_df(frame.drop(columns=["Country"]), [("global", None), ("country", "China")])
    assert len(out) == 4
```

- [ ] **Step 2: Run and confirm failure**

```bash
python3 -m pytest tests/test_cte_nav.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'cte_nav'`.

- [ ] **Step 3: Implement**

`cte_nav.py`:
```python
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
```

- [ ] **Step 4: Run the tests**

```bash
python3 -m pytest tests/test_cte_nav.py -v
```
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add cte_nav.py tests/test_cte_nav.py
git commit -m "feat: cte_nav level registry + N-level navigation stack"
```

---

### Task 9: `cte_charts.py` — both trend graphs, pies, ranking bars

Every level shows the same two trend graphs. This module builds them once.

**Files:**
- Create: `cte_charts.py`
- Test: verified in-app in Task 14 (Plotly figures + Streamlit rendering).

**Interfaces:**
- Consumes: `core.act_weighted_deviation_trend`, `core.ct_split_shot_trend`, `core.ct_split_summary`, `core.entity_efficiency`, `core.fast_within_slow_summary`, `cte_ui.*`
- Produces: `render_trend_block(trend_scope_df, trend_dim, keyns)`, `small_multiple_pies(df, dim, tolerance_pct, keyns, max_pies=8)`, `single_pie(df, tolerance_pct, keyns, title='Cycle Time Efficiency Split')`, `ranking_bars(df, dims, tolerance_pct, keyns, top_n=10)`, `TREND2_FOOTNOTE`

- [ ] **Step 1: Create the module**

`cte_charts.py`:
```python
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

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import cte_core as core
import cte_ui as ui

TREND2_FOOTNOTE = (
    "Faster / Within / Slower = share of shots produced faster than, within "
    "(±tolerance of), or slower than the Approved Cycle Time · shot-weighted "
    "across all tools with cycle-time data · bars show all recorded shots. "
    "CT Compliance = Faster% + Within%; it is a different measure from the "
    "Cycle Time Efficiency shown elsewhere, which is the shot-share weighted "
    "average of the three category efficiencies."
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
def _render_deviation_graph(df, dim, freq, period_word, keyns):
    ui.section("ACT-Weighted Deviation", size="1.1rem")
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
    st.dataframe(sty, use_container_width=True, hide_index=True, column_config={
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
        f'<b>CT Compliance {summ["ct_compliance"]:.0f}%</b> &nbsp;·&nbsp; '
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
    st.dataframe(ui.style_table(disp, ui.TREND2_FMT), use_container_width=True, hide_index=True)


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
            st.markdown(f'<div style="text-align:center;color:#e2e8f0;font-size:.92rem;'
                        f'font-weight:600;margin-bottom:2px;">{ent}</div>',
                        unsafe_allow_html=True)
            st.plotly_chart(_pie_figure([s['fast'], s['within'], s['slow']]),
                            use_container_width=True, key=f"pie_{keyns}_{ent}")
            st.markdown(f'<div style="text-align:center;color:#64748b;font-size:.78rem;">'
                        f'{s["total"]} tools</div>', unsafe_allow_html=True)
    if len(entities) > max_pies:
        st.caption(f"Showing {max_pies} of {len(entities)} {dim.lower()}s — "
                   f"use the Master Filter to narrow further.")


def single_pie(df, tolerance_pct, keyns, title="Cycle Time Efficiency Split"):
    s = core.fast_within_slow_summary(df, 'Tooling', tolerance_pct)
    st.markdown(f'<div style="text-align:center;color:#e2e8f0;font-size:1.05rem;'
                f'font-weight:600;margin-bottom:4px;">{title}</div>', unsafe_allow_html=True)
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
                        f'margin-bottom:4px;">{title}</div>', unsafe_allow_html=True)
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
```

- [ ] **Step 2: Verify it imports and the figure builders work headless**

```bash
python3 -c "
import pandas as pd, cte_core as core, cte_charts as ch
d = core.apply_financials(core.apply_tolerance(core.load_base_data.__wrapped__(version=11), 5.0), 40.0, 180.0)
print(core.ct_split_shot_trend(d, 'M').head(3).to_string())
print(core.ct_split_summary(d, 'M'))
print(ch._pie_figure([3,4,5]).to_dict()['data'][0]['values'])
"
```
Expected: a 3-row monthly split table whose percentages sum to 100, a summary dict, and `(3, 4, 5)`.

- [ ] **Step 3: Commit**

```bash
git add cte_charts.py
git commit -m "feat: cte_charts with reused Graph 1 and new CT Split & Shot Trend"
```

---

### Task 10: `cte_views.py` — scope overview (Global / Region / Country)

Part C sections 1, 2 and 3 are the same page with a different child dimension, so they share one renderer.

**Files:**
- Create: `cte_views.py`
- Test: in-app in Task 14.

**Interfaces:**
- Consumes: `cte_core`, `cte_nav`, `cte_ui`, `cte_charts`
- Produces: `render_scope_overview(ctx)` where `ctx` is the `Ctx` dataclass defined below; `Ctx(scope_df, trend_df, level, value, tolerance_pct, period_label, keyns)`

- [ ] **Step 1: Create the module with the context object and the scope renderer**

`cte_views.py`:
```python
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
    """Render a table whose row click drills into `level`."""
    event = st.dataframe(
        ui.style_table(ui.v3_display(df), ui.DETAIL_FMT),
        use_container_width=True, hide_index=True,
        on_select="rerun", selection_mode="single-row",
        key=f"tbl_{keyns}", column_config=ui.neg_help(df))
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
```

Note: the supplier table drills to `'supplier'` regardless of the current level, so the stack may read `Global › Foxconn` (skipping Region/Country). That is intentional — the supplier table at Global scope lists every supplier, and `scope_df` filters only on the frames present.

- [ ] **Step 2: Verify it imports**

```bash
python3 -c "import cte_views; print(cte_views.Ctx.__doc__.splitlines()[0]); print(cte_views._ranking_dims('global'))"
```
Expected: the docstring line and the six global ranking dimensions.

- [ ] **Step 3: Commit**

```bash
git add cte_views.py
git commit -m "feat: v3 scope overview renderer for Global/Region/Country"
```

---

### Task 11: Supplier view + individual tool report

**Files:**
- Modify: `cte_views.py`

**Interfaces:**
- Consumes: `Ctx`, `_drill`, `_table_drill` from Task 10.
- Produces: `render_supplier(ctx)`, `render_tool(ctx)`

- [ ] **Step 1: Append the supplier renderer**

Append to `cte_views.py`:
```python
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
```

- [ ] **Step 2: Append the tool report renderer**

Append to `cte_views.py`:
```python
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
        with st.expander(f"Parts ({len(parts)})", expanded=False):
            for p in parts:
                st.markdown(f"- **{p}** — {part_names.get(p, '')}")

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
```

- [ ] **Step 3: Verify import + the tool-table shape headless**

```bash
python3 -c "
import cte_core as core, cte_views as v
d = core.apply_financials(core.apply_tolerance(core.load_base_data.__wrapped__(version=11), 5.0), 40.0, 180.0)
t = v._tool_table(d[d['Supplier']=='Foxconn'], '', 5.0)
print(list(t.columns)); print(len(t), 'tools')
"
```
Expected: exactly `core.V3_TOOL_COLS` in order, and a tool count > 0.

- [ ] **Step 4: Commit**

```bash
git add cte_views.py
git commit -m "feat: v3 supplier overview and individual tool report"
```

---

### Task 12: Tooling Type and Part views

**Files:**
- Modify: `cte_views.py`

**Interfaces:**
- Produces: `render_type_all(ctx)`, `render_type(ctx)`, `render_part_all(ctx)`, `render_part(ctx)`, `render_part_tools(ctx)`

- [ ] **Step 1: Append the Tooling Type renderers**

Append to `cte_views.py`:
```python
def render_type_all(ctx):
    """Part C section 5 — Tooling Type overview across all types."""
    ui.section("Summary")
    ui.summary_tiles(core.scope_summary(ctx.scope, ctx.tolerance_pct), "Tools")

    st.markdown("<br>", unsafe_allow_html=True)
    ui.section("Cycle Time Efficiency by Tooling Type", size="1.1rem")
    ch.small_multiple_pies(ctx.scope, 'Tooling Type', ctx.tolerance_pct, ctx.keyns)

    st.markdown("<br>", unsafe_allow_html=True)
    ui.section("Saving Opportunity & Loss by Tooling Type", size="1.1rem")
    ch.ranking_bars(ctx.scope, ['Tooling Type'], ctx.tolerance_pct, ctx.keyns)

    st.markdown("<hr style='border-color:#2d3748;margin:1.75rem 0;'>", unsafe_allow_html=True)
    ch.render_trend_block(ctx.trend, 'Tooling Type', ctx.keyns)

    st.markdown("<hr style='border-color:#2d3748;margin:1.75rem 0;'>", unsafe_allow_html=True)
    ui.section("Tooling Type Detail")
    st.caption("Select a row to open that tooling type.")
    t = core.entity_detail_table(ctx.scope, 'Tooling Type', period_label=ctx.period_label,
                                tolerance_pct=ctx.tolerance_pct)
    if t.empty:
        st.info("No tooling-type data for this scope.")
        return
    t = t[[c for c in core.V3_TYPE_COLS if c in t.columns]]
    _table_drill(ui.search_box(t, f"type_{ctx.keyns}"), 'Tooling Type', 'type',
                 f"type_{ctx.keyns}")


def render_type(ctx):
    """One selected tooling type: same page, scoped, drilling into its tools."""
    ui.entity_badge("Tooling Type:", ctx.value)

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
    ch.render_trend_block(ctx.trend, 'Tooling', ctx.keyns)

    st.markdown("<hr style='border-color:#2d3748;margin:1.75rem 0;'>", unsafe_allow_html=True)
    ui.section("Tool Detail")
    st.caption("Select a row to open that tool's report.")
    tools = _tool_table(ctx.scope, ctx.period_label, ctx.tolerance_pct)
    if tools.empty:
        st.info("No tool data for this tooling type.")
        return
    _table_drill(ui.search_box(tools, f"tt_{ctx.keyns}"), 'Tooling ID', 'tool', f"tt_{ctx.keyns}")
```

- [ ] **Step 2: Append the Part renderers**

Append to `cte_views.py`:
```python
def render_part_all(ctx):
    """Part C section 7 — Part overview. Tiles count PARTS, not tools."""
    ui.section("Summary")
    ui.summary_tiles(core.scope_summary(ctx.scope, ctx.tolerance_pct, entity_dim='Part'), "Parts")

    st.markdown("<br>", unsafe_allow_html=True)
    ui.section("Saving Opportunity & Loss by Part", size="1.1rem")
    ch.ranking_bars(ctx.scope, ['Part'], ctx.tolerance_pct, ctx.keyns)

    st.markdown("<hr style='border-color:#2d3748;margin:1.75rem 0;'>", unsafe_allow_html=True)
    ch.render_trend_block(ctx.trend, 'Part', ctx.keyns)

    st.markdown("<hr style='border-color:#2d3748;margin:1.75rem 0;'>", unsafe_allow_html=True)
    ui.section("Part Detail")
    st.caption("Select a row to open that part.")
    p = core.entity_detail_table(ctx.scope, 'Part', extra_cols=('Part Name',),
                                 period_label=ctx.period_label, tolerance_pct=ctx.tolerance_pct)
    if p.empty:
        st.info("No part data for this scope.")
        return
    p = p[[c for c in core.V3_PART_COLS if c in p.columns]]
    _table_drill(ui.search_box(p, f"part_{ctx.keyns}"), 'Part', 'part', f"part_{ctx.keyns}")


def render_part(ctx):
    """One selected part's detail report."""
    names = sorted(ctx.scope['Part Name'].dropna().unique().tolist())
    ui.entity_badge("Part:", f"{ctx.value} — {', '.join(names)}" if names else str(ctx.value))

    row = core.compute_comprehensive_row(ctx.value, ctx.scope, 'Part', ctx.period_label,
                                         tolerance_pct=ctx.tolerance_pct)
    n_tools = ctx.scope['Tooling'].nunique()

    a, b, c, d = st.columns(4)
    with a:
        st.metric("Total Tools", f"{n_tools:,}")
        if st.button("View tools →", key=f"parttools_{ctx.keyns}"):
            _drill('part_tools', None)
    _eff = row['CT Weighted Average Efficiency']
    b.metric("Cycle Time Efficiency", f"{_eff:.1f}%" if pd.notna(_eff) else "N/A")
    c.metric("Saving Opportunity", f"${row['Financial Gain']:,.0f}")
    d.metric("Loss", f"${row['Financial Loss']:,.0f}")

    e, f, g = st.columns(3)
    e.metric("Fast Shots", f"{row['Fast Shots (%)']:.1f}%")
    f.metric("Within Shots", f"{row['Within Shots (%)']:.1f}%")
    g.metric("Slow Shots", f"{row['Slow Shots (%)']:.1f}%")

    st.markdown("<hr style='border-color:#2d3748;margin:1.75rem 0;'>", unsafe_allow_html=True)
    ch.render_trend_block(ctx.trend, 'Tooling', ctx.keyns)


def render_part_tools(ctx):
    """Part C section 7.1 — the list of tools making the selected part."""
    ui.section("Tools Making This Part")
    st.caption("Select a row to open that tool's report.")
    tools = _tool_table(ctx.scope, ctx.period_label, ctx.tolerance_pct)
    if tools.empty:
        st.info("No tools found for this part.")
        return
    _table_drill(ui.search_box(tools, f"pt_{ctx.keyns}"), 'Tooling ID', 'tool', f"pt_{ctx.keyns}")


RENDERERS = {
    'global': render_scope_overview,
    'region': render_scope_overview,
    'country': render_scope_overview,
    'supplier': render_supplier,
    'type_all': render_type_all,
    'type': render_type,
    'part_all': render_part_all,
    'part': render_part,
    'part_tools': render_part_tools,
    'tool': render_tool,
}
```

- [ ] **Step 3: Verify every level has a renderer**

```bash
python3 -c "
import cte_nav as nav, cte_views as v
missing = set(nav.LEVELS) - set(v.RENDERERS)
print('missing renderers:', missing)
assert not missing
print('all', len(v.RENDERERS), 'levels covered')
"
```
Expected: `missing renderers: set()` then `all 10 levels covered`.

- [ ] **Step 4: Commit**

```bash
git add cte_views.py
git commit -m "feat: v3 tooling type and part views"
```

---

### Task 13: Rewrite the entry point

**Files:**
- Modify: `Cycle-Time-Efficiency-v3.py` (full rewrite — the old 2-tab structure is retired)

**Interfaces:**
- Consumes: everything built in Tasks 2–12.

- [ ] **Step 1: Replace the whole file**

`Cycle-Time-Efficiency-v3.py`:
```python
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
    "Tooling Type", "Product", "Part", "Tooling",
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

period_label = f"{pd.to_datetime(start_date).date()} to {pd.to_datetime(end_date).date()}"

# ==========================================================================
# HEADER
# ==========================================================================
st.markdown('<div class="dash-header">Cycle Time Efficiency</div>', unsafe_allow_html=True)
_fast_thr, _slow_thr = 100 + tolerance_pct, 100 - tolerance_pct
st.markdown(
    f'<div class="dash-sub">'
    f'Fast (Gain): &gt;{_fast_thr:g}% CT Efficiency &nbsp;|&nbsp; '
    f'Within (Neutral): {_slow_thr:g}%–{_fast_thr:g}% CT Efficiency &nbsp;|&nbsp; '
    f'Slow (Loss): &lt;{_slow_thr:g}% CT Efficiency &nbsp;|&nbsp; '
    f'Tolerance: ±{tolerance_pct:g}%</div>',
    unsafe_allow_html=True,
)

_active = {k: v for k, v in master_selections.items() if v}
_chip_html = "".join(
    f'<span style="background:#1e293b;border:1px solid #38bdf8;border-radius:6px;'
    f'padding:3px 12px;font-size:.85rem;color:#e2e8f0;white-space:nowrap;">'
    f'<b>{k}:</b> {", ".join(v)}</span> ' for k, v in _active.items())
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
    _cols = st.columns([1, 1, 1, 3])
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
```

- [ ] **Step 2: Byte-compile the whole app to catch syntax errors before launching**

```bash
python3 -m py_compile Cycle-Time-Efficiency-v3.py cte_core.py cte_nav.py cte_ui.py cte_charts.py cte_views.py && echo "compiles clean"
```
Expected: `compiles clean`.

- [ ] **Step 3: Run the whole test suite one more time**

```bash
python3 -m pytest tests/ -v
```
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add Cycle-Time-Efficiency-v3.py
git commit -m "feat: v3 entry point with 5-level drill-down navigation"
```

---

### Task 14: End-to-end verification in the browser

No claim of "it works" without seeing it. This task walks the full drill path and both cross-cutting views.

**Files:** none (verification only, plus any fixes it surfaces).

- [ ] **Step 1: Confirm the launch config**

```bash
cat .claude/launch.json
```
Expected: the existing `cte-dashboard` configuration already runs `Cycle-Time-Efficiency-v3.py` on port 8501 — no edit needed. Only change it if that is not what you see.

- [ ] **Step 2: Start the app with `preview_start` (never `Bash`) and check the console**

Use `mcp__Claude_Browser__preview_start` with `{name: "cte-dashboard"}`, then `preview_logs` (level `error`) and `read_console_messages` (onlyErrors). Expected: no tracebacks, no `KeyError`, no Streamlit `DuplicateWidgetID`.

- [ ] **Step 3: Walk the geography drill path**

With `read_page` / `computer`:
1. Global Overview loads: six summary tiles, four region pies (APAC, Europe, North America, LATAM), the ranking pair, both trend graphs, the supplier table.
2. Click a supplier row → breadcrumb reads `Global › <supplier>`; the supplier page shows one pie, tool rankings, both trends, the tool table.
3. Click a tool row → the tool report shows Supplier/Plant/Region/Country, ACT, WACT, efficiency, the three shot percentages, saving/loss, and both trend graphs.
4. Click the `Global` crumb → returns to the overview.
5. Repeat via Region → Country → Supplier → Tool, confirming each level's pies use the child dimension (Region page → country pies; Country page → supplier pies).

Fix any error found, then re-check from Step 2.

- [ ] **Step 4: Verify the cross-cutting views and the multi-part dropdown**

1. Tooling Type tab → type table → a type → its tools → a tool.
2. Part tab → part table → a part → "View tools →" → tool list → a tool.
3. Find a multi-part tool (its report shows a `Parts (2)` or `Parts (3)` expander) and open the expander.
4. Toggle Month-to-Month ↔ Quarter-to-Quarter on both trend graphs at two different levels; confirm labels read `Q2 2026` style in quarter mode and no data labels overlap illegibly.

- [ ] **Step 5: Verify the settings**

1. Move the tolerance slider to 10% → tile counts and pie splits change (more Within).
2. Switch Time Range to `Last Quarter` → the Date Range chip reads `2026-04-01 to 2026-06-30`; both trend graphs still show full history (unchanged).
3. Change the labor rate to 80 → saving/loss dollars scale, efficiency percentages do not.
4. Apply a `Country` master filter → the chip appears and the scope narrows.

- [ ] **Step 6: Capture a screenshot of the Global Overview and the tool report**

`computer {action: "screenshot"}` at both pages, to share as proof.

- [ ] **Step 7: Commit any fixes**

```bash
git add -A
git commit -m "fix: issues found during v3 end-to-end verification"
```

---

## Reuse Ledger (what the plan promised to keep)

**Reused verbatim from `cte_core.py` — no signature or formula change:**
`calc_weighted_eff`, `apply_tolerance`, `apply_financials`, `performance_status_from_eff`, `compute_comprehensive_row`, `generate_ranking_table_data`, `entity_efficiency`, `fast_within_slow_summary`, `act_weighted_deviation_trend` (Trend Graph 1 at every level), `format_hm`, `detail_col_config`, `common_ranking_col_config`, `COMPREHENSIVE_TOOLING_COLS`, `REPORT_CARD_TOOLING_COLS`.

**Reused via a new group-by caller (math untouched, grouping is new):**
`act_weighted_deviation_trend` is called with a per-level `trend_dim` (Supplier for Global/Region/Country; Tooling Type for the type overview; Part for the part overview; Tooling for supplier/type/part/tool pages). `generate_ranking_table_data` is called through `ranking_by_financial`, which only re-sorts. `compute_comprehensive_row` is called through `entity_detail_table` for Supplier, Tooling, Tooling Type and Part.

**Genuinely new in `cte_core.py`:**
`PLANT_META`, `ensure_geo_columns`, `TIME_RANGE_PRESETS`, `resolve_time_range`, `ct_split_shot_trend`, `ct_split_summary`, `scope_summary`, `ranking_by_financial`, `entity_detail_table`, the four `V3_*_COLS` constants, and the multi-part branch in `load_base_data`.

**Retired:** the `Executive Summary` / `Full Ranking and Details` two-tab structure, `dimension_card`, `_trend_snippet`, `_weekly_efficiency_trend`, `render_dimension_view`, `render_report_card`, and the `Last 90 Days` preset.

## Known limitation carried forward

`compute_comprehensive_row` returns `group['Part'].iloc[0]` for its `Part` / `Part Name` fields. With multi-part tools that shows only the first part. Every v3 surface that needs the full list uses `entity_detail_table(extra_cols=...)` or reads `scope['Part'].unique()` directly (the tool report's dropdown), so no v3 view relies on that field — but do not add one that does without fixing the underlying row helper.
