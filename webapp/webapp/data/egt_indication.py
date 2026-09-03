"""Load the flight-level EGT failure labels (Boeing only).

The baseline parquet has one row for every usable takeoff EGTHDM or cruise
DEGT source observation.  Parameter values plotted on the charts still come
from the Boeing source parquets; this dataset supplies only failure labels.
"""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
DATASET_REPO_ROOT = REPO_ROOT / "egt-failure-dataset"
DATASET_DATA_DIR = DATASET_REPO_ROOT / "data"
BASELINE_REL = "data/egt_failure_baseline.parquet"
BASELINE_PATH = DATASET_REPO_ROOT / BASELINE_REL

# engine_id -> DataFrame[flight_datetime, failure], one row per flight, time-sorted.
_BY_ENGINE: dict[str, pd.DataFrame] = {}

# Full flight-level migrated baseline, including source rows whose engine id is
# null. Exposed so the labeling/export pipeline can preserve exact cardinality.
RAW_BASELINE_LABELS: pd.DataFrame = pd.DataFrame()

# Engines (str ids) that have predictions, sorted.
EGT_PREDICTION_ENGINES: list[str] = []

# Subset of the above with at least one predicted-failure flight.
EGT_FAILURE_ENGINES: set[str] = set()


def _read_baseline() -> pd.DataFrame:
    """Read locally when pulled, otherwise stream through the nested DVC repo."""
    if BASELINE_PATH.exists():
        return pd.read_parquet(BASELINE_PATH)

    try:
        import dvc.api

        with dvc.api.open(
            BASELINE_REL, repo=str(DATASET_REPO_ROOT), mode="rb"
        ) as source:
            return pd.read_parquet(io.BytesIO(source.read()))
    except Exception as exc:  # noqa: BLE001 - fail startup with actionable context
        raise RuntimeError(
            "Could not load the EGT failure baseline from DVC. "
            "Run `dvc pull` in egt-failure-dataset."
        ) from exc


def _load() -> None:
    global EGT_PREDICTION_ENGINES, EGT_FAILURE_ENGINES, RAW_BASELINE_LABELS

    raw = _read_baseline()
    required = {
        "aircraft_id",
        "engine_position",
        "engine_id",
        "flight_phase",
        "flight_datetime",
        "failure_value",
    }
    missing = sorted(required.difference(raw.columns))
    if missing:
        raise RuntimeError(
            f"EGT failure baseline is missing columns: {', '.join(missing)}"
        )

    raw = raw[
        [
            "aircraft_id",
            "engine_position",
            "engine_id",
            "flight_phase",
            "flight_datetime",
            "failure_value",
        ]
    ]
    raw["engine_id"] = pd.to_numeric(raw["engine_id"], errors="coerce").astype(
        "Int64"
    )
    dt = pd.to_datetime(raw["flight_datetime"], errors="coerce")
    if dt.dt.tz is not None:
        dt = dt.dt.tz_localize(None)
    raw["flight_datetime"] = dt
    labels = pd.to_numeric(raw["failure_value"], errors="coerce")
    if labels.isna().any() or (~labels.isin([0, 1])).any():
        raise RuntimeError("EGT failure baseline contains labels other than 0 or 1")
    raw["failure_value"] = labels.astype("int8")

    RAW_BASELINE_LABELS = raw

    df = raw.dropna(subset=["engine_id", "flight_datetime"]).copy()
    df["engine_id"] = df["engine_id"].astype("int64").astype(str)
    df["failure"] = df["failure_value"].astype(int)

    # Guard against duplicate timestamps by retaining the strongest label.
    per_flight = (
        df.groupby(["engine_id", "flight_datetime"], as_index=False)["failure"]
        .max()
        .sort_values(["engine_id", "flight_datetime"])
    )

    _BY_ENGINE.clear()
    EGT_FAILURE_ENGINES.clear()
    for eid, g in per_flight.groupby("engine_id"):
        g = g[["flight_datetime", "failure"]].reset_index(drop=True)
        _BY_ENGINE[eid] = g
        if (g["failure"] == 1).any():
            EGT_FAILURE_ENGINES.add(eid)

    EGT_PREDICTION_ENGINES = sorted(_BY_ENGINE.keys())


def merge_failure_spans(
    times: list,
    flags: list,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> list[tuple[datetime, datetime]]:
    """Collapse per-flight failure flags into contiguous shading spans.

    ``times`` are time-sorted flight timestamps and ``flags`` the parallel 0/1
    failure flags. Each failing flight shades from its own timestamp until the
    next flight (failing or not); contiguous runs merge into a single span. The
    trailing failing flight extends one day so a final isolated point stays
    visible. Optionally clipped to ``[start, end]``.
    """
    n = len(times)
    spans: list[tuple[datetime, datetime]] = []
    for i, t in enumerate(times):
        if flags[i] != 1:
            continue
        nxt = times[i + 1] if i + 1 < n else t + pd.Timedelta(days=1)
        spans.append((t.to_pydatetime(), nxt.to_pydatetime()))

    # Merge adjacent/overlapping spans.
    spans.sort()
    merged: list[tuple[datetime, datetime]] = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    if start is None and end is None:
        return merged

    clipped: list[tuple[datetime, datetime]] = []
    for s, e in merged:
        if end is not None and s > end:
            continue
        if start is not None and e < start:
            continue
        clipped.append((max(s, start) if start else s, min(e, end) if end else e))
    return clipped


def failure_spans_for(
    engine_id: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> list[tuple[datetime, datetime]]:
    """Contiguous time spans where the engine is predicted to be failing.

    Thin wrapper over :func:`merge_failure_spans` using the migrated baseline
    per-flight frame. Optionally clipped to ``[start, end]``.
    """
    g = _BY_ENGINE.get(engine_id)
    if g is None or g.empty:
        return []
    return merge_failure_spans(
        g["flight_datetime"].tolist(), g["failure"].tolist(), start, end
    )


_load()
