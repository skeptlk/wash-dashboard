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
from .models import (
    FlightRecord,
    MaintenanceRecord,
    UtilizationRecord,
    WashConfig,
    WashEvent,
    WashEventSummary,
    WashParameter,
    WashPlot,
)
from .plot import build_wash_plot
from .smoothing import smooth_series
from .utilization import UtilizationLookup, build_utilization_lookup, lookup_utilization
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
            maintenances=[MaintenanceRecord(...)],
            parameter=EGTHDM,
        )
        # summaries — list of WashEventSummary, each containing per-parameter WashEvents
    """

    def __init__(self, config: WashConfig | None = None):
        self.config = config or WashConfig()

    def _run_pipeline(
        self,
        flights: list[FlightRecord],
        maintenances: list[MaintenanceRecord],
        parameter: WashParameter,
        utilization_lookup: UtilizationLookup | None = None,
    ) -> tuple[list[tuple[str, pd.DataFrame]], list[WashEvent]]:
        """Run the full processing pipeline per engine; shared by `process` and `build_plot`.

        Returns a list of (engine_id, processed_df) pairs and the flat list of
        WashEvents across all engines.
        """
        flights_df = pd.DataFrame([dataclasses.asdict(f) for f in flights])
        maintenance_df = (
            pd.DataFrame([dataclasses.asdict(m) for m in maintenances])
            if maintenances
            else pd.DataFrame(columns=["engine_id", "maint_datetime", "ata_code"])
        )

        engine_results: list[tuple[str, pd.DataFrame]] = []
        all_events: list[WashEvent] = []

        if "engine_id" not in flights_df.columns:
            return engine_results, all_events

        for engine_id, eng_flights in flights_df.groupby("engine_id"):
            eng_maint = maintenance_df[maintenance_df["engine_id"] == engine_id]
            df = self._prepare_data(eng_flights, eng_maint)
            df["event_cum"] = df["event"].cumsum()
            df = self._apply_smoothing(df)
            events = self._compute_deltas(df, str(engine_id), parameter, utilization_lookup)
            engine_results.append((str(engine_id), df))
            all_events.extend(events)

        return engine_results, all_events

    def process(
        self,
        flights: list[FlightRecord],
        maintenances: list[MaintenanceRecord],
        parameter: WashParameter,
        utilization: list[UtilizationRecord] | None = None,
    ) -> list[WashEventSummary]:
        """Run the full wash-effect analysis for one parameter.

        Args:
            flights: Flight records, one per flight.
            maintenances: Wash/maintenance events.
            parameter: Parameter configuration.
            utilization: Optional engine utilization records. When provided,
                cycles_loss_of_efficiency and hours_loss_of_efficiency are calculated

        Returns:
            List of WashEventSummary, one per wash event.
        """
        lookup = build_utilization_lookup(utilization or [])
        _engine_dfs, events = self._run_pipeline(flights, maintenances, parameter, lookup)
        return self._build_summaries(events)

    def build_plot(
        self,
        flights: list[FlightRecord],
        maintenances: list[MaintenanceRecord],
        parameter: WashParameter,
    ) -> WashPlot:
        """Run the pipeline and assemble a chart-ready WashPlot.

        Three curves per engine (raw, first-pass smooth, per-segment
        second-pass smooth) plus one WashEventMarkers bundle per detected
        wash containing the wash event point, pre/post-wash mean reference
        segments, and (if detected) the loss-of-efficiency point.

        Args:
            flights: Flight records, one per flight.
            maintenances: Wash/maintenance events.
            parameter: Parameter configuration.

        Returns:
            A WashPlot with flat lists of curves and markers across all engines.
        """
        engine_dfs, events = self._run_pipeline(flights, maintenances, parameter)
        return build_wash_plot(engine_dfs, events, self.config.n_obs_mean)


    def process_all(
        self,
        flights: list[FlightRecord],
        maintenances: list[MaintenanceRecord],
        parameters: list[WashParameter] | None = None,
        utilization: list[UtilizationRecord] | None = None,
    ) -> list[WashEventSummary]:
        """Run wash-effect analysis for all configured parameters and merge.

        Processes each parameter independently, then groups events into
        summaries by engine_id and event_index.

        Args:
            flights: Flight records (see process() for schema).
            maintenances: Wash/maintenance events (see process() for schema).
            parameters: Parameters to analyze. Defaults to config.parameters.
            utilization: Optional engine utilization records (see process()).

        Returns:
            List of WashEventSummary items with WashEvent results for each parameter.
        """
        params = parameters or self.config.parameters
        lookup = build_utilization_lookup(utilization or [])
        all_events: list[WashEvent] = []

        for param in params:
            param_flights = [
                f for f in flights
                if f.parameter_name == param.name and f.flight_phase == param.flight_phase
            ]
            _engine_dfs, events = self._run_pipeline(
                param_flights, maintenances, param, lookup,
            )
            all_events.extend(events)

        return self._build_summaries(all_events)

    def _prepare_data(
        self, flights_df: pd.DataFrame, maintenance_df: pd.DataFrame
    ) -> pd.DataFrame:
        """Anchor wash events to flights for a single engine.

        Each wash is attached to the first flight after the maintenance datetime.
        """
        df = flights_df.copy()
        df["flight_datetime"] = pd.to_datetime(df["flight_datetime"])
        df = df.sort_values("flight_datetime").reset_index(drop=True)

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

        df["event"] = 0
        df["ata_code"] = None
        df["maint_datetime"] = pd.NaT

        if len(maintenance_df) == 0:
            return df

        maint = maintenance_df.copy()
        maint["maint_datetime"] = pd.to_datetime(maint["maint_datetime"])

        for _, wash in maint.iterrows():
            mdt = wash["maint_datetime"]
            ata = wash.get("ata_code", None)

            after_mask = df["flight_datetime"] >= mdt
            if after_mask.any():
                first_idx = df.index[after_mask][0]
                df.loc[first_idx, "event"] = 1
                df.loc[first_idx, "ata_code"] = ata
                df.loc[first_idx, "maint_datetime"] = mdt

        return df

    def _apply_smoothing(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply centered running mean within each event segment."""
        df["float_value_smooth_custom"] = np.nan

        for _, grp in df.groupby("event_cum"):
            smoothed = smooth_series(
                grp["float_value_smooth"],
                window=self.config.smooth_window,
                fallback=grp["float_value"],
            )
            df.loc[grp.index, "float_value_smooth_custom"] = smoothed

        return df

    def _compute_deltas(
        self,
        df: pd.DataFrame,
        engine_id: str,
        parameter: WashParameter,
        utilization_lookup: UtilizationLookup | None = None,
    ) -> list[WashEvent]:
        """Compute before/after deltas and detect loss-of-efficiency for one engine."""
        events: list[WashEvent] = []
        if df.empty:
            return events
        lookup: UtilizationLookup = utilization_lookup or {}

        seg_indices = df.groupby("event_cum").indices
        smooth_values = df["float_value_smooth_custom"].values
        time_values = df["flight_datetime"].values
        event_values = df["event"].values
        cart = parameter.direction
        max_seg = int(df["event_cum"].max())

        for seg in range(1, max_seg + 1):
            prev_idx = seg_indices.get(seg - 1)
            curr_idx = seg_indices.get(seg)
            if prev_idx is None or curr_idx is None or not len(prev_idx) or not len(curr_idx):
                continue

            prev_smooth = smooth_values[prev_idx]
            curr_smooth = smooth_values[curr_idx]
            curr_times = time_values[curr_idx]

            mean_before, mean_after, delta = compute_wash_means(
                prev_smooth, curr_smooth, self.config.n_obs_mean, cart
            )

            time_loe = detect_loss_of_efficiency(
                curr_smooth, curr_times, mean_before, parameter.threshold, cart,
            )

            # Maint metadata sits on the first flight of the segment (the anchor row)
            anchor_local = np.where(event_values[curr_idx] == 1)[0]
            maint_dt = None
            ata = None
            if len(anchor_local):
                anchor_row = df.iloc[curr_idx[anchor_local[0]]]
                mdt_raw = anchor_row["maint_datetime"]
                if pd.notna(mdt_raw):
                    maint_dt = mdt_raw.to_pydatetime()
                ata_raw = anchor_row["ata_code"]
                if pd.notna(ata_raw):
                    ata = ata_raw

            time_loe_dt = (
                pd.Timestamp(time_loe).to_pydatetime() if time_loe is not None else None
            )

            cyc_wash, hrs_wash = lookup_utilization(lookup, engine_id, maint_dt)
            cyc_loss, hrs_loss = lookup_utilization(lookup, engine_id, time_loe_dt)
            cycles_loe = (
                cyc_loss - cyc_wash if cyc_wash is not None and cyc_loss is not None else None
            )
            hours_loe = (
                int(round(hrs_loss - hrs_wash))
                if hrs_wash is not None and hrs_loss is not None
                else None
            )

            events.append(
                WashEvent(
                    engine_id=engine_id,
                    event_index=seg,
                    maint_datetime=maint_dt,
                    ata_code=ata,
                    parameter=parameter,
                    mean_before=mean_before,
                    mean_after=mean_after,
                    delta=delta,
                    time_loss_of_efficiency=time_loe_dt,
                    cycles_loss_of_efficiency=cycles_loe,
                    hours_loss_of_efficiency=hours_loe,
                )
            )

        return events

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
