# ECM webapp

Reflex UI for degradation, wash analysis, wash scheduling, EGT indication, and Constructor.

## Setup

Use Python 3.12 or newer. From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r webapp/requirements.txt
cd webapp
reflex run
```

Set `APP_PASSWORD` in the server environment for the shared login. The app loads
the aircraft datasets from the URLs in `webapp/data/registry.py` at startup.
EGT also needs the baseline from `../egt-failure-dataset`; see that directory's
README for DVC setup. Imports expose the sibling `pythonlib` automatically.

### Shared login

After entering the shared password, the browser keeps a signed token in
localStorage (`ew_auth_token`). It has no time limit and survives browser and
backend restarts, including Reflex session expiry. Sign out clears it and syncs
the change to other tabs. Clearing site storage, using another browser/profile,
or changing `APP_PASSWORD` requires a new login. Keep the same password across
backend workers. If unset, the test-dashboard default remains `ecm`.

The backend checks the token before every dashboard event, including report
loads, label edits/deletions, exports, and direct WebSocket calls. The initial
hydration response excludes dashboard state. Login and the framework events
needed to restore browser storage remain public; the WebSocket connection itself,
static frontend assets, `/ping`, and `/_health` do not require authentication.
There are no custom HTTP data routes or upload handlers in this app.

This is a shared test-dashboard login: tokens are bearer credentials, with no
per-user accounts or individual server-side revocation. Rotating the shared
password revokes all saved tokens. It does not restrict access to the upstream
public dataset URLs.

Reflex 0.9.10 production mode serves frontend and backend on one port:

```bash
reflex run --env prod --single-port --backend-port 8000
```

For a reverse proxy, set `REFLEX_API_URL` to the public backend URL and route
both HTTP and WebSocket traffic to that port. Separate frontend/backend ports
are supported in development mode.

Python runtime dependencies are pinned in `requirements.txt`. Reflex manages
the frontend packages in `reflex.lock/package.json` and `reflex.lock/bun.lock`;
keep both files when updating Reflex. The Python dependencies are all used:
Arrow supplies parquet support, and DVC's S3 extra supplies dataset version access.

## Validation

With the virtual environment activated, from the repository root:

```bash
python -m pip install pytest ruff
PYTHONPATH=webapp:pythonlib python -m pytest webapp/tests pythonlib/tests -q
ruff check webapp --select F,E9
python -m pip check
cd webapp
reflex export --frontend-only --no-zip
```

The tests use local fixtures. Production export also loads the configured
datasets and installs frontend packages, so it needs network access.

## Constructor and the flight database

`/constructor` reads B737, A320 and E170 trends and engine installation/removal
markers from DuckDB. Select an engine (search also matches aircraft type and tail
number), an inclusive date range, and parameters grouped by Takeoff/Cruise. The
chart uses the same readings and trailing-average presentation as EGT, without
labels or predictions. Smoothing includes history before the displayed range.
The other dashboard pages continue using their existing loaders.

Constructor keeps the engine/type (`engine`), date range (`start`, `end`), ordered
parameter selection (`params`, comma-separated), smoothing window (`smoothing`),
and horizontal chart viewport (`x_start`, `x_end`) in the URL. Reloading or sharing
the link restores those settings. Empty date bounds and an empty parameter
selection are preserved. Changing the date range resets the viewport; zooming or
panning updates the URL without querying DuckDB again.

Create the database from the repository root, with the virtual environment active:

```bash
PYTHONPATH=webapp python -m webapp.data.migrate_flights
```

The command downloads the five flight Parquets and onwing CSV configured in
`webapp/data/registry.py`. To use previously downloaded copies with the same
filenames, add `--source-dir /path/to/sources`. It does not load maintenance,
utilization, EGT labels or predictions. Default output is `data/flights.duckdb`,
relative to the repository (independent of the current working directory).
Set `FLIGHT_DATABASE_PATH` for both the migration and Quack service to override it,
or use `--database /path/to/flights.duckdb` for the migration alone. Then install
and start the separate Quack service using [the deployment guide](../deploy/README.md).
Constructor defaults to `FLIGHT_DATABASE_MODE=quack` and connects to
`FLIGHT_QUACK_URL` (default `quack:127.0.0.1:9494`), using `QUACK_TOKEN_FILE` or
`QUACK_TOKEN` from the backend environment. The service owns the database file.
For offline development only, set `FLIGHT_DATABASE_MODE=file` while Quack is
stopped; explicit file paths in fixture tests also use that mode.

The database contains:

- `reports`: one wide table containing the union of all source columns, plus
  `aircraft_type`. `flight_phase` distinguishes reports. Columns absent from a
  source are NULL. Source row counts, duplicates, null engine IDs, measurements
  and timestamp precision are retained. Engine IDs are nullable strings;
  aircraft IDs are zero-padded strings matching the aircraft registry.
- `onwing`: installation/removal history, with each distinct source CSV loaded
  once. Used for Constructor replacement markers.
- `report_parameters`: numeric measurement columns available per type and phase.
- `import_sources`: source URLs, imported row counts and import timestamps.
- `constructor_reports`: view installed by the Quack service to retain source
  row ordering for duplicate timestamps without changing the report columns.

The report grain is an engine-position observation at its original report
timestamp, not a takeoff/cruise join. No uniqueness constraint or synthetic
flight ID is inferred from the historical snapshots. Rows without an engine ID
remain queryable in SQL but cannot be selected by engine in Constructor.

The migration refuses to overwrite an existing database by default. `--replace`
explicitly rebuilds it from the sources. It builds a temporary database beside the
destination, validates counts, closes it, and atomically publishes it; failed
imports leave the previous file intact. Stop the dashboard and Quack before replacing
it. Database files are ignored by Git and must be migrated or copied separately
when deploying. Connection failures are surfaced on Constructor.

Constructor opens short-lived read-only Quack attachments; it has no file or
Parquet fallback if the service is unavailable. External trusted clients can
insert data through the same service. The deployment guide includes an SSH
tunnel, client examples and the `transaction(db)` helper required for remote
batch atomicity in Quack 1.5.6.

The planned incremental connector is a separate step: it will use
`ecmapp.no_data_report`, pivot the upstream reports, resolve engine IDs and insert
new observations. Its merge keys and writer coordination must be explicit:
Only Quack owns the local database file; all dashboard and writer processes
connect through it. See
[DuckDB concurrency](https://duckdb.org/docs/stable/connect/concurrency.html).
