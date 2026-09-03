"""DVC dataset versions for the flight-level EGT failure labels.

A dataset *version* is a git commit that changed the DVC pointer at
``egt-failure-dataset/data/egt_failure_dataset.parquet.dvc``. This module
enumerates those commits and loads the parquet at any given revision via
``dvc.api`` so the EGT page can show a read-only snapshot.

The app never commits or pushes — a new version appears here only after the
user commits the pointer to git.

Pure pandas + subprocess; mirrors the style of ``labels.py``.
"""

from __future__ import annotations

import io
import subprocess
from datetime import datetime
from typing import Optional

import pandas as pd

from .egt_indication import DATASET_REPO_ROOT, REPO_ROOT, merge_failure_spans

# The data path is relative to the nested DVC root; the pointer path is relative
# to the outer Git repository.
CURATED_REL = "data/egt_failure_dataset.parquet"
CURATED_DVC = "egt-failure-dataset/data/egt_failure_dataset.parquet.dvc"

# Field separator for `git log --format` (unit separator, safe in commit text).
_FS = "\x1f"

# sha -> normalized curated frame. No Date.now()/random keys: safe to cache.
_FRAME_CACHE: dict[str, pd.DataFrame] = {}


def list_versions() -> list[dict]:
    """Git commits that changed the curated pointer, newest first.

    Returns ``[{"sha", "short", "date", "subject", "label"}]`` — empty when the
    pointer has never been committed.
    """
    proc = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "log",
         f"--format=%H{_FS}%h{_FS}%cs{_FS}%s", "--", CURATED_DVC],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        return []
    versions: list[dict] = []
    for line in proc.stdout.splitlines():
        parts = line.split(_FS)
        if len(parts) != 4:
            continue
        sha, short, date, subject = parts
        versions.append({
            "sha": sha,
            "short": short,
            "date": date,
            "subject": subject,
            "label": f"{short}  {date}  {subject[:40]}",
        })
    return versions


def _load_version_frame(sha: str) -> pd.DataFrame:
    """Read the curated parquet at git revision ``sha`` (cached by sha).

    Raises ``RuntimeError`` with a UI-friendly message if the data blob can't
    be fetched (e.g. not in the local DVC cache and the remote is unreachable).
    """
    cached = _FRAME_CACHE.get(sha)
    if cached is not None:
        return cached
    try:
        import dvc.api

        with dvc.api.open(
            CURATED_REL, repo=str(DATASET_REPO_ROOT), rev=sha, mode="rb"
        ) as f:
            df = pd.read_parquet(io.BytesIO(f.read()))
    except Exception as exc:  # noqa: BLE001 — surface any fetch/read failure to UI
        raise RuntimeError(
            f"Could not load version {sha[:7]}: {exc}. Try `dvc pull`."
        ) from exc

    # Normalize to match the live path (egt_indication._load).
    df = df.dropna(subset=["engine_id", "flight_datetime"]).copy()
    df["engine_id"] = pd.to_numeric(df["engine_id"], errors="coerce").astype(
        "Int64"
    )
    dt = pd.to_datetime(df["flight_datetime"], errors="coerce")
    if dt.dt.tz is not None:
        dt = dt.dt.tz_localize(None)
    df["flight_datetime"] = dt
    df = df.dropna(subset=["flight_datetime"])
    df = df.dropna(subset=["engine_id"])
    df["engine_id"] = df["engine_id"].astype("int64").astype(str)

    _FRAME_CACHE[sha] = df
    return df


def failure_spans_for_version(
    sha: str,
    engine_id: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> list[tuple[datetime, datetime]]:
    """Failure-shading spans for one engine from a past curated version.

    Collapses the version frame's ``failure_value`` to one flag per flight
    (any parameter flagged → failing) and reuses :func:`merge_failure_spans`.
    Raises ``RuntimeError`` if the version can't be loaded.
    """
    df = _load_version_frame(sha)
    g = df[df["engine_id"] == str(engine_id)]
    if g.empty:
        return []
    per_flight = (
        g.groupby("flight_datetime")["failure_value"]
        .max()
        .fillna(0)
        .astype(int)
        .sort_index()
    )
    return merge_failure_spans(
        list(per_flight.index), per_flight.tolist(), start, end
    )
