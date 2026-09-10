# EGT failure dataset

This DVC sub-repository stores the flight-level labels used by the web app's
EGT page. Its default remote is `s3://ecm-data/egt-failure-dataset`.

The dataset schema is:

| column | dtype | meaning |
| --- | --- | --- |
| `aircraft_id` | `int64` | aircraft identifier |
| `engine_position` | `int64` | installed engine position |
| `engine_id` | nullable `Int64` | engine identifier from the source row |
| `flight_phase` | string | `TAKEOFF` or `CRUISE` |
| `flight_datetime` | `datetime64[ns]` | source observation timestamp |
| `failure_value` | `int8` | curated failure label (`0` or `1`) |

`data/egt_failure_baseline.parquet` is the immutable migrated baseline.
`data/egt_failure_manual_labels.parquet` records corrections relative to that
baseline. Exporting in the web app writes the corrections into
`data/egt_failure_dataset.parquet`, whose DVC pointer defines the selectable
dataset versions.

Rebuild the initial files from the two B737 source parquets and the legacy
curated indication dataset:

```bash
python migrate.py --legacy ../data/egt_indication_curated.parquet
dvc add data/egt_failure_baseline.parquet \
  data/egt_failure_dataset.parquet \
  data/egt_failure_manual_labels.parquet
dvc push
```

The migration retains every takeoff row with non-null `egthdm` and every
cruise row with non-null `degt`. A row receives `failure_value = 1` when a
legacy failure point for the same engine is strictly less than six hours away.

The initial migration produced 329,444 rows (165,158 takeoff and 164,286
cruise), including 9,302 rows with a null source `engine_id`. It migrated all
2,758 unique legacy failure timestamps across six engines and labeled 2,784
new rows as failures.
