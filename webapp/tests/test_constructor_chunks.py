"""Exercise the exact browser chunk assembler, including rerenders and resets."""

import shutil
import subprocess

import pytest

from webapp.components.constructor_plotly import _CONSTRUCTOR_FIGURE_JS


def test_chunk_assembly():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required")
    subprocess.run(
        [
            node,
            "-e",
            _CONSTRUCTOR_FIGURE_JS
            + """
const assert = require('node:assert/strict');
const ref = {current: null};
const first = {data: [{name: 'EGTHDM'}], layout: {title: 'first'}};
assert.equal(constructorFigure(ref, first, 1, 0).data.length, 1);
// A React rerender must not duplicate observations.
assert.equal(constructorFigure(ref, first, 1, 0).data.length, 1);
const second = {data: [{name: 'GWFM'}], layout: {title: 'second'}};
const result = constructorFigure(ref, second, 1, 1);
assert.deepEqual(result.data.map(t => t.name), ['EGTHDM', 'GWFM']);
assert.equal(constructorFigure(ref, second, 1, 1), result);
// Zoom sends only layout; observations remain in the browser.
const zoom = {data: [], layout: {xaxis: {range: [1, 2]}}};
assert.equal(constructorFigure(ref, zoom, 1, 2).data.length, 2);
assert.deepEqual(ref.current.figure.layout.xaxis.range, [1, 2]);
// A new selection replaces all previous traces.
const changed = constructorFigure(ref, first, 2, 0);
assert.deepEqual(changed.data.map(t => t.name), ['EGTHDM']);
assert.deepEqual(first.data, [{name: 'EGTHDM'}]);
""",
        ],
        check=True,
    )
