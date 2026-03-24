---

Engine Wash Effect Analysis

Entry Point — enginewash_workspaceMod.R

When the user clicks "Calculate", the module runs three parameters in a loop (enginewash_workspaceMod.R:582-589):

┌───────────┬──────────────┬────────────┬────────────────────────────────────┐
│ Parameter │ Flight Phase │ Cartoonist │ Meaning                            │
├───────────┼──────────────┼────────────┼────────────────────────────────────┤
│ GWFM      │ CRUISE       │ -1         │ Fuel flow — lower is better        │
├───────────┼──────────────┼────────────┼────────────────────────────────────┤
│ DEGT      │ CRUISE       │ -1         │ Differential EGT — lower is better │
├───────────┼──────────────┼────────────┼────────────────────────────────────┤
│ EGTHDM    │ TAKEOFF      │ +1         │ EGT margin — higher is better      │
└───────────┴──────────────┴────────────┴────────────────────────────────────┘

Each iteration runs CalculatorHistory_v2$process_history(...) and the results are joined into a single event table (df_event).

---

Processing Pipeline — CalculatorHistory_v2.R

Step 1 — Data load (upload_and_process_wash_data, line 102)

Pulls three things from the DB:

- engine_raw_output_mv — raw per-flight parameter values
- s7_mdb.engine_smooth — pre-smoothed values from a DB materialized view
- ecmapp.maintenance — wash events filtered by ATA codes (206/207/209)

Wash events are then "anchored" to flight records: each wash is attached to the first flight after the maintenance datetime by setting
event = 1 on that row.

Step 2 — Event segmentation (process_event, line 313)

event_cum = cumsum(event) — splits each engine's time series into segments: 0 = pre-first-wash, 1 = between wash 1 and 2, etc.

Step 3 — Smoothing (process_params_smooth, line 337)

Within each segment, applies a centered running mean (default window = 30 flights) via caTools::runmean() to produce
float_value_smooth_custom. Falls back to raw float_value where the DB smooth is missing.

Step 4 — Wash delta calculation (process_params_mean, line 371)

This is the core effect measurement. For each segment after a wash:

- mean_float_value_custom_before_wash = worst value in last N observations of the previous segment (the cartoonist sign controls whether
  "worst" = min or max)
- mean_float_value_custom_after_wash = best value in first N observations of the current segment
- delta_float_value_custom = after − before (positive = improvement for EGTHDM; negative = improvement for GWFM/DEGT)

Step 5 — Loss of Efficiency detection (still in process_params_mean)

After the wash, the code tracks when the benefit wears off. "Loss of efficiency" is defined as the first flight where the smoothed value
returns to within threshold of the pre-wash level:

cartoonist _ float_value_smooth_custom <= cartoonist _ mean_before_wash + threshold

The timestamp of this crossing is stored as time*loss_of_efficiency. Everything after that point has mean*\*\_series set to NA (stops the
reference lines in the chart).

Step 6 — Utilization enrichment (process_df_event, line 694)

Joins the event table against s7.fake_amos_ac_utilization to look up TAH (total air hours) and TAC (total air cycles) at two points: wash
date and loss-of-efficiency date. The difference gives:

cyc_loss_off_efficiency = tac_at_loe - tac_at_wash # cycles the benefit lasted
hrs_loss_off_efficiency = (tah_at_loe - tah_at_wash) / 60

---

Output

The module produces two views:

1. Event table (enginewash_details_table) — one row per wash event, columns like delta_EGTHDM_TAKEOFF, cyc_loe_EGTHDM_TAKEOFF,
   hrs_loe_GWFM_CRUISE, etc., color-coded diverging from zero.
2. Detail chart (enginewash_details_plot_hc) — for a selected wash, shows visualize_by_enginehc_hc_v02() (highcharter): raw scatter + DB
   smooth + custom smooth + green horizontal lines for before/after wash means + green vertical line at wash date + red vertical line at
   loss-of-efficiency. One chart per parameter.
3. Summary modal — violin + jitter plot of any delta or LoE metric grouped by ATA code.

---

Key Design Note: cartoonist parameter

The cartoonist flag (+1 or -1) is a generalization added in v2 that makes the before/after measurement direction-aware. For EGTM (higher =
better), it takes min(last N before) and max(first N after). For fuel flow (lower = better), it's the reverse. This is what allows the
same class to handle parameters with opposite "good direction".

---

What the violin plot shows for delta_EGTHDM_TAKEOFF × ata_code = 330

What ata_code is in df_event

ata_code is propagated from the maintenance record to each wash event row. It's the ATA chapter
of the wash work order — 330 would be a specific maintenance task type (alongside the 206/207/209
codes used as filters when querying). Every row in df_event carries the ATA code of the wash
that triggered that segment.

What delta_EGTHDM_TAKEOFF is per row

Each row = one wash event on one engine. The column holds:

delta = mean(first N smoothed values after wash) − mean(last N smoothed values before wash)

For EGTHDM (higher = better), a positive delta = the wash improved EGT margin.

What the violin for ata_code = 330 shows

The plot takes all wash events where ata_code == "330" and draws:

- Violin shape — the kernel density distribution of delta_EGTHDM_TAKEOFF across all those events.
  Wide = many events landed at that delta value; narrow = few.
- Crossbar (stat_summary(fun="mean")) — a horizontal bar at the mean delta across all 330-coded
  washes.
- Jitter dots — individual wash events scattered over the violin, so you can see the raw scatter
  and spot outliers.

---

What parameters need utilization data?

Without utilization data (utilization_df=None):

Per parameter (suffixed \_GWFM_CRUISE, \_DEGT_CRUISE, \_EGTHDM_TAKEOFF):

- delta\_{suffix} — before/after wash improvement
- mean\_{suffix}\_before_wash — worst smoothed value in last N obs before wash
- mean\_{suffix}\_after_wash — best smoothed value in first N obs after wash
- date*loe*{suffix} — timestamp when the benefit wore off (from detection, no utilization needed)

Plus the key columns from the time-series df: float_value_smooth_custom, mean_before_wash,
mean_after_wash, event_loss_of_efficiency, efficient_treatment.

Requires utilization data:

- cyc*loe*{suffix} — cycles the wash benefit lasted (TAC at LoE − TAC at wash)
- hrs*loe*{suffix} — hours the benefit lasted (TAH difference / 60)
- days*loe*{suffix} — days between wash and LoE (this one is interesting: it's computed in
  \_compute_utilization but only uses timestamps, not TAH/TAC)
