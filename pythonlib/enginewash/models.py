"""Data models for engine wash effect analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


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
        engine_id: Engine identifier
        flight_datetime: Timestamp of the flight
        parameter_name: Name of the parameter
        flight_phase: Flight phase
        float_value: Raw parameter value.
        float_value_smooth: Pre-smoothed value from DB (optional; if not provided, smoothing is handled by the library).
    """

    engine_id: str
    flight_datetime: datetime
    parameter_name: str
    flight_phase: FlightPhase
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
    maint_datetime: datetime
    ata_code: Optional[str] = None

@dataclass
class UtilizationRecord:
    """Engine utilization record.
    Attributes:
        engine_id: Engine identifier.
        total_cycles: Cumulative engine cycles.
        total_hours: Cumulative engine hours (tah from AMOS / 60, since tah is actually minutes).
        departure_datetime: Timestamp of the departure event.
        arrival_datetime: Timestamp of the arrival event.
    """
    engine_id: str
    total_cycles: int
    total_hours: float
    departure_datetime: datetime
    arrival_datetime: datetime


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
        smooth_window: Number of flights for per-segment smoothing.
        pre_smooth_window: Window for initial smoothing of raw values when
            pre-smoothed data (float_value_smooth) is not provided.
        n_obs_mean: Number of observations for before/after wash mean.
        before_wash_mode: How to pick mean_before within the pre-wash window.
            "worst" selects the worst smoothed value (extremum, per trend
            direction); "last" selects the last smoothed point before the wash.
        after_wash_mode: How to pick mean_after within the post-wash window.
            "best" selects the best smoothed value (extremum, per trend
            direction); "first" selects the first smoothed point after the wash.
        parameters: List of parameters to analyze.
    """

    smooth_window: int = 30
    pre_smooth_window: int = 15
    n_obs_mean: int = 15
    before_wash_mode: str = "worst"
    after_wash_mode: str = "best"
    parameters: list[WashParameter] = field(default_factory=lambda: list(DEFAULT_PARAMETERS))


@dataclass
class WashEvent:
    """Result for a single wash event on a single flight parameter.

    Attributes:
        engine_id: Engine identifier
        event_index: Cumulative event index (starting from 1)
        maint_datetime: Wash event timestamp
        ata_code: ATA code of the event
        parameter: The analyzed flight parameter
        mean_before: Worst smoothed value in last N obs before wash
        mean_after: Best smoothed value in first N obs after wash
        delta: After minus before (sign depends on trend direction)
        time_loss_of_efficiency: Timestamp when wash effect wore off, or None
        cycles_loss_of_efficiency: Number of cycles the wash effect lasted, or None
        hours_loss_of_efficiency: Number of hours the wash effect lasted, or None
    """

    engine_id: str
    event_index: int
    maint_datetime: Optional[datetime]
    ata_code: Optional[str]
    parameter: WashParameter
    mean_before: float
    mean_after: float
    delta: float
    time_loss_of_efficiency: Optional[datetime] = None
    cycles_loss_of_efficiency: Optional[int] = None
    hours_loss_of_efficiency: Optional[int] = None

    @property
    def has_loss(self) -> bool:
        """Whether a loss-of-efficiency point was detected."""
        return self.time_loss_of_efficiency is not None

    @property
    def days_loss_of_efficiency(self) -> Optional[int]:
        """Days between maintenance and loss-of-efficiency, or None."""
        if self.has_loss and self.maint_datetime is not None:
            return (self.time_loss_of_efficiency - self.maint_datetime).days
        return None


@dataclass(frozen=True)
class PlotPoint:
    """A single point on a plot curve. `value` is None for points where no
    smoothed value is available (e.g. wash anchors at the very start of a series)."""

    flight_datetime: datetime
    value: Optional[float] = None


@dataclass(frozen=True)
class PlotCurve:
    """A labeled sequence of points for a single engine.

    Attributes:
        kind: Curve kind — "raw", "smooth", or "smooth_custom".
        engine_id: Engine identifier.
        points: Ordered points (one per flight).
    """

    kind: str
    engine_id: str
    points: tuple[PlotPoint, ...]


@dataclass(frozen=True)
class PlotSegment:
    """A horizontal reference segment with a constant value over a time range."""

    start_datetime: datetime
    end_datetime: datetime
    value: float


@dataclass(frozen=True)
class WashEventMarkers:
    """Marker points associated with a single wash event.

    Attributes:
        engine_id: Engine identifier.
        event_index: Cumulative event index (1-based) within the engine.
        wash_event_point: The wash itself, anchored to the first flight on/after maint_datetime.
        before_segment: Horizontal reference for the pre-wash window (last n_obs_mean
            flights of the previous segment), valued at mean_before.
        after_segment: Horizontal reference for the post-wash window (first n_obs_mean
            flights of the current segment), valued at mean_after.
        before_value_point: Flight inside the pre-wash window whose smoothed value
            equals mean_before (the extremum the algorithm picked).
        after_value_point: Flight inside the post-wash window whose smoothed value
            equals mean_after.
        loss_of_efficiency_point: First flight where the smoothed value returns
            to the pre-wash threshold zone, or None.
    """

    engine_id: str
    event_index: int
    wash_event_point: PlotPoint
    before_segment: Optional[PlotSegment] = None
    after_segment: Optional[PlotSegment] = None
    before_value_point: Optional[PlotPoint] = None
    after_value_point: Optional[PlotPoint] = None
    loss_of_efficiency_point: Optional[PlotPoint] = None


@dataclass(frozen=True)
class WashPlot:
    """Chart-ready data for a wash-effect plot.

    Attributes:
        curves: Flat list of curves across all engines (3 per engine: raw / smooth / smooth_custom).
        markers: Flat list of per-wash marker bundles across all engines.
    """

    curves: tuple[PlotCurve, ...]
    markers: tuple[WashEventMarkers, ...]


@dataclass
class WashEventSummary:
    """Summary for a single wash event across all analyzed parameters.

    Groups per-parameter WashEvent results by wash identity (engine_id and event_index).

    Attributes:
        engine_id: Engine identifier.
        event_index: Cumulative event index (starting from 1).
        maint_datetime: Maintenance event timestamp.
        ata_code: ATA code of the maintenance event.
        results: Per-parameter WashEvent results for this wash.
    """

    engine_id: str
    event_index: int
    maint_datetime: Optional[datetime]
    ata_code: Optional[str]
    results: list[WashEvent]
