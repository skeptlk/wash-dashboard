# enginewash

Python library for calculating engine wash effects on aircraft engine parameters. Port of the `CalculatorHistory_v2` R6 class to pure Python.

## Structure

```
enginewash/
├── __init__.py             # Public API exports
├── models.py               # WashParameter, WashEvent, WashResult, enums, presets
├── smoothing.py            # Centered running mean (equivalent to caTools::runmean)
├── detection.py            # Before/after delta + loss-of-efficiency detection
└── calculator.py           # WashCalculator — full processing pipeline
```

## Processing pipeline

Same as the R implementation:

1. **Prepare** — anchor wash events to the first flight after each maintenance datetime
2. **Segment** — `event_cum = cumsum(event)` splits each engine's time series into segments (0 = pre-first-wash, 1 = between wash 1 and 2, etc.)
3. **Smooth** — centered running mean (default window = 30 flights) within each segment
4. **Compute deltas** — before-wash vs after-wash reference values using worst/best of last/first N observations
5. **Detect loss-of-efficiency** — find the first flight where the smoothed value returns to within threshold of the pre-wash level
6. **Build event table** — one row per wash with delta, LoE date, and optional utilization metrics (cycles/hours)

## Parameters

Three pre-configured engine parameters are included:

| Constant | Parameter | Flight Phase | Trend | Threshold | Meaning |
|----------|-----------|-------------|-------|-----------|---------|
| `GWFM` | GWFM | CRUISE | DOWN (-1) | 0.05 | Fuel flow — lower is better |
| `DEGT` | DEGT | CRUISE | DOWN (-1) | 2.0 | Differential EGT — lower is better |
| `EGTHDM` | EGTHDM | TAKEOFF | UP (+1) | 2.0 | EGT margin — higher is better |

The `TrendDirection` (cartoonist) makes the same algorithm work for parameters with opposite "good direction".

## Design

- **Pure Python** — no C/Cython bindings, no compilation step
- **DB-free** — takes pandas DataFrames as input; the caller handles data access
- **pandas/numpy** only runtime dependencies

## Install

```bash
cd pythonlib
pip install -e .
```

With dev dependencies (pytest):

```bash
pip install -e ".[dev]"
```

## Test

```bash
cd pythonlib
python -m pytest tests/ -v
```

## Usage

```python
import pandas as pd
from enginewash import WashCalculator, WashConfig, GWFM, DEGT, EGTHDM

# Flight records — one row per flight per engine
flights_df = pd.DataFrame({
    "engine_id":          [...],
    "flight_datetime":    [...],
    "float_value":        [...],  # raw parameter value
    "float_value_smooth": [...],  # pre-smoothed value (optional, falls back to raw)
})

# Maintenance wash events
maintenance_df = pd.DataFrame({
    "engine_id":      [...],
    "maint_datetime": [...],
    "ata_code":       [...],  # e.g. "206", "207", "209"
})

# Single parameter
calc = WashCalculator(WashConfig(smooth_window=30, n_obs_mean=15))
result = calc.process(flights_df, maintenance_df, parameter=GWFM)

result.df         # Full time series with smoothed values and annotations
result.events     # List of WashEvent objects
result.df_event   # Summary DataFrame (one row per wash)

# All three parameters at once — merges event tables
result = calc.process_all(flights_df, maintenance_df, parameters=[GWFM, DEGT, EGTHDM])
# result.df_event has columns: delta_GWFM_CRUISE, delta_DEGT_CRUISE, delta_EGTHDM_TAKEOFF, ...
```

### Custom parameters

```python
from enginewash import WashParameter, FlightPhase, TrendDirection

my_param = WashParameter(
    name="N1VIB",
    flight_phase=FlightPhase.CRUISE,
    trend_direction=TrendDirection.DOWN,
    threshold=0.5,
)
result = calc.process(flights_df, maintenance_df, parameter=my_param)
```

### Utilization enrichment

Pass a utilization DataFrame to get cycles/hours between wash and loss-of-efficiency:

```python
utilization_df = pd.DataFrame({
    "engine_id":      [...],
    "flight_datetime": [...],
    "tac":            [...],  # total air cycles
    "tah":            [...],  # total air hours (minutes)
})

result = calc.process(flights_df, maintenance_df, GWFM, utilization_df=utilization_df)
# result.df_event gains columns: cyc_loe_GWFM_CRUISE, hrs_loe_GWFM_CRUISE, days_loe_GWFM_CRUISE
```
