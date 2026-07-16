"""Engine wash effect calculator for aircraft engine condition monitoring."""

from .calculator import WashCalculator
from .models import (
    DEGT,
    DEFAULT_PARAMETERS,
    EGTHDM,
    GWFM,
    FlightPhase,
    FlightRecord,
    MaintenanceRecord,
    PlotCurve,
    PlotPoint,
    PlotSegment,
    TrendDirection,
    UtilizationRecord,
    WashConfig,
    WashEvent,
    WashEventMarkers,
    WashEventSummary,
    WashParameter,
    WashPlot,
)
from .smoothing import running_mean, smooth_series
from .detection import compute_wash_means, detect_loss_of_efficiency
from .egt_prediction import predict_egt_failure, predict_egt_failure_enhanced

__all__ = [
    "WashCalculator",
    "WashConfig",
    "WashParameter",
    "WashEvent",
    "WashEventSummary",
    "FlightRecord",
    "MaintenanceRecord",
    "UtilizationRecord",
    "FlightPhase",
    "TrendDirection",
    "GWFM",
    "DEGT",
    "EGTHDM",
    "DEFAULT_PARAMETERS",
    "running_mean",
    "smooth_series",
    "compute_wash_means",
    "detect_loss_of_efficiency",
    "predict_egt_failure",
    "predict_egt_failure_enhanced",
    "PlotPoint",
    "PlotCurve",
    "PlotSegment",
    "WashEventMarkers",
    "WashPlot",
]
