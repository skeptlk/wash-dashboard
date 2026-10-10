# DuckDB / Quack service

`wash-quack.service` is the sole process opening `data/flights.duckdb` for writing.
Constructor uses authenticated Quack connections. External Python clients use the
same service through an SSH tunnel. Existing Parquet-backed dashboard pages are
unchanged.

DuckDB is pinned to 1.5.6. Quack is an official beta extension; install it for that
version on both client and server. See the [protocol documentation](https://duckdb.org/docs/current/quack/overview).

## Deploy on compute-vm-2

These unit templates use the existing deployment user `b000gdan`, repository
`/home/b000gdan/ecm` and `wash-dashboard.service`. Verify those paths/user before
installing on another host. Keep the existing dashboard `override.conf`, password,
port and public URL settings; the new drop-in only configures the database.

After committing/pushing the code, run on the server as `b000gdan`:

```bash
cd /home/b000gdan/ecm
git pull --ff-only
.venv/bin/python -m pip install -r webapp/requirements.txt

# Install once; regular service startup only LOADs the installed extension.
PYTHONPATH=webapp DUCKDB_EXTENSION_DIRECTORY=/home/b000gdan/.duckdb/extensions \
  .venv/bin/python -m webapp.data.quack install

# First deployment only; do not rebuild an existing database with new observations.
if [ ! -f data/flights.duckdb ]; then
  PYTHONPATH=webapp .venv/bin/python -m webapp.data.migrate_flights
fi

sudo install -d -m 755 /etc/ecm
sudo install -m 644 deploy/quack.env.example /etc/ecm/quack.env
sudo sh -c 'umask 077; if [ ! -e /etc/ecm/quack.token ]; then openssl rand -hex 32 > /etc/ecm/quack.token; fi'
sudo chown b000gdan /etc/ecm/quack.token
sudo chmod 600 /etc/ecm/quack.token

# Release any old direct file readers before starting the database owner.
sudo systemctl stop wash-dashboard.service
sudo install -m 644 deploy/systemd/wash-quack.service /etc/systemd/system/wash-quack.service
sudo install -d /etc/systemd/system/wash-dashboard.service.d
sudo install -m 644 deploy/systemd/wash-dashboard-quack.conf /etc/systemd/system/wash-dashboard.service.d/quack.conf
sudo systemctl daemon-reload
sudo systemctl enable --now wash-quack.service

set -a
. /etc/ecm/quack.env
set +a
PYTHONPATH=webapp .venv/bin/python -m webapp.data.quack check
# Run only after the connection check succeeds:
sudo systemctl restart wash-dashboard.service
sudo systemctl status wash-quack.service wash-dashboard.service --no-pager
sudo journalctl -u wash-quack.service -n 50 --no-pager
```

If `/etc/ecm/quack.env` already has custom paths, preserve those when updating.
The token creation step preserves an existing token. Never commit the real token
or include it in client-side Reflex state. `FLIGHT_DATABASE_PATH` belongs to the
server; Constructor does not open that file in Quack mode.

No inbound database firewall port is needed: the server binds only to
`127.0.0.1:9494`. The dashboard reuses up to four read-only connections per process,
leased exclusively to each reader. Failed connections are discarded. Constructor
executes complete queries through `flights.query()` so filtering and smoothing
stay on the server, including queries against views. A service
failure is surfaced in the UI, with no silent fallback to the local file.
SIGTERM/SIGINT stops the listener, checkpoints the database and closes it.

The first service start upgrades two compatibility details without rebuilding
reports: it removes the `import_sources.imported_at` function default (new imports
supply that value explicitly), and creates `constructor_reports`, a view exposing
DuckDB's implicit row order for smoothing. Existing report values and import times
are preserved. Quack 1.5.6 cannot attach catalogs with function-valued defaults;
avoid adding such defaults while using this version.

## External Python connection

Create a tunnel from your workstation (substitute the actual SSH host):

```bash
ssh -N -L 19494:127.0.0.1:9494 b000gdan@<ssh-host>
```

Keep that terminal open. Transfer the token securely over SSH into a local file
readable only by your user, then use the project environment in another terminal:

```bash
export FLIGHT_QUACK_URL=quack:127.0.0.1:19494
export QUACK_TOKEN_FILE=/absolute/path/to/local/quack.token
PYTHONPATH=webapp .venv/bin/python -m webapp.data.quack install
PYTHONPATH=webapp .venv/bin/python -m webapp.data.quack check
```

A client in this checkout can read or write using the same connection helper:

```python
from webapp.data.quack import connect_remote, transaction

with connect_remote() as db:
    print(db.execute("SELECT aircraft_type, count(*) FROM reports GROUP BY 1").fetchall())

# rows is a batch produced by your connector; timestamps are source wall-clock time.
def insert_reports(rows):
    with connect_remote(read_only=False) as db, transaction(db):
        db.executemany(
            """INSERT INTO reports
               (aircraft_type, aircraft_id, engine_position, engine_id,
                flight_phase, flight_datetime, egthdm)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
```

Use `transaction(db)` for write batches: in Quack 1.5.6 a plain client `BEGIN`
does not isolate remote inserts. The helper sends BEGIN/COMMIT/ROLLBACK through
the attached server catalog; concurrent readers see only committed rows.
Run schema changes separately before the batch: native remote DDL inside this
explicit transaction can fail with a nested-transaction error in Quack 1.5.6.

The shared token grants trusted SQL access; the client's `READ_ONLY` attachment
is protection against accidental writes, not a separate server authorization role.
Do not distribute it to dashboard users. For direct internet exposure, configure
a TLS reverse proxy and an authorization policy first; the supplied service
intentionally stays on localhost. See [Quack security](https://duckdb.org/docs/current/quack/security).

The `no_data_report` incremental connector is a separate step. Before production
inserts it must define merge keys/checkpoints and prevent repeated batches from
creating duplicates. New measurement columns also need `report_parameters`
updates and a service restart to refresh `constructor_reports`; engine replacement
history lives in `onwing`.

## Local development and tests

Quack is the default backend. To inspect a closed database without a service,
explicitly set `FLIGHT_DATABASE_MODE=file`. Never use file mode while the service
owns that database. Migration and fixture tests can still pass an explicit file
path independently of the service configuration.

To run the real subprocess/network integration tests after extension installation:

```bash
RUN_QUACK_TESTS=1 PYTHONPATH=webapp:pythonlib \
  .venv/bin/python -m pytest webapp/tests/test_flight_db.py -k quack -q
```

These tests start a temporary localhost server, verify authentication, Constructor
queries, concurrent readers during an uncommitted write, visibility after commit,
and persistence after graceful shutdown. The ordinary offline test suite skips
network tests. Set `DUCKDB_EXTENSION_DIRECTORY` consistently if using a custom
extension cache.

For migration/replacement or offline copying, stop the dashboard and Quack first.
Never run `migrate_flights --replace` against a database held open by Quack. For
subsequent code-only deploys, restart Quack if its code changes and restart the
existing dashboard service; use `daemon-reload` only when unit/drop-in files change.
