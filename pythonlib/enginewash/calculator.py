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
from .models import FlightRecord, MaintenanceRecord, WashConfig, WashEvent, WashEventSummary, WashParameter
from .smoothing import smooth_series
from collections import OrderedDict


class WashCalculator:
    """Calculate engine wash effects from flight and maintenance data.

    Implements the full processing pipeline:
      1. Anchor wash events to flight records
      2. Segment time series by wash events (cumulative event index)
      3. Smooth parameter values per segment
      4. Compute before/after wash deltas
      5. Detect loss-of-efficiency points

    Usage:

        calc = WashCalculator(config=WashConfig())
        summaries = calc.process(
            flights=[FlightRecord(...)],
            maintenance=[MaintenanceRecord(...)],
            parameter=EGTHDM,
        )
        # summaries — list of WashEventSummary, each containing per-parameter WashEvents
    """

    def __init__(self, config: WashConfig | None = None):
        self.config = config or WashConfig()

    def process(
        self,
        flights: list[FlightRecord],
        maintenance: list[MaintenanceRecord],
        parameter: WashParameter,
        utilization_df: pd.DataFrame | None = None,
    ) -> list[WashEventSummary]:
        """Run the full wash-effect analysis for one parameter.

        Args:
            flights: Flight records, one per flight.
            maintenance: Wash/maintenance events.
            parameter: Parameter configuration.
            utilization_df: Optional utilization data (engine_id, flight_datetime,
                tac, tah) for future cycle/hour enrichment. Currently unused.

        Returns:
            List of WashEventSummary, one per wash event.
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
        _df, events = self._compute_deltas(df, parameter)
        return self._build_summaries(events)

    def process_all(
        self,
        flights: list[FlightRecord],
        maintenance: list[MaintenanceRecord],
        parameters: list[WashParameter] | None = None,
        utilization_df: pd.DataFrame | None = None,
    ) -> list[WashEventSummary]:
        """Run wash-effect analysis for all configured parameters and merge.

        Processes each parameter independently, then groups events into
        summaries keyed by (engine_id, event_index).

        Args:
            flights: Flight records (see process() for schema).
            maintenance: Wash/maintenance events (see process() for schema).
            parameters: Parameters to analyze. Defaults to config.parameters.
            utilization_df: Optional utilization data for future cycle/hour
                enrichment. Currently unused.

        Returns:
            List of WashEventSummary items with WashEvent results for each parameter.
        """
        params = parameters or self.config.parameters
        all_events: list[WashEvent] = []

        for param in params:
            summaries = self.process(
                flights=flights,
                maintenance=maintenance,
                parameter=param,
                utilization_df=utilization_df,
            )
            for s in summaries:
                all_events.extend(s.results)

        return self._build_summaries(all_events)

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
            df["float_value_smooth"] = np.nan

        # Where pre-smoothed values are missing, fill with a running mean of raw values
        missing = df["float_value_smooth"].isna()
        if missing.any():
            smoothed_raw = smooth_series(
                df.loc[missing, "float_value"],
                window=self.config.pre_smooth_window,
            )
            df.loc[missing, "float_value_smooth"] = smoothed_raw

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

                # Build event record — convert pandas types to stdlib
                wash_row = df.loc[curr_mask & (df["event"] == 1)]
                maint_dt = wash_row["maint_datetime"].iloc[0] if len(wash_row) > 0 else None
                maint_dt = maint_dt.to_pydatetime() if pd.notna(maint_dt) else None
                ata = wash_row["ata_code"].iloc[0] if len(wash_row) > 0 else None

                time_loe_dt = None
                if time_loe is not None:
                    time_loe_dt = pd.Timestamp(time_loe).to_pydatetime()

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
                        time_loss_of_efficiency=time_loe_dt,
                    )
                )

        return df, events

    @staticmethod
    def _build_summaries(events: list[WashEvent]) -> list[WashEventSummary]:
        """Group WashEvents into per-wash summaries."""

        groups: OrderedDict[tuple[str, int], list[WashEvent]] = OrderedDict()
        for ev in events:
            key = (ev.engine_id, ev.event_index)
            groups.setdefault(key, []).append(ev)

        summaries = []
        for (engine_id, event_index), group in groups.items():
            first = group[0]
            summaries.append(
                WashEventSummary(
                    engine_id=engine_id,
                    event_index=event_index,
                    maint_datetime=first.maint_datetime,
                    ata_code=first.ata_code,
                    results=group,
                )
            )
        return summaries
