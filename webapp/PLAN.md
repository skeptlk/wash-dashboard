# Reflex ECM Web App — Implementation Plan

## Context

The Dash prototype at `dashboard/app.py` (747 lines, 2 tabs) works but is a single-file prototype. We want a polished, multi-page UI with proper routing and a path to support multiple aircraft types (Boeing 737 now; A320-200, Embraer 170 later). Solution: a new Reflex app at `webapp/`, keeping the existing `dashboard/` intact as a reference until parity is reached. All wash calculations go through the `enginewash` library; the Reflex app is a thin UI layer. A new Long-Term Degradation page is added.

## Goal

Three pages under one Reflex app:

1. **Long-Term Degradation** (NEW) — EGTHDM linear trend over each engine's lifespan, ranked to surface fast vs slow degraders.
2. **Wash Analysis** — port of current Dash Analysis tab.
3. **Wash Schedule** — port of current Dash Schedule tab (Gantt).

Every page has shared selectors: aircraft type, engine id(s), date range.

## File / Folder Structure (`webapp/`)

```
webapp/
  rxconfig.py                     # app_name="webapp"
  requirements.txt                # reflex, pandas, plotly, pyarrow, numpy
  PLAN.md                         # this file
  tests/
    test_trends.py                # 11 tests for the trend fitter
  webapp/
    __init__.py                   # adds ../../pythonlib to sys.path
    webapp.py                     # rx.App() + page registration
    trends.py                     # LifetimeTrend, compute_lifetime_trend, rank_engines_by_trend
                                  #   (kept in webapp for now; will move into enginewash later)
    data/
      registry.py                 # AIRCRAFT_DATA_REGISTRY dict (URLs per type)
      loader.py                   # loads all aircraft data at import → LOADED dict
      derived.py                  # flights_for(), maint_for(), PARAMETER_BY_NAME
      aircraft_registry.py        # AIRCRAFT_REG tail-number lookup
    state/
      base.py                     # GlobalState: aircraft_type, start/end date
      degradation.py              # DegradationState
      analysis.py                 # AnalysisState (Phase 2)
      schedule.py                 # ScheduleState (Phase 3)
    components/
      shell.py                    # page_shell() — sticky top header + tab nav
      selectors.py                # aircraft_type_selector, date_range_picker
      plot.py                     # rx.plotly wrappers + ported _build_chart (Phase 2)
    pages/
      degradation.py              # @ /
      analysis.py                 # @ /analysis  (Phase 2)
      schedule.py                 # @ /schedule  (Phase 3)
```

## Trends Module — `webapp/webapp/trends.py`

Lives in the webapp while the API is still shifting; will move into `enginewash` once the lifetime-trend feature stabilizes.

- `@dataclass(frozen=True) LifetimeTrend`: `engine_id, parameter_name, slope_per_day, intercept, r_squared, n_points, start_datetime, end_datetime, fitted_endpoints: tuple[PlotPoint, ...]`.
- `compute_lifetime_trend(flights, parameter, smooth_window=None) -> LifetimeTrend` — least-squares OLS on `(days_from_start, value)`. Optional centered smoothing first. Pure numpy.
- `rank_engines_by_trend(trends, direction) -> list[LifetimeTrend]` — sorts so worst degrader is first (sign respects `TrendDirection.DOWN`/`UP`); NaN slopes pushed to the end.

## State Design

- **`GlobalState`** (`base.py`): `aircraft_types: list[str]`, `start_date / end_date: str`. Computed var `aircraft_options`; engine lists and labels are managed by each page. Setters re-default the date range when aircraft types change.
- **`DegradationState`** (`state/degradation.py`): `selected_parameter: str = "EGTHDM"`, `selected_engine_id: str`, `ranked_rows: list[dict]`, `chart_figure: go.Figure`. Event handler `recompute()` loops engines in the current aircraft type, calls `compute_lifetime_trend`, sorts via `rank_engines_by_trend`, auto-selects the worst degrader so the chart populates immediately.
- **`AnalysisState`** (Phase 2): mirrors current Dash controls — `selected_param`, `selected_engine_ids`, smoothing/detection params, `loe_threshold`. Handler `run_analysis()` builds `WashConfig`, runs `WashCalculator.process_all`, stores per-engine figures + summary + violin.
- **`ScheduleState`** (Phase 3): ATA filter, engine filter, `gantt_figure`. Driven by a ported pure helper of `dashboard/schedule.py:_prepare`.

Pages access `GlobalState` via `self.get_state(GlobalState)` so shared selectors propagate naturally.

## Data Layer

- `data/registry.py` holds `AIRCRAFT_DATA_REGISTRY` — dict `aircraft_type → {onwing, maintenance, takeoff, cruise}` URLs. Only `"B737"` populated initially; slots reserved for `"A320"`, `"E170"`.
- `data/loader.py` runs at import: iterates the registry, loads frames, builds `LOADED: dict[str, AircraftBundle]` (onwing/maintenance/takeoff/cruise + derived `wash_maint`, `engine_labels`, `available_engines`, `date_min`, `date_max`). Module-level singleton — same pattern as the current Dash app at `dashboard/app.py:36-100`. The engine-family map is used locally to sort engines during loading.
- `data/derived.py` exposes `flights_for(bundle, engine_id, parameter, start=None, end=None) -> list[FlightRecord]` and `maint_for(bundle, engine_id) -> list[MaintenanceRecord]`, and `PARAMETER_BY_NAME` mapping name strings to `WashParameter` objects.

## Pages

### Page 1 — Long-Term Degradation (`/`)

- Controls: aircraft type, date range, parameter (default EGTHDM), "Recompute".
- Action: `DegradationState.recompute()` → for each engine in the type, build flights, call `compute_lifetime_trend(smooth_window=30)`, sort via `rank_engines_by_trend`. Auto-selects the worst degrader and updates the chart.
- Visuals: ranked `rx.table` (engine label, slope/day, r², n, start, end) with clickable rows + `rx.plotly` scatter + OLS-line chart for the selected engine; slope and r² shown in the chart title.

### Page 2 — Wash Analysis (`/analysis`) — *Phase 2*

- Controls: aircraft type, engine multi-select, date range, parameter, smoothing window, second-smooth window, LoE threshold, before/after window days.
- Action: `AnalysisState.run_analysis()` runs `WashCalculator.process_all` over selected engines.
- Visuals: one `rx.plotly` per engine, summary table, ATA-code violin plot.
- Port `_build_chart` from `dashboard/app.py:343-450` into `components/plot.py` as a pure function.

### Page 3 — Wash Schedule (`/schedule`) — *Phase 3*

- Controls: aircraft type, date range, ATA codes, engines.
- Action: `ScheduleState.rebuild_gantt()` calls ported `_prepare` (from `dashboard/schedule.py:24`) lifted into `components/schedule_fig.py`.
- Visual: single Plotly Gantt.

## Shared Components

- `shell.page_shell(active_route, *children)` — sticky 60px top header with the ECM brand on the left, three tab links across the middle (active tab gets accent underline + color), color-mode toggle on the right. Content area is padded and capped to a max width, centered.
- `selectors.aircraft_type_selector()`, `selectors.date_range_picker()` — Radix-based (`rx.select`, `rx.input(type="date")`), bound to `GlobalState` setters so they work on every page.

## Phasing

### Phase 1 — Skeleton + Page 1 *(done)*

1. Add `webapp/webapp/trends.py` + `webapp/tests/test_trends.py`.
2. Scaffold `webapp/` (`reflex init`): `rxconfig.py`, `requirements.txt`.
3. `data/registry.py`, `data/loader.py`, `data/derived.py` for B737.
4. `state/base.py` + `components/shell.py` (top tab header) + `components/selectors.py`.
5. `pages/degradation.py` + `state/degradation.py` end-to-end.
6. Stub `/analysis` and `/schedule`.
7. Update `CLAUDE.md` with the `webapp/` section; mark `dashboard/` as reference.

### Phase 2 — Wash Analysis

- Port `_build_chart` and analysis aggregation into pure helpers.
- Implement `AnalysisState`, page UI, summary table, ATA-code violin.
- Engine multi-select component.

### Phase 3 — Wash Schedule

- Port `dashboard/schedule.py:_prepare` + Gantt builder into pure helpers.
- Implement `ScheduleState` and the schedule page UI.

### Phase 4 — Polish & cleanup

- Once Phase 2 and 3 are stable, move `webapp/webapp/trends.py` into `enginewash/trends.py` and update the import in `state/degradation.py`.
- Retire `dashboard/`.

## Verification (Phase 1)

- Install: `cd webapp && pip install -r requirements.txt` (the editable `enginewash` lib is picked up via `sys.path` insert in `webapp/webapp/__init__.py`).
- Run: `reflex run` → open `http://localhost:3000/`.
  - Top header shows three tabs; current route's tab has an accent underline.
  - Aircraft type defaults to "B737"; engine list and date range populate from `LOADED["B737"]`.
  - "Recompute" fills the ranked table; worst degrader first (sign-aware for `TrendDirection.UP` vs `DOWN`).
  - Clicking a row updates the Plotly chart (scatter + OLS line, slope/r² in title).
- Tests: `python -m pytest tests/` from `webapp/` (11 trend tests pass); `python -m pytest tests/` from `pythonlib/` (44 lib tests pass).

## Critical Files

- `webapp/webapp/trends.py`
- `webapp/webapp/data/loader.py` (mirrors `dashboard/app.py:36-100`)
- `webapp/webapp/data/registry.py` (add new aircraft types here)
- `webapp/webapp/state/base.py` (`GlobalState`)
- `webapp/webapp/state/degradation.py`
- `webapp/webapp/components/shell.py` (top tab header + content layout)
- `webapp/webapp/pages/degradation.py`
- `webapp/tests/test_trends.py`
