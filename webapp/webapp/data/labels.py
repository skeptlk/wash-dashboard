"""Manual EGT failure labels: overlay store + dataset export.

The EGT page lets a user mark a time range for an engine as ``failure = 0/1``.
Those actions are stored in a small, auditable overlay parquet in the
``egt-failure-dataset`` DVC sub-repository.

"Export" bakes the overlay into a full copy of the migrated baseline. Both the
exported dataset and overlay are versioned with the nested DVC repository.

Pure pandas; mirrors the load-once style of ``loader.py`` / ``egt_indication.py``.
"""

from __future__ import annotations

import subprocess
import uuid
from datetime import datetime
from typing import Optional

import pandas as pd

from .egt_indication import (
    DATASET_DATA_DIR,
    DATASET_REPO_ROOT,
    RAW_BASELINE_LABELS,
)

DATA_DIR = DATASET_DATA_DIR
OVERLAY_PATH = DATA_DIR / "egt_failure_manual_labels.parquet"
CURATED_PATH = DATA_DIR / "egt_failure_dataset.parquet"

_OVERLAY_COLUMNS = [
    "row_id",
    "engine_id",
    "start_datetime",
    "end_datetime",
    "failure_value",
    "labeled_by",
    "labeled_at",
    "note",
]

# In-memory cache of the overlay frame; written through on every mutation.
_overlay: Optional[pd.DataFrame] = None


def _empty_overlay() -> pd.DataFrame:
    df = pd.DataFrame(columns=_OVERLAY_COLUMNS)
    df["engine_id"] = df["engine_id"].astype(str)
    df["start_datetime"] = pd.to_datetime(df["start_datetime"])
    df["end_datetime"] = pd.to_datetime(df["end_datetime"])
    df["labeled_at"] = pd.to_datetime(df["labeled_at"])
    df["failure_value"] = df["failure_value"].astype("int64")
    return df


def load_overlay() -> pd.DataFrame:
    """Return the overlay frame, loading it from disk once and caching."""
    global _overlay
    if _overlay is None:
        if OVERLAY_PATH.exists():
            df = pd.read_parquet(OVERLAY_PATH)
            df["engine_id"] = df["engine_id"].astype(str)
            df["start_datetime"] = pd.to_datetime(df["start_datetime"])
            df["end_datetime"] = pd.to_datetime(df["end_datetime"])
            df["labeled_at"] = pd.to_datetime(df["labeled_at"])
            df["failure_value"] = df["failure_value"].astype("int64")
            _overlay = df
        else:
            _overlay = _empty_overlay()
    return _overlay


def _write_overlay(df: pd.DataFrame) -> None:
    global _overlay
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OVERLAY_PATH, index=False)
    _overlay = df


def _parse_dt(value) -> Optional[pd.Timestamp]:
    if value is None or value == "":
        return None
    ts = pd.to_datetime(value, errors="coerce")
    if ts is pd.NaT:
        return None
    if getattr(ts, "tz", None) is not None:
        ts = ts.tz_localize(None)
    return ts


# engine_id -> Series indexed by flight_datetime with the migrated baseline label.
# The manual overlay records only diffs against this immutable baseline.
_BASELINE_BY_ENGINE: dict[str, pd.Series] = {}


def _engine_baseline(engine_id: str) -> pd.Series:
    eid = str(engine_id)
    cached = _BASELINE_BY_ENGINE.get(eid)
    if cached is not None:
        return cached
    df = RAW_BASELINE_LABELS
    if df is None or df.empty:
        s = pd.Series(dtype="int64")
    else:
        sub = df[df["engine_id"].astype("string") == eid]
        s = (
            sub.groupby("flight_datetime")["failure_value"]
            .max()
            .fillna(0)
            .astype(int)
            .sort_index()
        )
    _BASELINE_BY_ENGINE[eid] = s
    return s


def _diff_ranges(
    eid: str,
    eff: pd.Series,
    baseline: pd.Series,
    labeled_by: str,
    note: str,
) -> list[dict]:
    """Maximal runs where ``eff`` differs from ``baseline`` and
    shares the same value → one overlay row each (minimal, non-overlapping)."""
    rows: list[dict] = []
    ts = list(eff.index)
    vals = eff.to_numpy()
    base = baseline.to_numpy()
    now = pd.Timestamp(datetime.now())
    run_start = run_end = None
    run_val: Optional[int] = None

    def flush():
        if run_start is not None:
            rows.append(
                {
                    "row_id": uuid.uuid4().hex,
                    "engine_id": eid,
                    "start_datetime": run_start,
                    "end_datetime": run_end,
                    "failure_value": int(run_val),
                    "labeled_by": labeled_by or "",
                    "labeled_at": now,
                    "note": note or "",
                }
            )

    for i in range(len(ts)):
        if vals[i] != base[i]:
            v = int(vals[i])
            if run_start is not None and v == run_val:
                run_end = ts[i]
            else:
                flush()
                run_start, run_end, run_val = ts[i], ts[i], v
        else:
            flush()
            run_start = run_end = run_val = None
    flush()
    return rows


def labels_for(engine_id: str) -> list[dict]:
    """Overlay rows for one engine, newest first, formatted for the UI."""
    df = load_overlay()
    g = df[df["engine_id"] == str(engine_id)].sort_values("labeled_at", ascending=False)
    out: list[dict] = []
    for r in g.itertuples():
        out.append(
            {
                "row_id": r.row_id,
                "engine_id": r.engine_id,
                "start": pd.Timestamp(r.start_datetime).strftime("%Y-%m-%d %H:%M"),
                "end": pd.Timestamp(r.end_datetime).strftime("%Y-%m-%d %H:%M"),
                "failure_value": int(r.failure_value),
                "labeled_by": r.labeled_by or "",
                "note": r.note or "",
            }
        )
    return out


def add_label(
    engine_id: str,
    start,
    end,
    failure_value: int,
    labeled_by: str = "",
    note: str = "",
) -> int:
    """Label every phase observation in ``[start, end]`` as ``failure_value``.

    Idempotent and deduplicated by timestamp: an observation already at the
    requested value (whether from the baseline or a prior manual change) is left
    untouched. The overlay is then rebuilt as a minimal, non-overlapping set of
    correction ranges (diffs vs. the migrated baseline), so re-labeling never appends
    duplicate rows, and reverting a flight to its baseline value drops it from the overlay.

    Returns the number of timestamps whose effective label changed (0 = no-op).
    """
    s = _parse_dt(start)
    e = _parse_dt(end)
    if s is None or e is None:
        raise ValueError("start and end must be valid dates")
    if e < s:
        s, e = e, s
    # Exact-timestamp range: every phase observation whose timestamp
    # falls in the closed interval [s, e] is selected — no day snapping.
    value = 1 if failure_value else 0
    eid = str(engine_id)

    baseline = _engine_baseline(eid)
    if baseline.empty:
        return 0

    # Effective current label per flight = migrated baseline + existing overlay.
    overlay = load_overlay()
    eff = baseline.copy()
    eng_rows = overlay[overlay["engine_id"] == eid]
    for r in eng_rows.itertuples():
        m = (eff.index >= pd.Timestamp(r.start_datetime)) & (
            eff.index <= pd.Timestamp(r.end_datetime)
        )
        eff.loc[m] = int(r.failure_value)

    sel = (eff.index >= s) & (eff.index <= e)
    if not sel.any():
        return 0
    changed = int((eff[sel] != value).sum())
    if changed == 0:
        return 0  # every selected flight already has this label — do nothing.

    eff.loc[sel] = value

    # Rebuild this engine's overlay rows from the effective state (diffs vs baseline).
    others = overlay[overlay["engine_id"] != eid]
    new_rows = _diff_ranges(eid, eff, baseline, labeled_by, note)
    if new_rows:
        combined = pd.concat([others, pd.DataFrame(new_rows)], ignore_index=True)
    else:
        combined = others.reset_index(drop=True)
    if combined.empty:
        combined = _empty_overlay()
    _write_overlay(combined)
    return changed


def delete_label(row_id: str) -> None:
    df = load_overlay()
    _write_overlay(df[df["row_id"] != row_id].reset_index(drop=True))


def manual_spans_for(
    engine_id: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> list[tuple[datetime, datetime, int]]:
    """Manual label spans for one engine as ``(start, end, failure_value)``.

    Clipped to ``[start, end]`` when given. Unlike baseline failure spans these
    are kept separate per value so the chart can color 0 (cleared) vs 1 (failing).
    """
    df = load_overlay()
    g = df[df["engine_id"] == str(engine_id)].sort_values("labeled_at")
    out: list[tuple[datetime, datetime, int]] = []
    lo = _parse_dt(start)
    hi = _parse_dt(end)
    for r in g.itertuples():
        s = pd.Timestamp(r.start_datetime)
        e = pd.Timestamp(r.end_datetime)
        if hi is not None and s > hi:
            continue
        if lo is not None and e < lo:
            continue
        cs = max(s, lo) if lo is not None else s
        ce = min(e, hi) if hi is not None else e
        out.append((cs.to_pydatetime(), ce.to_pydatetime(), int(r.failure_value)))
    return out


def export_curated() -> dict:
    """Bake the overlay into a copy of the migrated flight-level baseline.

    Writes ``CURATED_PATH`` with manual ranges applied oldest to newest.
    Returns a summary dict ``{rows, overridden, path}``.
    """
    if RAW_BASELINE_LABELS is None or RAW_BASELINE_LABELS.empty:
        raise RuntimeError("failure baseline not loaded; cannot export dataset")

    out = RAW_BASELINE_LABELS.copy()
    baseline = out["failure_value"].fillna(0).astype("int8")
    out["failure_value"] = baseline

    overlay = load_overlay().sort_values("labeled_at")  # apply oldest→newest
    eid = out["engine_id"].astype(str)
    dt = out["flight_datetime"]
    for r in overlay.itertuples():
        mask = (
            (eid == str(r.engine_id))
            & (dt >= pd.Timestamp(r.start_datetime))
            & (dt <= pd.Timestamp(r.end_datetime))
        )
        out.loc[mask, "failure_value"] = int(r.failure_value)

    overridden = int((out["failure_value"] != baseline).sum())

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out.to_parquet(CURATED_PATH, index=False)
    return {"rows": int(len(out)), "overridden": overridden, "path": str(CURATED_PATH)}


def dvc_add() -> tuple[bool, str]:
    """Run ``dvc add`` on the overlay + curated files (no commit/push).

    Returns ``(ok, output)``. Git commit and ``dvc push`` are left to the
    operator so the web app never makes commits or network pushes on its own.
    """
    targets = [
        str(OVERLAY_PATH.relative_to(DATASET_REPO_ROOT)),
        str(CURATED_PATH.relative_to(DATASET_REPO_ROOT)),
    ]
    try:
        proc = subprocess.run(
            ["dvc", "add", *targets],
            cwd=DATASET_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        return False, f"dvc add failed: {exc}"
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, out.strip()
