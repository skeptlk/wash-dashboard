"""Shared Plotly component preserving source wall-clock timestamps."""

import plotly.graph_objects as go
import reflex as rx
from reflex.vars.function import FunctionStringVar
from reflex_components_plotly.plotly import Plotly

# Plotly.js 3.x treats numeric date coordinates as browser-local epoch times.
# Decode only X at the component boundary to preserve the source wall clock.
# Cache by figure identity so unrelated UI updates do not repeat the conversion.
_DATE_FIGURE_JS = """
const egtDateFigureCache = new WeakMap();
function egtDateFigure(figure) {
    if (!figure || typeof figure !== "object") return figure;
    const cached = egtDateFigureCache.get(figure);
    if (cached) return cached;
    const data = (figure.data || []).map(trace => {
        const encoded = trace.x;
        if (!encoded || encoded.dtype !== "f8" || !encoded.bdata) return trace;
        const bytes = Uint8Array.from(atob(encoded.bdata), c => c.charCodeAt(0));
        const view = new DataView(bytes.buffer);
        const x = Array.from({length: bytes.length / 8}, (_, i) => {
            const ms = view.getFloat64(i * 8, true);
            if (!Number.isFinite(ms)) return null;
            const whole = Math.floor(ms);
            const fraction = (ms - whole).toFixed(6).slice(2).replace(/0+$/, "");
            return new Date(whole).toISOString().slice(0, -1) + fraction;
        });
        return {...trace, x};
    });
    const result = {...figure, data};
    egtDateFigureCache.set(figure, result);
    return result;
}
"""


class TrendPlotly(Plotly):
    # Reflex's default Plotly handler discards the relayout payload.
    on_relayout: rx.EventHandler[lambda data: [data]]

    def add_custom_code(self) -> list[str]:
        return [*super().add_custom_code(), _DATE_FIGURE_JS]

    @classmethod
    def create(cls, *children, **props):
        if "data" in props:
            props["data"] = (
                FunctionStringVar("egtDateFigure").call(props["data"]).to(go.Figure)
            )
        return super().create(*children, **props)
