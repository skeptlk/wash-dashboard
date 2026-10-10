# AGENTS.md

Guidance for coding agents working in this repository.

## Project overview

Aircraft engine condition monitoring system for airline operations (S7 Airlines).

- **`webapp/`** — primary dashboard, built with Reflex and Plotly. Used to view
  engine trends, installation/removal and replacement history, long-term
  degradation, wash effects, maintenance history, and model predictions.
- **`pythonlib/`** — `enginewash`, the Python wash-effect calculation library.
  Also contains utilization helpers, plot-data builders, and EGT failure
  prediction functions used by the dashboard.
- **`egt-failure-dataset/`** — nested DVC repository for the current EGT failure
  baseline, manual corrections, and exported labeled dataset. Its DVC pointers
  are tracked in the outer Git repository.
- **`data/`** — earlier DVC-tracked EGT indication datasets, retained separately
  from the current flight-level dataset.
- **`legacy/`** — archived R Shiny application, RStudio project, configuration,
  modules, utilities, and R research scripts. Not under active development.
- **Root notebooks** — Python usage and exploration examples.

The former `dashboard/` Dash prototype has been removed. Historical references
in `webapp/PLAN.md` and source comments describe its migration, not an active app.

## Working conventions

- Target `webapp/` for dashboard work and `pythonlib/` for reusable wash-effect
  calculations. Do not duplicate wash calculations in page or state code.
- The web app owns data loading, UI state, and presentation. Lifetime and
  utilization trend calculations currently live in `webapp/webapp/trends.py`.
- The calculation library accepts caller-supplied data; keep database and
  dataset access outside it.
- Preserve unrelated working-tree changes. Keep legacy changes scoped to
  explicit requests involving the archived R app.
- Validate with relevant local tests. Report actual checks and distinguish
  unit-test success from a frontend build or live end-to-end check.

## Primary dashboard (`webapp/`)

### Setup and run

Use Python 3.12 or newer. From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r webapp/requirements.txt
cd webapp
reflex run
```

Development serves the UI at `http://localhost:3000`. The package initializer
adds the sibling `pythonlib/` to `sys.path`, exposing `enginewash` without a
separate install. Set `APP_PASSWORD` in the server environment for shared login;
see `webapp/README.md` for authentication and deployment behavior.

Aircraft data loads at startup from the URLs in `webapp/webapp/data/registry.py`.
The EGT baseline must also be available locally or through its DVC remote:

```bash
cd egt-failure-dataset   # from the repository root
dvc pull
```

### Current pages

| Route | Page | Purpose |
| --- | --- | --- |
| `/` | Degradation | Engine parameter trends, fleet rankings, lifetime and utilization-based degradation |
| `/analysis` | Wash Analysis | Before/after wash effects, per-engine charts, and effectiveness summaries |
| `/schedule` | Wash Schedule | Wash/maintenance timeline with aircraft and ATA filters |
| `/egt` | EGT Indication | B737 parameter traces, installation/removal and maintenance markers, failure predictions, and dataset labeling |
| `/constructor` | Constructor | DuckDB-backed parameter trends for B737, A320 and E170 with engine installation/removal markers |
| `/login` | Sign In | Shared dashboard authentication |

These pages are implemented; Wash Analysis and Wash Schedule are not stubs.
Replacement history is shown through installation/removal markers in the engine
views rather than a separate route. The EGT view combines stored failure labels
with configurable heuristic predictions from `enginewash`.

### Code map

Paths below are relative to `webapp/`:

- `webapp/webapp.py` — creates `rx.App`, registers routes and auth middleware.
- `webapp/pages/` — page layouts: degradation, analysis, schedule, EGT, login.
- `webapp/state/` — corresponding Reflex states; `base.py` provides shared
  aircraft/date preferences and `auth.py` manages shared login.
- `webapp/auth_middleware.py` — backend authorization for dashboard events.
- `webapp/components/` — shared header/navigation, selectors, and Plotly figure
  builders (`analysis_fig.py`, `schedule_fig.py`, `egt_fig.py`).
- `webapp/trends.py` — lifetime, grouped, and utilization trend calculations.
- `webapp/data/registry.py` — aircraft-type source registry (B737, A320, E170).
- `webapp/data/loader.py` — startup loading into `LOADED` aircraft bundles.
- `webapp/data/derived.py` — flight, maintenance, installation/removal helpers
  and parameter lookup.
- `webapp/data/aircraft_registry.py` — tail-number lookup.
- `webapp/data/egt_params.py` — chart parameter catalog, keyed by `NAME@PHASE`.
- `webapp/data/egt_indication.py`, `labels.py`, `versions.py` — EGT baseline,
  manual corrections/export, and historical dataset loading.
- `tests/` — local fixture tests for authentication, trends, EGT labels,
  parameter selection, and URL handling.

Runtime dependencies are pinned in `requirements.txt`; retain both
`reflex.lock/package.json` and `reflex.lock/bun.lock` when updating Reflex.

Constructor reads through the separate `wash-quack.service`, which owns
`data/flights.duckdb` (override with `FLIGHT_DATABASE_PATH`). Its default backend
is Quack; `FLIGHT_DATABASE_MODE=file` is an explicit offline-only option.
From the repository root, build it with
`PYTHONPATH=webapp python -m webapp.data.migrate_flights`; see `webapp/README.md`
for offline sources and explicit replacement, and `deploy/README.md` for systemd
installation, tokens, SSH access and remote transactions. `webapp/data/flight_db.py`
owns read-only queries; `quack.py` owns connections and the server-side transaction
helper; `quack_server.py` owns the listener lifecycle. Stop Quack before replacing
or directly opening its database file. The migration preserves every source report, including null
engine IDs, in one wide `reports` table. Other pages still use the Parquet loader.

### Adding an aircraft type

Add an entry to `AIRCRAFT_DATA_REGISTRY` in
`webapp/webapp/data/registry.py`. Required sources are `onwing`, `maintenance`,
and `takeoff`; `cruise` and `utilization` are optional. Restart to load the new
type. General dashboard selectors use the registry; the EGT indication workflow
is currently B737-specific.

### EGT labeling and dataset versions

The active files are under `egt-failure-dataset/data/`:

- `egt_failure_baseline.parquet` — immutable migrated flight-level baseline,
  loaded as `RAW_BASELINE_LABELS`.
- `egt_failure_manual_labels.parquet` — auditable manual correction ranges.
- `egt_failure_dataset.parquet` — baseline with exported corrections applied.

The label schema includes `aircraft_id`, `engine_position`, `engine_id`,
`flight_phase`, `flight_datetime`, and binary `failure_value`. Measurement values
still come from the aircraft source datasets. Preserve baseline row cardinality,
including rows with null source engine IDs, during export.

With Label mode enabled, chart selection or typed timestamps define a closed
interval `[start, end]` for an engine. `add_label` is idempotent: it returns the
number of changed observations and rebuilds minimal, non-overlapping corrections
relative to the baseline. Restoring the baseline value removes the correction.
`delete_label` removes one correction range. Bounds are exact timestamps, with
no day snapping or flight-ID join; takeoff and cruise observations can have
different timestamps for the same logical flight.

The chart parameter selector groups measurements by Takeoff/Cruise. Chart height
follows the selected row count. The enhanced EGT model uses full-history takeoff
EGTHDM and cruise DEGT before applying the visible date window.

Export writes the curated dataset and runs `dvc add` for it and the overlay in
the nested DVC repository. The app never commits or pushes. A selectable version
is a Git commit changing
`egt-failure-dataset/data/egt_failure_dataset.parquet.dvc`. Working (live) is
editable; committed snapshots are read-only and disable label mode. Version
loads use `dvc.api.open(..., rev=sha)` and surface fetch failures in the UI.

After exporting, an operator can publish a version from the repository root:

```bash
git add egt-failure-dataset/data/*.dvc egt-failure-dataset/data/.gitignore
git commit -m "Label EGT failures: <description>"
cd egt-failure-dataset
dvc push
```

The nested remote is configured in `egt-failure-dataset/.dvc/config` and points
to `s3://ecm-data/egt-failure-dataset`. Remote access requires working credentials;
do not assume old credential failures are still current. Root `data/` pointers
and the root DVC remote belong to the earlier indication dataset.

## Wash-effect library (`pythonlib/`)

### Install and test

```bash
cd pythonlib
python -m pip install -e ".[dev]"
python -m pytest tests/ -v
```

The package is named **`enginewash`**. Runtime dependencies are `pandas` and
`numpy`; callers provide data and the library has no database access.

### Code map and processing

- `enginewash/models.py` — flight, maintenance, utilization, configuration,
  result, and plot dataclasses; parameter presets `GWFM`, `DEGT`, `EGTHDM`.
- `enginewash/calculator.py` — `WashCalculator.process()`, `process_all()`,
  and `build_plot()`.
- `enginewash/smoothing.py` — centered moving averages.
- `enginewash/detection.py` — pre/post-wash deltas and loss-of-effect detection.
- `enginewash/utilization.py` — utilization lookup and elapsed cycles/hours.
- `enginewash/plot.py` — reusable wash plot data.
- `enginewash/egt_prediction.py` — basic and enhanced EGT failure heuristics.
- `enginewash/__init__.py` — public API exports.

The wash pipeline anchors maintenance to the first flight at or after its
timestamp, segments the engine series by wash events, smooths within segments,
computes pre/post reference levels, and detects the first return to the
pre-wash threshold zone. Results include parameter effects and optional
utilization metrics. See `WASH_ANALYSIS.md` for calculation details.

## Validation

With the virtual environment activated, from the repository root:

```bash
PYTHONPATH=webapp:pythonlib python -m pytest webapp/tests pythonlib/tests -q
ruff check webapp --select F,E9
git diff --check
```

Install `pytest` and `ruff` if missing. For frontend changes, also run:

```bash
cd webapp
reflex export --frontend-only --no-zip
```

Unit tests use local fixtures. Frontend export loads configured datasets and
installs frontend packages, so it requires network access.

## Archived R application (`legacy/`)

All R application and project files live together under `legacy/`:

- `app.R` — Shiny entry point, database pool, authentication, module wiring.
- `EngineConditionMonitoringWashApp.Rproj` — RStudio project.
- `config/config.ini` — legacy PostgreSQL configuration.
- `modules/` — engine trends, wash analysis, fleet reports, maintenance,
  summaries, report constructor, data quality, and user settings.
- `utils/calculator/` — original `CalculatorHistory` R6 implementations.
- `utils/visualization/` — Highcharter chart helpers.
- `research/` — R scripts and R Markdown experiments.

Run from the legacy working directory so relative module/config paths resolve:

```bash
cd legacy
R -e "shiny::runApp('.')"
```

Alternatively, open the RStudio project under `legacy/` and run
`shiny::runApp('.')`. The app requires its R packages and access to the configured
PostgreSQL database. Its stack includes Shiny/bs4Dash, shinymanager,
pool/DBI/RPostgreSQL/dbplyr, Highcharter, ggplot2, and reactable. The active Python
dashboard does not depend on this directory.
