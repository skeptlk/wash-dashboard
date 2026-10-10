"""Exercise the exact browser chunk assembler, including rerenders and resets."""

import shutil
import subprocess

import pytest

from webapp.components.constructor_plotly import _CONSTRUCTOR_FIGURE_JS


def test_constructor_page_builds_with_state_bindings():
    from webapp.pages.constructor import constructor_page

    assert constructor_page().render()


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
// Parameter changes retain arrays and change only subplot references.
const cachedRef = {current: null};
const readings = [10, 20, 30];
const initial = {data: [{meta: 'A:0', x: [1, 2, 3], y: readings, yaxis: 'y'}]};
constructorFigure(cachedRef, initial, 1, 0, 1);
const addition = {data: [
    {meta: 'A:0', yaxis: 'y'},
    {meta: 'B:0', x: [4], y: [40], yaxis: 'y3'},
]};
const added = constructorFigure(cachedRef, addition, 2, 0, 1);
assert.equal(added.data[0].y, readings);
assert.equal(added.data[0].uid, '41-3a-30');
const removal = {data: [{meta: 'B:0', yaxis: 'y'}]};
const removed = constructorFigure(cachedRef, removal, 3, 0, 1);
assert.deepEqual(removed.data[0].y, [40]);
assert.equal(removed.data[0].yaxis, 'y');
const restored = constructorFigure(cachedRef, {data: [{meta: 'A:0'}]}, 4, 0, 1);
assert.equal(restored.data[0].y, readings);
// Engine/date/smoothing changes invalidate the browser cache.
const fresh = constructorFigure(cachedRef, {data: [{meta: 'A:0', x: [9], y: [99]}]}, 5, 0, 2);
assert.deepEqual(fresh.data[0].y, [99]);
assert.equal(cachedRef.current.cache.has('B:0'), false);
""",
        ],
        check=True,
    )
