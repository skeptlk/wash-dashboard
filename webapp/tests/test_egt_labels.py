from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pandas as pd


def _load_labels_module(tmp_path: Path, baseline: pd.DataFrame):
    package_name = "_egt_labels_test_data"
    data_dir = Path(__file__).resolve().parents[1] / "webapp" / "data"

    package = types.ModuleType(package_name)
    package.__path__ = [str(data_dir)]
    sys.modules[package_name] = package

    indication = types.ModuleType(f"{package_name}.egt_indication")
    indication.DATASET_REPO_ROOT = tmp_path
    indication.DATASET_DATA_DIR = tmp_path / "data"
    indication.RAW_BASELINE_LABELS = baseline
    sys.modules[indication.__name__] = indication

    spec = importlib.util.spec_from_file_location(
        f"{package_name}.labels", data_dir / "labels.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_label_export_is_idempotent_and_preserves_dataset_rows(tmp_path: Path) -> None:
    baseline = pd.DataFrame(
        {
            "aircraft_id": [1, 1, 1],
            "engine_position": [1, 1, 2],
            "engine_id": pd.Series([10, 10, pd.NA], dtype="Int64"),
            "flight_phase": ["TAKEOFF", "CRUISE", "TAKEOFF"],
            "flight_datetime": pd.to_datetime(
                [
                    "2025-01-01 00:00:00",
                    "2025-01-01 02:00:00",
                    "2025-01-01 00:00:00",
                ]
            ),
            "failure_value": pd.Series([0, 1, 0], dtype="int8"),
        }
    )
    labels = _load_labels_module(tmp_path, baseline)

    assert labels.add_label("10", "2025-01-01 00:00", "2025-01-01 00:00", 1) == 1
    assert labels.add_label("10", "2025-01-01 00:00", "2025-01-01 00:00", 1) == 0

    summary = labels.export_curated()
    exported = pd.read_parquet(summary["path"])
    assert summary["rows"] == 3
    assert summary["overridden"] == 1
    assert exported["failure_value"].tolist() == [1, 1, 0]
    assert exported["engine_id"].isna().sum() == 1

    row_id = labels.labels_for("10")[0]["row_id"]
    labels.delete_label(row_id)
    summary = labels.export_curated()
    reverted = pd.read_parquet(summary["path"])
    assert summary["overridden"] == 0
    assert reverted["failure_value"].tolist() == [0, 1, 0]
