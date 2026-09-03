# Webapp review — 2026-09-03

Reviewed all five routes, their state handlers, data/plot helpers, tests, and
dependency manifests against the working tree, including the existing EGT
dataset changes.

## Remaining findings

1. **High: authentication is only a page-load redirect.**
   `webapp/state/auth.py:30` redirects unauthenticated visitors, but sensitive
   events such as `EgtState.apply_label`, `delete_label`, and `export_dataset`
   do not check authentication. `webapp/webapp.py` has no central event guard.
   Backend events need an authorization check before reading or modifying data;
   hiding controls or navigating to `/login` does not enforce that check.
   The shared password also defaults to the public literal `ecm` when
   `APP_PASSWORD` is missing (`webapp/state/auth.py:9`).

2. **Medium: date-only end dates exclude most of the final day.**
   The page states parse `YYYY-MM-DD` as midnight and pass it to inclusive
   timestamp filters in `webapp/data/derived.py:54` and
   `webapp/data/egt_params.py:74`. For example, an end date of `2026-06-10`
   excludes a reading at noon that day. Convert the page's date-only upper bound
   to an exclusive next-day boundary. Keep the exact timestamp semantics of
   manual label intervals separate. The schedule currently uses `<= end + 1 day`,
   which also includes midnight from the following day.

3. **Medium: snapshot read-only mode is only enforced by the UI.**
   `EgtState.set_version` disables label mode and the page hides the panel, but
   `apply_label`, `delete_label`, and `export_dataset` do not reject calls while
   `selected_version != "working"`. A queued or directly invoked event can still
   alter the live dataset while a historical snapshot is selected. Check the
   selected version in each mutation handler before accessing the label store.

These behavior changes are separate from the dead-code/dependency cleanup.

## Changes made

- Removed unused global engine-list/label computed vars, write-only analysis
  engine state, an unused analysis-chart argument and import, a discarded event
  set, and the unused stored engine-family map. Reused the filtered event list.
- Fixed the EGT chart title being overwritten by an install/removal annotation.
- Pinned and tested Reflex 0.9.10.post1, pandas 3.0.5, NumPy 2.5.2, Plotly 7.0.0,
  PyArrow 25.0.1, and DVC with S3 3.67.1. DVC was already current locally.
  These pins require Python 3.12+. All six direct dependencies are used.
- Regenerated both Reflex frontend lockfiles through the framework's production
  build. Added setup/validation instructions and corrected stale cleanup references.

Release metadata was checked against the primary package registry:
[Reflex](https://pypi.org/project/reflex/0.9.10.post1/),
[pandas](https://pypi.org/project/pandas/3.0.5/),
[NumPy](https://pypi.org/project/numpy/2.5.2/),
[Plotly](https://pypi.org/project/plotly/7.0.0/),
[PyArrow](https://pypi.org/project/pyarrow/25.0.1/),
[DVC](https://pypi.org/project/dvc/3.67.1/).

## Validation

- Python 3.13.9: all 63 existing webapp/library tests pass with the updated pins.
- Ruff `F,E9`, Vulture at 80% confidence, and `pip check` pass.
  Lower-confidence Vulture hits are TypedDict keys and the fixture package path.
- Production frontend export succeeds with all five routes and the configured
  B737, A320, and E170 datasets.
- Browser smoke check of the local production build: login, degradation report,
  wash report and event selection, schedule (275 events), EGT chart, and parameter
  toggle/reset all work. No browser errors were recorded. Label mutations and
  remote DVC upload were not exercised.
- Reflex 0.9.10 requires one production port for frontend and backend; the local
  server was verified with `--env prod --single-port --backend-port 8010`.
- `git diff --check` passes. Existing calculator and EGT dataset edits were preserved.
