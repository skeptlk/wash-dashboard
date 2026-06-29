"""Load the EGT-failure ML predictions (Boeing only).

The predictions parquet carries one ``failure_value_auto`` flag per
(engine, parameter, flight). We collapse it to a per-flight failure flag
(any parameter flagged → failing) and expose, per engine, the contiguous
time spans where the sensor is predicted to be failing — used to shade the
EGT Indication charts.

Loaded once at import, mirroring ``loader.py``. The actual parameter *values*
plotted on the charts come from the Boeing parquet files in the registry
(the source of truth); this file is used only for the failure predictions.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd

EGT_PREDICTIONS_URL = (
    "https://storage.yandexcloud.net/ecm-data/egt_indication_auto_labels_2026-06-10.parquet"
)

# engine_id -> DataFrame[flight_datetime, failure], one row per flight, time-sorted.
_BY_ENGINE: dict[str, pd.DataFrame] = {}

# Full per-(engine, parameter, flight) auto-labels frame, normalized once at load.
# Exposed so the labeling/export pipeline (`data/labels.py`) can build a curated copy
# without re-downloading the parquet. Columns mirror the source plus a normalized
# string `engine_id` and tz-naive `flight_datetime`.
RAW_AUTO_LABELS: pd.DataFrame = pd.DataFrame()

# Engines (str ids) that have predictions, sorted.
EGT_PREDICTION_ENGINES: list[str] = []

# Subset of the above with at least one predicted-failure flight.
EGT_FAILURE_ENGINES: set[str] = set()


def _load() -> None:
    global EGT_PREDICTION_ENGINES, EGT_FAILURE_ENGINES, RAW_AUTO_LABELS

    df = pd.read_parquet(EGT_PREDICTIONS_URL)
    df = df.dropna(subset=["engine_id", "flight_datetime"]).copy()
    df["engine_id"] = df["engine_id"].astype(int).astype(str)

    dt = pd.to_datetime(df["flight_datetime"], errors="coerce")
    if dt.dt.tz is not None:
        dt = dt.dt.tz_localize(None)
    df["flight_datetime"] = dt
    df = df.dropna(subset=["flight_datetime"])

    RAW_AUTO_LABELS = df.copy()

    df["failure"] = df["failure_value_auto"].fillna(0).astype(int)

    # Collapse to one flag per (engine, flight): any parameter flagged → failing.
    per_flight = (
        df.groupby(["engine_id", "flight_datetime"], as_index=False)["failure"]
        .max()
        .sort_values(["engine_id", "flight_datetime"])
    )

    for eid, g in per_flight.groupby("engine_id"):
        g = g[["flight_datetime", "failure"]].reset_index(drop=True)
        _BY_ENGINE[eid] = g
        if (g["failure"] == 1).any():
            EGT_FAILURE_ENGINES.add(eid)

    EGT_PREDICTION_ENGINES = sorted(_BY_ENGINE.keys())


def failure_spans_for(
    engine_id: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> list[tuple[datetime, datetime]]:
    """Contiguous time spans where the engine is predicted to be failing.

    Each failing flight shades from its own timestamp until the next flight
    (failing or not); contiguous runs merge into a single span. The trailing
    failing flight extends one day so a final isolated point stays visible.
    Optionally clipped to ``[start, end]``.
    """
    g = _BY_ENGINE.get(engine_id)
    if g is None or g.empty:
        return []

    times = g["flight_datetime"].tolist()
    flags = g["failure"].tolist()
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


_load()
