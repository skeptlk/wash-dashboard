# Python Library Review

## Critical Bug

### `compute_wash_means` logic is inverted (`detection.py:42-47`)

For `direction=-1` (lower-is-better, e.g. GWFM fuel flow), the code takes `min(tail)` as
`mean_before` and `max(head)` as `mean_after` — the opposite of the stated spec
("worst before / best after" in README and `WashEvent` docstring).

Real-world example — fuel flow degrading before wash: `[10.0, 10.5, 11.0, 11.5, 12.0]`,
after wash: `[9.0, 9.2, 9.5, 10.0, 10.5]`:

|               | Code (inverted)         | Correct                  |
|---------------|-------------------------|--------------------------|
| `mean_before` | 10.0 (best pre-wash)    | 12.0 (degraded state)    |
| `mean_after`  | 10.5 (worst post-wash)  | 9.0 (best post-wash)     |
| `delta`       | **+0.5 (wash = worse!)** | -3.0 (correct)          |

Same inversion applies to `direction=+1`. Fix:

```python
# direction == -1 (lower is better)
mean_before = float(np.max(tail_valid))   # worst = most degraded
mean_after  = float(np.min(head_valid))   # best = most improved

# direction == +1 (higher is better)
mean_before = float(np.min(tail_valid))   # worst = most degraded
mean_after  = float(np.max(head_valid))   # best = most improved
```

**Secondary effect:** LoE detection is also wrong — `mean_before` is used as the pre-wash
reference level in `detect_loss_of_efficiency`. Using the engine's best state instead of its
degraded state makes LoE trigger too early.

Tests that need updating after fix: `test_downward_trend`, `test_upward_trend` in
`tests/test_detection.py` (assert values will flip), plus `test_single_wash_downward_trend`
and `test_single_wash_upward_trend` in `tests/test_calculator.py`.

---

## Architectural Issues

### Internal DataFrame is computed and immediately discarded (`calculator.py:73`)

```python
_df, events = self._compute_deltas(df, parameter)
return self._build_summaries(events)   # _df thrown away
```

`_compute_deltas` writes substantial output onto `_df`: `mean_before_wash`,
`mean_after_wash`, `delta`, `efficient_treatment`, `event_loss_of_efficiency`,
`time_loss_of_efficiency`. None of it reaches the caller. The R implementation likely
returned this annotated DataFrame; the Python port lost it but kept all the column-writing
code. Decision needed: either expose `_df` from `process()`, or delete the dead DataFrame
assignments.

### `process_all` builds summaries, deconstructs, then rebuilds (`calculator.py:103-111`)

```python
summaries = self.process(...)          # calls _build_summaries() internally
for s in summaries:
    all_events.extend(s.results)       # unpacks the summaries back to WashEvent
return self._build_summaries(all_events)  # rebuilds summaries
```

Fix: extract a private `_process_events()` returning `list[WashEvent]` and have both
`process()` and `process_all()` call it. `process()` wraps it with `_build_summaries()`;
`process_all()` collects raw events across parameters then calls `_build_summaries()` once.

---

## Logic Issues

### `efficient_treatment` boundary overlap (`calculator.py:241-242`)

```python
df.loc[curr_mask & (df["flight_datetime"] <= time_loe), "efficient_treatment"] = 1
df.loc[curr_mask & (df["flight_datetime"] >= time_loe), "efficient_treatment"] = 0
```

The flight exactly at `time_loe` is set to `1` then immediately overwritten to `0`.
Presumably the LoE point should be `0` (inefficient), but the first condition should be
`< time_loe` to make the intent explicit rather than relying on write order.

### `_apply_smoothing` accepts `parameter` but ignores it (`calculator.py:170`)

GWFM is CRUISE-phase, EGTHDM is TAKEOFF-phase. A window of 30 TAKEOFF measurements
covers far more calendar time than 30 CRUISE measurements. The parameter argument is
accepted but never used — at minimum, smoothing windows should vary per flight phase.

---

## Incomplete / Misleading

### `utilization_df` is documented but not implemented

Both the README and `process()`/`process_all()` docstrings describe cycle/hour enrichment
via `utilization_df`, promising output columns `cyc_loe_*`, `hrs_loe_*`, `days_loe_*`.
The implementation comments it as "Currently unused." Either implement or remove from docs.

### `compute_wash_means` is misnamed

It returns `min`/`max` values, not averages. Rename to something like
`compute_wash_references` or `compute_wash_levels`.

### README shows the wrong API

Examples pass DataFrames to `process()`/`process_all()`, but the actual API takes
`list[FlightRecord]`. Also does not mention the `parameter_name` field added in the
`FlightRecord` fix. Needs a full rewrite of the Usage section.
