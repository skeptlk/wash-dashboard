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
