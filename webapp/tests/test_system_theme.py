"""Verify the browser listener survives manual toggles and cleans up."""

import shutil
import subprocess

import pytest

from webapp.components.system_theme import SystemTheme


def test_device_theme_overrides_saved_and_manual_choices():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required")
    subprocess.run(
        [
            node,
            "-e",
            """
const assert = require('node:assert/strict');
let theme = 'dark';
let cleanup;
let listener;
const storage = new Map([['theme', 'dark']]);
const localStorage = {setItem: (key, value) => storage.set(key, value)};
const useTheme = () => ({setTheme: value => {theme = value;}});
const useEffect = callback => {cleanup = callback();};
const preference = {
    matches: false,
    addEventListener: (event, callback) => {
        assert.equal(event, 'change');
        listener = callback;
    },
    removeEventListener: (event, callback) => {
        assert.equal(event, 'change');
        assert.equal(callback, listener);
        listener = null;
    },
};
const window = {matchMedia: query => {
    assert.equal(query, '(prefers-color-scheme: dark)');
    return preference;
}};
"""
            + "\n".join(SystemTheme.create().add_hooks())
            + """
assert.equal(theme, 'system');
assert.equal(storage.get('theme'), 'system');
const resolved = () => theme === 'system'
    ? (preference.matches ? 'dark' : 'light') : theme;
assert.equal(resolved(), 'light');
// Manually selecting light must not block the next OS switch to dark.
theme = 'light';
preference.matches = true;
listener();
assert.equal(resolved(), 'dark');
// The same applies when switching back to light after a manual dark choice.
theme = 'dark';
preference.matches = false;
listener();
assert.equal(resolved(), 'light');
// Subsequent toggles still work without a rerender or another subscription.
theme = 'dark';
assert.equal(resolved(), 'dark');
assert.equal(typeof listener, 'function');
cleanup();
assert.equal(listener, null);
""",
        ],
        check=True,
    )
