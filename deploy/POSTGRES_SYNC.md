# PostgreSQL → Quack: Windows 10 ingestion

`webapp.data.sync_flights` runs once and exits. Schedule it every ten minutes on
one designated Windows machine. It reads PostgreSQL using a read-only session,
and writes to the existing Quack service; it never opens the server's database
file. Python 3.12+ x64 is required. No Reflex, DVC or pandas installation is needed.

## Source contract and pivot

The supplied `external_schema/schema.sql` describes the three measurement tables,
`ecmapp.no_data_report`, and `s7_mdb.onwing_engine`. Aircraft type also comes from
`s7_mdb.aircraft(aircraft_id, aircraft_type)`, as in the existing production export
queries; this table's DDL is **not** included in the supplied schema.
The read-only account needs SELECT on all six tables.

The operator confirmed that flight timestamps are UTC and `no_data_report` is
updated **after all three measurement tables have finished loading**. The connector
converts its `timestamptz` watermark using `AT TIME ZONE 'UTC'`, independent of
Windows/PostgreSQL session timezone. It processes TAKEOFF and CRUISE independently.
Aircraft types follow the original export prefixes: `B737% → B737`, `A320% → A320`,
`ERJ% → E170`. Unsupported types are logged and skipped; missing/ambiguous aircraft
mapping is an error. E170 CRUISE can be loaded even though the old snapshot only
contained TAKEOFF.

`sync_parameters.json` records the parameter lists from the existing
`ecm/scripts/pivot_tables_{b737,a320,erj}.sql` exports. PostgreSQL performs the pivot:
`MAX(COALESCE(float_value, integer_value::double precision))` for each parameter,
with the union of engine-input and engine-output report keys. Aircraft measurements
join on exact aircraft, phase and timestamp and are repeated for each engine.
As with the original exports, aircraft-only timestamps do not invent engine reports;
`char_value` and parameters outside the checked-in catalog are not imported.
Add new numeric parameters to that catalog deliberately. The connector adds missing
DOUBLE columns, updates `report_parameters`, and refreshes `constructor_reports`
through the server. No service restart is needed for those schema changes; reload
the dashboard page to refresh an already-loaded parameter selector.

Engine IDs join on aircraft, position and `[install_datetime, removal_datetime)`.
An absent match stays NULL. Overlapping intervals with distinct engine IDs stop the
batch rather than choosing an arbitrary engine. `deletion_flag` is retained as in
the previous export; it is not used as an undocumented filter. Each committed window
also refreshes that aircraft's `onwing` history from the same source snapshot.
Existing `n1_modifier` values and columns outside this import are preserved on
updates. New rows have NULL `n1_modifier`: its engine-configuration source was not
provided in `external_schema`.

## Progress, restarts and first catch-up

- `postgres_sync_state` in DuckDB holds a cursor and target per aircraft/type/phase.
  Each window atomically merges reports, history, parameter catalog and checkpoint.
- Report identity is `(aircraft_type, aircraft_id, engine_position, flight_phase,
  flight_datetime)`. `engine_id` is a value, not part of the identity. Repeating a
  window updates existing rows and does not append copies. Pre-existing duplicate
  snapshot keys are preserved, not silently removed.
- An interrupted run resumes its captured target from the last committed boundary.
  Boundary timestamps are intentionally included again. Even a lost commit response
  is safe: the next run reads the server checkpoint.
- On the first run, the start is the earlier of the two engine-position maxima for
  that aircraft/phase in DuckDB, minus 24 hours. If either engine position has no
  data, it starts at the earliest source engine report. No fleet-wide maximum is
  used. This fills the months of backlog without fetching all aircraft at once.
- Default windows cover seven days for one aircraft/phase. PostgreSQL uses its
  existing `(aircraft_id, flight_datetime)` indexes for range filtering; inspect
  production EXPLAIN if a window is slow. A query timeout is five minutes. At most
  20,001 pivoted rows are returned to the client; more than 20,000 causes a clean
  failure before writing. Reduce `--window-days` to 1 if needed. Quack sends at most
  250 rows per SQL statement within the window transaction.
- Unchanged completed watermarks perform no data import. Changed watermarks replay
  24 hours before the previous cursor, then catch up to the new watermark.
  A backwards watermark is an error.
- `--max-windows N` stops cleanly after N windows, useful for the first monitored
  catch-up. Subsequent scheduled invocations resume without that option.
- Older gaps, source deletions, and corrections that do not advance the watermark
  are not a change-data-capture feed. `--since 2026-01-01T00:00:00` explicitly replays
  source rows from a selected date, including history/engine mappings. It updates
  and inserts; it does not delete destination reports absent from the source.
  Remove `--since` from routine scheduling, or every run will repeat the replay.

A per-machine OS lock prevents overlapping Python runs and releases on process
exit/crash. Configure Task Scheduler to ignore new instances while one is running.
Use only one designated ingestion machine; this is not a distributed writer lock.
Other Parquet-backed dashboard pages continue to use their existing data sources.

## Python-only launcher (no PowerShell script execution)

Run `deploy/run_postgres_sync.py` directly with Python. It sets the package path,
loads configuration, opens the optional SSH tunnel, and calls the same ingestion
module. It does not invoke PowerShell or require changing its execution policy.
The already-configured `deploy/postgres-sync.local.psd1` is reused as a data file:
the Python reader accepts the example's flat, single-quoted strings and integer
values, including comments, UTF-8/BOM and UTF-16. It does not evaluate expressions
or variable interpolation. No additional Python dependencies are needed.

From the existing checkout on Windows:

```powershell
.\.venv-sync\Scripts\python.exe deploy\run_postgres_sync.py --dry-run --max-windows 1
```

An alternate config is selected with `--config C:\path\postgres-sync.local.psd1`.
All ingestion options (`--since`, `--aircraft`, `--window-days`, etc.) are forwarded;
explicit command-line options override config defaults. The existing OS lock is
acquired before SSH starts. The former `.ps1` launcher remains available for
existing installations but is not needed for these instructions.

## Install and verify

Place this repository at, for example, `C:\engine-wash`. In PowerShell:

```powershell
Set-Location C:\engine-wash
py -3.12 -m venv .venv-sync
.\.venv-sync\Scripts\python.exe -m pip install -r deploy\requirements-sync.txt
Copy-Item deploy\postgres-sync.example.psd1 deploy\postgres-sync.local.psd1
```

Edit the local configuration with the actual PostgreSQL host/database/account,
Quack token path and SSH destination/key. Store passwords in `PGPASSFILE` using
`host:port:database:user:password` format. Restrict the secrets directory to the
scheduled-task account. Adapt PostgreSQL TLS settings to the production certificate
policy (`verify-full` and `PGSSLROOTCERT` when available).

The optional wrapper tunnel uses Windows OpenSSH, key authentication and an existing
trusted `known_hosts` entry. Run SSH interactively once as the scheduled-task account
to validate the host and key; do not disable host-key verification. If the key is
passphrase-protected, provide an SSH agent available to that account. The wrapper
opens `127.0.0.1:19494 → server 127.0.0.1:9494`, then stops only its own SSH process.
Set `SSH_HOST = ''` to use an already-managed tunnel/endpoint.

Install Quack once **as the scheduled-task account**, using the same extension path
as the configuration (DuckDB 1.5.6 must match the server):

```powershell
$env:PYTHONPATH = 'C:\engine-wash\webapp'
$env:DUCKDB_EXTENSION_DIRECTORY = 'C:\engine-wash-secrets\duckdb-extensions'
.\.venv-sync\Scripts\python.exe -m webapp.data.quack install

# Read-only preview: validates source SQL, engine joins and representative windows.
.\.venv-sync\Scripts\python.exe deploy\run_postgres_sync.py --dry-run --max-windows 3

# First bounded import; subsequent invocations resume from its committed cursor.
.\.venv-sync\Scripts\python.exe deploy\run_postgres_sync.py --max-windows 10
# Full catch-up / normal recurring run:
.\.venv-sync\Scripts\python.exe deploy\run_postgres_sync.py
```

The commands above launch Python directly; no PowerShell script execution is
required. Logs rotate under `data\sync-logs\sync.log`; SSH errors are separate.
Exit 0 means success, unchanged state, or a requested window budget reached. Exit 1
means failure; previously committed windows remain safe. Driver error SQL and
credentials are not logged. Validation errors include an actionable explanation;
for connection errors check PostgreSQL/SSH/Quack logs and configured paths.

For direct Python use, set standard libpq `PGHOST`, `PGDATABASE`, `PGUSER`,
`PGPASSFILE`, etc., or `SYNC_POSTGRES_DSN`. Quack uses the existing
`FLIGHT_QUACK_URL`, `QUACK_TOKEN_FILE` and `DUCKDB_EXTENSION_DIRECTORY` variables.
`python -m webapp.data.sync_flights --help` lists filtering and replay options.

## Windows Task Scheduler (every 10 minutes)

Create a task under the same account used above:

1. Trigger: daily, repeat every **10 minutes**, duration **indefinitely**.
2. Action program: `C:\engine-wash\.venv-sync\Scripts\python.exe`.
3. Arguments: `"C:\engine-wash\deploy\run_postgres_sync.py"`.
4. Start in: `C:\engine-wash`.
5. Run whether the user is logged on or not, using the account with access to the
   secrets, SSH key/agent and network. Test this exact execution mode manually.
6. Settings: **Do not start a new instance**; allow catch-up to run for longer than
   ten minutes. Disable a short execution-time limit; the Python script already
   limits each PostgreSQL query. Enable “Run task as soon as possible after a
   scheduled start is missed”. Keep the machine awake and network connected.

A long first run remains active while repeated triggers are ignored. If stopped,
the next invocation resumes from its last committed window. Check Last Run Result
and the log after the first scheduled run.

References: [Quack protocol](https://duckdb.org/docs/current/quack/overview),
[psycopg transactions](https://www.psycopg.org/psycopg3/docs/basic/transactions.html),
[Windows task settings](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtasksettingsset).
