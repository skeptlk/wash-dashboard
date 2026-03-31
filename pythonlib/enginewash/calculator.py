"""Engine wash effect calculator.

Ported from old ECM portal R code to Python.
This is a pure computation library — it takes lists of dataclasses as input
and returns results. Database access is the caller's responsibility.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd

from .detection import compute_wash_means, detect_loss_of_efficiency
from .models import FlightRecord, MaintenanceRecord, WashConfig, WashEvent, WashParameter, WashResult
from .smoothing import smooth_series


class WashCalculator:
    """Calculate engine wash effects from flight and maintenance data.

    Implements the full processing pipeline:
      1. Anchor wash events to flight records
      2. Segment time series by wash events (cumulative event index)
      3. Smooth parameter values per segment
      4. Compute before/after wash deltas
      5. Detect loss-of-efficiency points

    Usage::

        calc = WashCalculator(config=WashConfig())
        result = calc.process(
            flights=[FlightRecord(...)],
            maintenance=[MaintenanceRecord(...)],
            parameter=EGTHDM,
        )
        # result.df        — annotated time series
        # result.events    — list of WashEvent
        # result.df_event  — summary DataFrame
    """

    def __init__(self, config: WashConfig | None = None):
        self.config = config or WashConfig()

    def process(
        self,
        flights: list[FlightRecord],
        maintenance: list[MaintenanceRecord],
        parameter: WashParameter,
    ) -> WashResult:
        """Run the full wash-effect analysis for one parameter.

        Args:
            flights: Flight records, one per flight.
            maintenance: Wash/maintenance events.
            parameter: Parameter configuration.

        Returns:
            WashResult with annotated DataFrame, events list, and summary.
        """
        flights_df = pd.DataFrame([dataclasses.asdict(f) for f in flights])
        maintenance_df = (
            pd.DataFrame([dataclasses.asdict(m) for m in maintenance])
            if maintenance
            else pd.DataFrame(columns=["engine_id", "maint_datetime", "ata_code"])
        )
        df = self._prepare_data(flights_df, maintenance_df)
        df = self._segment_events(df)
        df = self._apply_smoothing(df, parameter)
        df, events = self._compute_deltas(df, parameter)
        df_event = self._build_event_table(events, parameter)

        return WashResult(df=df, events=events, df_event=df_event)

    def process_all(
        self,
        flights: list[FlightRecord],
        maintenance: list[MaintenanceRecord],
        parameters: list[WashParameter] | None = None,
    ) -> WashResult:
        """Run wash-effect analysis for all configured parameters and merge.

        Processes each parameter independently, then joins event tables
        into a single summary (one row per wash, columns for each parameter).

        Args:
            flights: Flight records (see process() for schema).
            maintenance: Wash/maintenance events (see process() for schema).
            parameters: Parameters to analyze. Defaults to config.parameters.

        Returns:
            WashResult with merged df_event across all parameters.
        """
        params = parameters or self.config.parameters
        all_events: list[WashEvent] = []
        event_dfs: list[pd.DataFrame] = []
        last_df = pd.DataFrame()

        for param in params:
            result = self.process(
                flights=flights,
                maintenance=maintenance,
                parameter=param,
            )
            all_events.extend(result.events)
            if not result.df_event.empty:
                event_dfs.append(result.df_event)
            last_df = result.df

        if not event_dfs:
            return WashResult(
                df=last_df,
                events=all_events,
                df_event=pd.DataFrame(),
            )

        # Merge event tables on common keys
        merge_keys = ["engine_id", "event_index", "maint_datetime", "ata_code"]
        merged = event_dfs[0]
        for edf in event_dfs[1:]:
            merged = merged.merge(edf, on=merge_keys, how="outer")

        return WashResult(df=last_df, events=all_events, df_event=merged)

    def _prepare_data(
        self, flights_df: pd.DataFrame, maintenance_df: pd.DataFrame
    ) -> pd.DataFrame:
        """Join flights with maintenance events, anchoring washes to flights.

        Each wash is attached to the first flight after the maintenance datetime.
        """
        df = flights_df.copy()
        df["flight_datetime"] = pd.to_datetime(df["flight_datetime"])
        df = df.sort_values(["engine_id", "flight_datetime"]).reset_index(drop=True)

        if "float_value_smooth" not in df.columns:
            df["float_value_smooth"] = df["float_value"]

        # Fill missing smooth with raw; infer_objects suppresses pandas FutureWarning
        # about silent dtype downcasting during fillna
        df["float_value_smooth"] = df["float_value_smooth"].fillna(df["float_value"]).infer_objects(copy=False)

        # Mark wash events
        df["event"] = 0
        df["ata_code"] = None
        df["maint_datetime"] = pd.NaT

        maint = maintenance_df.copy()
        maint["maint_datetime"] = pd.to_datetime(maint["maint_datetime"])

        for _, wash in maint.iterrows():
            eid = wash["engine_id"]
            mdt = wash["maint_datetime"]
            ata = wash.get("ata_code", None)

            engine_mask = df["engine_id"] == eid
            after_mask = engine_mask & (df["flight_datetime"] >= mdt)

            if after_mask.any():
                first_idx = df.loc[after_mask, "flight_datetime"].idxmin()
                df.loc[first_idx, "event"] = 1
                df.loc[first_idx, "ata_code"] = ata
                df.loc[first_idx, "maint_datetime"] = mdt

        return df

    def _segment_events(self, df: pd.DataFrame) -> pd.DataFrame:
        """Create cumulative event index per engine.

        event_cum splits each engine's time series into segments:
        0 = pre-first-wash, 1 = between wash 1 and 2, etc.
        """
        df = df.sort_values(["engine_id", "flight_datetime"]).reset_index(drop=True)
        df["event_cum"] = df.groupby("engine_id")["event"].cumsum()
        return df

    def _apply_smoothing(
        self, df: pd.DataFrame, parameter: WashParameter
    ) -> pd.DataFrame:
        """Apply centered running mean within each event segment per engine."""
        df["float_value_smooth_custom"] = np.nan

        for (eid, ecum), grp in df.groupby(["engine_id", "event_cum"]):
            smoothed = smooth_series(
                grp["float_value_smooth"],
                window=self.config.smooth_window,
                fallback=grp["float_value"],
            )
            df.loc[grp.index, "float_value_smooth_custom"] = smoothed

        return df

    def _compute_deltas(
        self, df: pd.DataFrame, parameter: WashParameter
    ) -> tuple[pd.DataFrame, list[WashEvent]]:
        """Compute before/after deltas and detect loss-of-efficiency."""
        events: list[WashEvent] = []

        df["mean_before_wash"] = np.nan
        df["mean_after_wash"] = np.nan
        df["delta"] = np.nan
        df["event_loss_of_efficiency"] = 0
        df["time_loss_of_efficiency"] = pd.NaT
        df["efficient_treatment"] = np.nan

        cart = parameter.direction

        for eid, eng_df in df.groupby("engine_id"):
            max_seg = int(eng_df["event_cum"].max())

            for seg in range(1, max_seg + 1):
                prev_mask = (df["engine_id"] == eid) & (df["event_cum"] == seg - 1)
                curr_mask = (df["engine_id"] == eid) & (df["event_cum"] == seg)

                prev_smooth = df.loc[prev_mask, "float_value_smooth_custom"].values
                curr_smooth = df.loc[curr_mask, "float_value_smooth_custom"].values
                curr_times = df.loc[curr_mask, "flight_datetime"].values

                if len(prev_smooth) == 0 or len(curr_smooth) == 0:
                    continue

                mean_before, mean_after, delta = compute_wash_means(
                    prev_smooth, curr_smooth, self.config.n_obs_mean, cart
                )

                # Store on all rows of current segment
                df.loc[curr_mask, "mean_before_wash"] = mean_before
                df.loc[curr_mask, "mean_after_wash"] = mean_after
                df.loc[curr_mask, "delta"] = delta

                # Detect loss of efficiency
                time_loe = detect_loss_of_efficiency(
                    curr_smooth,
                    curr_times,
                    mean_before,
                    parameter.threshold,
                    cart,
                )

                if time_loe is not None:
                    loe_mask = curr_mask & (df["flight_datetime"] >= time_loe)
                    first_loe = curr_mask & (df["flight_datetime"] == time_loe)
                    df.loc[first_loe, "event_loss_of_efficiency"] = 1
                    df.loc[curr_mask, "time_loss_of_efficiency"] = time_loe

                    # Mark efficient vs inefficient treatment
                    df.loc[curr_mask & (df["flight_datetime"] <= time_loe), "efficient_treatment"] = 1
                    df.loc[curr_mask & (df["flight_datetime"] >= time_loe), "efficient_treatment"] = 0

                    # Truncate mean series after loss point
                    df.loc[loe_mask, "mean_before_wash"] = np.nan
                    df.loc[loe_mask, "mean_after_wash"] = np.nan
                else:
                    df.loc[curr_mask, "efficient_treatment"] = 1

                # Build event record
                wash_row = df.loc[curr_mask & (df["event"] == 1)]
                maint_dt = wash_row["maint_datetime"].iloc[0] if len(wash_row) > 0 else pd.NaT
                ata = wash_row["ata_code"].iloc[0] if len(wash_row) > 0 else None

                events.append(
                    WashEvent(
                        engine_id=str(eid),
                        event_index=seg,
                        maint_datetime=maint_dt,
                        ata_code=ata,
                        parameter=parameter,
                        mean_before=mean_before,
                        mean_after=mean_after,
                        delta=delta,
                        time_loss_of_efficiency=time_loe,
                    )
                )

        return df, events

    def _build_event_table(
        self,
        events: list[WashEvent],
        parameter: WashParameter,
    ) -> pd.DataFrame:
        """Build summary DataFrame from wash events."""
        if not events:
            return pd.DataFrame()

        suffix = parameter.suffix

        records = []
        for ev in events:
            days_loe = (
                (ev.time_loss_of_efficiency - ev.maint_datetime).days
                if ev.has_loss and pd.notna(ev.maint_datetime)
                else None
            )
            rec = {
                "engine_id": ev.engine_id,
                "event_index": ev.event_index,
                "maint_datetime": ev.maint_datetime,
                "ata_code": ev.ata_code,
                f"delta_{suffix}": ev.delta,
                f"mean_{suffix}_before_wash": ev.mean_before,
                f"mean_{suffix}_after_wash": ev.mean_after,
                f"date_loe_{suffix}": ev.time_loss_of_efficiency,
                f"days_loe_{suffix}": days_loe,
            }
            records.append(rec)

        return pd.DataFrame(records)
