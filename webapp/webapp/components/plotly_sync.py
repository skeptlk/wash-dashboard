"""A Plotly subclass whose ``on_relayout`` reports the new x-axis range.

The stock ``reflex_components_plotly.Plotly`` fires ``on_relayout`` with no
arguments, so a rangeslider can't tell the backend which time window the user
selected. This subclass extracts ``xaxis.range[0]``/``[1]`` (and the autorange
flag) from the relayout event, letting a short pinned "navigator" chart drive a
separate, scrollable main chart.
"""

from __future__ import annotations

from reflex_base.components.component import field
from reflex_base.event import EventHandler
from reflex_base.vars.base import Var
from reflex_components_plotly.plotly import Plotly


def _relayout_xrange_signature(e0: Var):
    """Pull (x_start, x_end, autorange) out of a plotly relayout event.

    Plotly emits either ``xaxis.range[0]``/``xaxis.range[1]`` (rangeslider drag)
    or ``xaxis.range`` as a 2-element array (programmatic), and
    ``xaxis.autorange: true`` when reset — so we defend against all three.
    """
    e = f"({e0}||{{}})"
    r0 = (
        f"({e}['xaxis.range[0]']!==undefined?{e}['xaxis.range[0]']:"
        f"({e}['xaxis.range']?{e}['xaxis.range'][0]:undefined))"
    )
    r1 = (
        f"({e}['xaxis.range[1]']!==undefined?{e}['xaxis.range[1]']:"
        f"({e}['xaxis.range']?{e}['xaxis.range'][1]:undefined))"
    )
    return (
        Var(_js_expr=f"({r0}!==undefined?String({r0}):'')").to(str),
        Var(_js_expr=f"({r1}!==undefined?String({r1}):'')").to(str),
        Var(_js_expr=f"({e}['xaxis.autorange']===true)").to(bool),
    )


class RangeSyncPlotly(Plotly):
    """Plotly graph that reports its x-axis range on relayout."""

    on_relayout: EventHandler[_relayout_xrange_signature] = field(
        doc="Fired after a layout change; reports (x_start, x_end, autorange)."
    )


range_sync_plotly = RangeSyncPlotly.create
