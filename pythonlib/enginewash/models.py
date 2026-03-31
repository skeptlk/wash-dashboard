"""Data models for engine wash effect analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd


class FlightPhase(Enum):
    """Flight phase for parameter measurement."""

    TAKEOFF = "TAKEOFF"
    CRUISE = "CRUISE"


class TrendDirection(Enum):
    """Direction indicating whether higher or lower values are better.
      Meaning:
      UP   (+1) = higher is better (e.g., EGT margin)
      DOWN (-1) = lower is better  (e.g., fuel flow, differential EGT)
    """

    UP = 1
    DOWN = -1


@dataclass
class FlightRecord:
    """A single flight data point for one engine.

    Attributes:
        engine_id: Engine identifier.
        flight_datetime: Timestamp of the flight.
        float_value: Raw parameter value.
        float_value_smooth: Pre-smoothed value from DB (optional; falls back to float_value).
    """

    engine_id: str
    flight_datetime: pd.Timestamp
    float_value: float
    float_value_smooth: Optional[float] = None


@dataclass
class MaintenanceRecord:
    """A single wash/maintenance event.

    Attributes:
        engine_id: Engine identifier.
        maint_datetime: Timestamp of the maintenance event.
        ata_code: ATA code of the maintenance event.
    """

    engine_id: str
    maint_datetime: pd.Timestamp
    ata_code: Optional[str] = None


@dataclass(frozen=True)
class WashParameter:
    """Configuration for a single engine parameter to analyze.

    Attributes:
        name: Parameter name (e.g., "GWFM", "DEGT", "EGTHDM").
        flight_phase: Flight phase the parameter is measured in.
        trend_direction: Whether higher or lower values indicate improvement.
        threshold: Threshold for loss-of-efficiency detection.
    """

    name: str
    flight_phase: FlightPhase
    trend_direction: TrendDirection
    threshold: float = 2.0

    @property
    def direction(self) -> int:
        """Return the numeric direction value (+1 or -1)."""
        return self.trend_direction.value

    @property
    def suffix(self) -> str:
        """Column suffix for this parameter, e.g. 'GWFM_CRUISE'."""
        return f"{self.name}_{self.flight_phase.value}"


GWFM = WashParameter(
    name="GWFM",
    flight_phase=FlightPhase.CRUISE,
    trend_direction=TrendDirection.DOWN,
    threshold=0.05,
)

DEGT = WashParameter(
    name="DEGT",
    flight_phase=FlightPhase.CRUISE,
    trend_direction=TrendDirection.DOWN,
    threshold=2.0,
)

EGTHDM = WashParameter(
    name="EGTHDM",
    flight_phase=FlightPhase.TAKEOFF,
    trend_direction=TrendDirection.UP,
    threshold=2.0,
)

DEFAULT_PARAMETERS = [GWFM, DEGT, EGTHDM]


@dataclass
class WashConfig:
    """Configuration for the wash module

    Attributes:
        smooth_window: Number of flights for smoothing.
        n_obs_mean: Number of observations for before/after wash mean.
        parameters: List of parameters to analyze.
    """

    smooth_window: int = 30
    n_obs_mean: int = 15
    parameters: list[WashParameter] = field(default_factory=lambda: list(DEFAULT_PARAMETERS))


@dataclass
class WashEvent:
    """Result for a single wash event on a single parameter.

    Attributes:
        engine_id: Engine identifier
        event_index: Cumulative event index (starting from 1)
        maint_datetime: Maintenance event timestamp
        ata_code: ATA code of the maintenance event
        parameter: The analyzed parameter config
        mean_before: Worst smoothed value in last N obs before wash
        mean_after: Best smoothed value in first N obs after wash
        delta: After minus before (sign depends on trend direction)
        time_loss_of_efficiency: Timestamp when benefit wore off, or None
    """

    engine_id: str
    event_index: int
    maint_datetime: pd.Timestamp
    ata_code: Optional[str]
    parameter: WashParameter
    mean_before: float
    mean_after: float
    delta: float
    time_loss_of_efficiency: Optional[pd.Timestamp] = None

    @property
    def has_loss(self) -> bool:
        """Whether a loss-of-efficiency point was detected."""
        return self.time_loss_of_efficiency is not None


@dataclass
class WashResult:
    """Complete result of wash effect analysis.

    Attributes:
        df: Full time-series DataFrame with smoothed values and annotations
        events: List of WashEvent results per wash per parameter
        df_event: Summary DataFrame of wash events (one row per wash,
            columns for each parameter's delta and loss-of-efficiency metrics).
    """

    df: pd.DataFrame
    events: list[WashEvent]
    df_event: pd.DataFrame
