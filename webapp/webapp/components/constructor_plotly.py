"""Assemble acknowledged parameter chunks without retransmitting earlier rows."""

import plotly.graph_objects as go
import reflex as rx
from reflex.vars.base import Var
from reflex.vars.function import FunctionStringVar

from .trend_plotly import TrendPlotly

_CONSTRUCTOR_FIGURE_JS = """
function constructorFigure(ref, chunk, generation, offset, dataGeneration) {
    const previous = ref.current;
    if (previous && previous.generation === generation && previous.chunk === chunk) {
        return previous.figure;
    }
    const data = previous && previous.generation === generation
        ? previous.figure.data.slice(0, offset) : [];
    const cache = previous && previous.dataGeneration === dataGeneration
        ? previous.cache : new Map();
    const incoming = (chunk.data || []).map(trace => {
        // Reflex strips Plotly's uid during serialization; meta survives.
        const key = trace.meta;
        const uid = key && Array.from(key, c => c.codePointAt(0).toString(16)).join('-');
        const result = key && cache.has(key)
            ? {...cache.get(key), ...trace, uid}
            : key ? {...trace, uid} : trace;
        if (key) cache.set(key, result);
        return result;
    });
    const figure = {...chunk, data: [...data, ...incoming]};
    ref.current = {generation, dataGeneration, cache, chunk, figure};
    return figure;
}
"""


class ConstructorPlotly(TrendPlotly):
    # These callbacks run after React-Plotly installs the current handlers.
    # plotly_afterplot can still invoke the previous render's acknowledgement.
    on_initialized: rx.EventHandler[lambda: []]
    on_update: rx.EventHandler[lambda: []]

    def add_imports(self):
        return {**super().add_imports(), "react": ["useRef"]}

    def add_hooks(self):
        return ["const constructorFigureRef = useRef(null);"]

    def add_custom_code(self):
        return [*super().add_custom_code(), _CONSTRUCTOR_FIGURE_JS]

    @classmethod
    def create(cls, *children, **props):
        props["data"] = (
            FunctionStringVar("constructorFigure")
            .call(
                Var("constructorFigureRef"),
                props["data"],
                props.pop("generation"),
                props.pop("offset"),
                props.pop("data_generation"),
            )
            .to(go.Figure)
        )
        return super().create(*children, **props)
