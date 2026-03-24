"""Engine wash effect calculator for aircraft engine condition monitoring."""

from .calculator import WashCalculator
from .models import (
    DEGT,
    DEFAULT_PARAMETERS,
    EGTHDM,
    GWFM,
    FlightPhase,
    TrendDirection,
    WashConfig,
    WashEvent,
    WashParameter,
    WashResult,
)
from .smoothing import running_mean, smooth_series
from .detection import compute_wash_means, detect_loss_of_efficiency

__all__ = [
    "WashCalculator",
    "WashConfig",
    "WashParameter",
    "WashEvent",
    "WashResult",
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
]
