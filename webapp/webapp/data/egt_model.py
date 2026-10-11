"""Shared dashboard defaults for the enhanced EGT indication model."""

# Defaults for the enhanced (EGTHDM + DEGT + decline) failure model, matching
# the tuned run in enhanced_baseline.ipynb.
DEFAULT_MODEL_PARAMS = {
    "lookback_cycles": 10,
    "egthdm_threshold": 4.85,
    "degt_threshold": 2.70,
    "smoothing_window": 26,
    "decline_window_days": 5.0,
    "decline_min_span_days": 2.0,
    "decline_min_points": 5,
    "decline_threshold": 4.0,
    "decline_min_downward_fraction": 0.75,
    "decline_min_r2": 0.50,
}
