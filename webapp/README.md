# ECM webapp

Reflex UI for degradation, wash analysis, wash scheduling, and EGT indication.

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

Reflex 0.9.10 production mode serves frontend and backend on one port:

```bash
reflex run --env prod --single-port --backend-port 8000
```

For a reverse proxy, set `REFLEX_API_URL` to the public backend URL and route
both HTTP and WebSocket traffic to that port. Separate frontend/backend ports
are supported in development mode.

Python runtime dependencies are pinned in `requirements.txt`. Reflex manages
the frontend packages in `reflex.lock/package.json` and `reflex.lock/bun.lock`;
keep both files when updating Reflex. The six Python dependencies are all used:
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
