# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Aircraft engine condition monitoring system for airline operations (S7 Airlines). The project has three active parts and one legacy part:

- **`pythonlib/`** — `enginewash` Python library: core wash-effect calculation logic (active)
- **`webapp/`** — Reflex web app: the polished multi-page UI being built out (active, primary target)
- **`dashboard/`** — Dash/Plotly prototype dashboard (active reference; will be retired once `webapp/` reaches parity)
- **R Shiny app** (`app.R`, `modules/`, `utils/`) — legacy production app, not under active development

---

## Python Library (`pythonlib/`)

### Install

```bash
cd pythonlib
pip install -e .
# With dev dependencies (pytest):
pip install -e ".[dev]"
```

### Run tests

```bash
cd pythonlib
python -m pytest tests/ -v
```

### Structure

- **`enginewash/models.py`** — `FlightRecord`, `MaintenanceRecord`, `WashEvent`, `WashParameter`, `WashConfig`; preset parameters `GWFM`, `DEGT`, `EGTHDM`
- **`enginewash/smoothing.py`** — Centered moving average
- **`enginewash/detection.py`** — Pre/post-wash delta calculation and loss-of-effectiveness detection
- **`enginewash/calculator.py`** — `WashCalculator`: top-level entry point; `process()` / `process_all()`
- **`enginewash/__init__.py`** — Public API exports

### Processing pipeline

1. Bind wash events to first flight after maintenance date
2. Segment time series per engine via `event_cum = cumsum(event)`
3. Smooth within each segment (centered moving average, default window = 30 flights)
4. Compute pre/post-wash deltas from worst/best of last/first N observations
5. Detect first flight where smoothed value returns to threshold zone relative to pre-wash level
6. Build event table: one row per wash with delta, loss-of-effectiveness date, optional utilization metrics

### Dependencies

Runtime: `pandas`, `numpy` only. No DB access — callers supply data.

---

## Reflex Web App (`webapp/`)

Primary UI target. Multi-page Reflex app with three pages: Long-Term Degradation, Wash Analysis, Wash Schedule. All calculation goes through the `enginewash` library — the app is a thin UI layer.

### Run

```bash
cd webapp
pip install -r requirements.txt          # installs reflex, pandas, plotly, pyarrow, numpy
# `enginewash` is imported from `../pythonlib` via sys.path insert in webapp/webapp/__init__.py
reflex run                                # http://localhost:3000
```

### Structure

```
webapp/
  rxconfig.py                       # app_name="webapp"
  requirements.txt
  webapp/
    webapp.py                       # rx.App() — registers pages by route
    trends.py                       # Lifetime linear-trend calc (will move to enginewash later)
    data/
      registry.py                   # AIRCRAFT_DATA_REGISTRY: aircraft_type → dataset URLs
      loader.py                     # loads all aircraft data once at import → LOADED dict
      derived.py                    # flights_for(), maint_for(), PARAMETER_BY_NAME
      aircraft_registry.py          # AIRCRAFT_REG (tail-number lookup)
    state/
      base.py                       # GlobalState (aircraft_type, date range)
      degradation.py                # DegradationState
    components/
      shell.py                      # page_shell() — sidebar nav + content area
      selectors.py                  # aircraft_type_selector, date_range_picker
    pages/
      degradation.py                # @ /
      analysis.py                   # @ /analysis  (Phase 2 stub)
      schedule.py                   # @ /schedule  (Phase 3 stub)
```

### Adding a new aircraft type

Add an entry to `AIRCRAFT_DATA_REGISTRY` in `webapp/webapp/data/registry.py` with URLs for `onwing`, `maintenance`, `takeoff`, `cruise`. Restart the app — the loader picks it up automatically and the type appears in every page's selector.

### EGT data labeling & dataset versioning (DVC)

The EGT page (`/egt`) doubles as a labeling tool. With **Label mode** on, drag-select a
span on the chart (or type the start/end dates), choose `failure = 0/1`, and **Apply** to
record a whole-engine label range. **Export & version** bakes all labels into a curated
dataset and updates the DVC pointers.

- **`webapp/webapp/data/labels.py`** — overlay store + curated export. Writes two parquet
  files under the repo-root `data/` dir:
  - `egt_manual_labels.parquet` — overlay of manual corrections vs. the auto baseline
    (`engine_id, start_datetime, end_datetime, failure_value, labeled_by, labeled_at, note`).
    Labeling is **idempotent per flight**: a flight already at the requested value (from
    auto or a prior change) is left alone, and the overlay is rebuilt as a minimal,
    non-overlapping set of correction ranges — re-labeling never appends duplicates, and
    reverting a flight to its auto value removes it from the overlay.
  - `egt_indication_curated.parquet` — copy of the auto-labels frame plus a `failure_value`
    column (= `failure_value_auto`, overridden per manual range, latest label wins).
- The raw auto-labels frame is reused from `egt_indication.py:RAW_AUTO_LABELS` (no re-download).
- Both files are **DVC-tracked**; the `*.dvc` pointers are committed to git, the parquet
  files are gitignored. The web app runs `dvc add` on export but never commits or pushes.

**`labels.py` public API** (all pure pandas, overlay cached in-memory + written through):
- `add_label(engine_id, start, end, failure_value, labeled_by="", note="") -> int` —
  label every flight reading of the engine in the **exact** closed interval `[start, end]`
  (timestamp-precise, no day snapping). Idempotent per flight; returns the count of flights
  whose effective label changed (`0` = no-op). Rebuilds the engine's overlay rows as
  minimal diff-vs-auto ranges (range bounds are actual flight timestamps).
- `delete_label(row_id)` — drop one correction range (reverts those flights to auto).
- `labels_for(engine_id) -> list[dict]` — correction ranges for the UI list.
- `manual_spans_for(engine_id, start, end) -> [(start, end, value)]` — for chart shading.
- `export_curated() -> {rows, overridden, path}` / `dvc_add() -> (ok, output)`.

**EGT page controls & state** (`pages/egt.py` `_labeling_panel()`, `state/egt.py:EgtState`):
- `label_mode` switch toggles the labeling panel and the chart's plotly `dragmode`
  (`select` ↔ `zoom`); rebuilds the chart so the mode change takes effect.
- `on_plot_selected(points)` — box-select handler; takes min/max `x` of the selected
  points and fills `label_start` / `label_end` at full timestamp precision (the inputs are
  `datetime-local`, `step=1`). `on_relayout` carries no args in this Reflex version, so the
  typed inputs are the reliable fallback.
- `set_label_value(value)` accepts the segmented control's `str | list[str]` → `0/1`.
- `apply_label` (calls `add_label`, reports changed-count or "no change"),
  `delete_label(row_id)`, `export_dataset` (runs `export_curated` then `dvc_add`, sets
  `export_status` with the `git commit` / `dvc push` reminder).
- Chart overlay: auto failure spans stay light-red; manual corrections are drawn on top —
  green outline for `failure=0` (cleared), red outline for `failure=1`.

**Dataset version selector** (`data/versions.py`, `pages/egt.py:_version_selector()`,
`state/egt.py:EgtState`): a **Dataset version** dropdown lets you view past labeled
snapshots read-only. A "version" is a **git commit that changed
`data/egt_indication_curated.parquet.dvc`** — so a new version appears in the dropdown only
after you `git commit` the pointer (the app never commits/pushes). DVC has no auto-latest.
- `"Working (live)"` (default) = the editable view above (auto baseline + manual overlay,
  labeling panel shown).
- Any other entry = a committed snapshot: failure spans are shaded from that version's
  `failure_value` column (red outline), the labeling panel is **hidden**, and `label_mode`
  is forced off. Switch back to Working (live) to edit.
- `versions.py`: `list_versions()` (git log on the pointer, newest first),
  `failure_spans_for_version(sha, engine_id, start, end)` — loads the curated parquet at the
  git rev via `dvc.api.open(..., rev=sha)` (cached per sha), collapses `failure_value` to a
  per-flight flag, and reuses `egt_indication.merge_failure_spans` (extracted from
  `failure_spans_for`). Loading a version whose blob isn't in the local DVC cache pulls from
  the S3 remote; if that fails (e.g. the known bad write keys) the error surfaces as a red
  callout and the chart still renders its traces.

**Cross-parameter matching:** a label range matches by **exact timestamp**. EGTHDM
(takeoff phase) and DEGT/GWFM (cruise phase) have *different* `flight_datetime` per logical
flight, so each parameter's points are matched independently — every row of any parameter
whose timestamp falls in the exact interval `[start, end]` gets the label. There is no
flight-id join in this dataset, so labels are keyed to absolute time, not to a logical
flight; at the range edges, a takeoff reading and a same-day cruise reading just outside the
bounds are treated separately (pick the bounds to include the readings you intend).

**DVC remote:** `ycloud` → `s3://ecm-data/egt-indication-dvc` (same Yandex bucket as the
data, separate prefix — created automatically on first `dvc push`, no manual bucket
setup), configured in `.dvc/config`. Credentials come from `~/.aws/credentials`.

Publish a new dataset version after labeling:

```bash
cd <repo root>
git add data/*.dvc data/.gitignore   # commit the updated pointers
git commit -m "Label EGT failures: <description>"
dvc push                             # upload parquet to the bucket
```

> ⚠️ `dvc push` needs working write keys for `s3://ecm-data`. The keys currently in
> `~/.aws/credentials` fail with `SignatureDoesNotMatch` (reads work — the bucket is public
> over HTTP). Fix the keys (e.g. `yc iam access-key create`) or set them on the remote with
> `dvc remote modify --local ycloud access_key_id <id>` / `secret_access_key <secret>`
> before pushing. The local label/export flow works without this.

---

## Dash Dashboard (`dashboard/`)

Prototype UI built with Dash + Plotly + Bootstrap. Loads data from parquet files at startup (no live DB connection needed). **Status:** active reference while `webapp/` is being built; will be removed once `webapp/` reaches parity.

### Run

```bash
cd dashboard
pip install -r requirements.txt
python app.py
```

### Structure

- **`app.py`** — Entry point; data loading, layout, callbacks
- **`schedule.py`** — Scheduling/flight schedule data helpers
- **`aircraft_registry.py`** — Static aircraft registration data
- **`requirements.txt`** — `dash`, `dash-bootstrap-components`, `plotly`, `pandas`, `pyarrow`

The dashboard imports `enginewash` directly from `../pythonlib` via a `sys.path` insert.

---

## Legacy R Shiny App

> **Legacy:** The R Shiny app is no longer under active development. The Python library, Reflex web app, and Dash dashboard are the active codebase.

### Running (if needed)

```r
# From R console or RStudio
shiny::runApp('.')

# From terminal
R -e "shiny::runApp('.')"
```

Requires `./config/config.ini` with PostgreSQL connection details.

### Tech stack

- UI: `bs4Dash`, `shinyWidgets`, `shinyjs`
- Database: PostgreSQL via `pool` + `DBI` + `RPostgreSQL` + `dbplyr`
- Visualization: `highcharter`, `ggplot2`, `reactable`
- Auth: `shinymanager` (hardcoded credentials in `app.R`)

**Key schemas:** `ecmapp`, `s7_mdb`, `utair`

### Structure

- **`app.R`** — Entry point; DB pool, auth, UI, module registration
- **`modules/`** — Shiny modules (`*_workspaceMod.R`), one per tab
- **`utils/visualization/`** — `highcharter`-based chart functions
- **`utils/calculator/`** — `CalculatorHistory` R6 class
- **`research/`** — Experimental scripts, not used by app

### Modules

| File | Tab | Purpose |
|---|---|---|
| `enginetrends_workspaceMod.R` | Engine Trends | Parameter trending, multi-engine, smoothing, baseline |
| `enginewash_workspaceMod.R` | Engine Wash | Pre/post wash efficiency using `CalculatorHistory` |
| `fleetreports_workspaceMod.R` | Fleet Reports | Aggregate fleet reporting |
| `maintenance_workspaceMod.R` | Maintenance | Maintenance event tracking |
| `fleetsummary_workspaceMod.R` | Fleet Summary | Fleet-wide status overview |
| `constructor_workspaceMod.R` | Constructor | Report template/preset builder (~55k lines) |
| `dataquality_workspaceMod.R` | Data Quality | Data validation and quality monitoring |
| `useroptions_workspaceMod.R` | User Options | Per-user preferences stored as JSON in DB |
| `alerts_workspaceMod.R` | Alerts | Alert management (disabled in UI) |
| `headerMod.R` | — | Header navigation bar |
