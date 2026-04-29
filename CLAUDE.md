# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Aircraft engine condition monitoring system for airline operations (S7 Airlines). The project has two active parts and one legacy part:

- **`pythonlib/`** — `enginewash` Python library: core wash-effect calculation logic (active)
- **`dashboard/`** — Dash/Plotly prototype dashboard (active)
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

## Dash Dashboard (`dashboard/`)

Prototype UI built with Dash + Plotly + Bootstrap. Loads data from parquet files at startup (no live DB connection needed).

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

> **Legacy:** The R Shiny app is no longer under active development. The Python library and Dash dashboard are the active codebase.

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
