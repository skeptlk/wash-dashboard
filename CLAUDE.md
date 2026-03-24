# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Application

```r
# From R console or RStudio
shiny::runApp('.')

# From terminal
R -e "shiny::runApp('.')"
```

The app reads `./config/config.ini` for PostgreSQL connection details. A running database connection is required.

## Architecture

This is an R Shiny dashboard for aircraft engine condition monitoring, built for airline operations (S7 Airlines). It uses the **Shiny Module Pattern** throughout.

**Tech stack:**
- UI: `bs4Dash` (Bootstrap 4 dashboard), `shinyWidgets`, `shinyjs`
- Database: PostgreSQL via `pool` + `DBI` + `RPostgreSQL` + `dbplyr`
- Visualization: `highcharter` (primary), `ggplot2`, `reactable`
- Data: `dplyr`, `data.table`, `tidyr`
- Auth: `shinymanager` (hardcoded credentials in `app.R`)

**Key schemas:** `ecmapp` (main app data, presets, parameters), `s7_mdb` (smoothed engine data), `utair` (Utair-specific data)

## Project Structure

- **`app.R`** — Entry point. Loads packages, reads config, creates DB pool, sets up auth, defines UI (sidebar tabs), and registers all modules.
- **`modules/`** — All Shiny modules. Each `*_workspaceMod.R` is a full tab: UI + server logic.
- **`utils/visualization/`** — Reusable `highcharter`-based chart functions, one file per workspace.
- **`utils/calculator/`** — `CalculatorHistory` R6 class for engine wash event time-series analysis.
- **`research/`** — Experimental/development scripts, not used by the app.
- **`config/config.ini`** — Database credentials (three environments: S3, AMOS test, ECM core UAT).

## Modules Overview

| Module file | Tab | Purpose |
|---|---|---|
| `enginetrends_workspaceMod.R` | Engine Trends | Parameter trending over time, multi-engine, smoothing, baseline comparison |
| `enginewash_workspaceMod.R` | Engine Wash | Pre/post wash efficiency analysis using `CalculatorHistory` |
| `fleetreports_workspaceMod.R` | Fleet Reports | Aggregate fleet reporting |
| `maintenance_workspaceMod.R` | Maintenance | Maintenance event tracking and history |
| `fleetsummary_workspaceMod.R` | Fleet Summary | Fleet-wide status overview |
| `constructor_workspaceMod.R` | Constructor | Report template/preset builder (largest module, ~55k lines) |
| `dataquality_workspaceMod.R` | Data Quality | Data validation and quality monitoring |
| `useroptions_workspaceMod.R` | User Options | Per-user preferences stored as JSON in DB |
| `alerts_workspaceMod.R` | Alerts | Alert management (currently disabled in UI) |
| `headerMod.R` | — | Header navigation bar |

## Key Patterns

- **Module registration:** Each module is called in `app.R` server via `<name>Server(id, pool, ...)` and UI via `<name>UI(id)`.
- **Database access:** The `pool` object is passed to every module. Queries use `dbplyr` (dplyr-to-SQL translation) or raw SQL via `DBI::dbGetQuery()`.
- **User defaults:** Stored as JSON in the database, retrieved and parsed per session.
- **Reactive state:** Most inter-module communication uses `reactiveValues` passed as arguments.
