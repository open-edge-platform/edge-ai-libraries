# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Shared serving-state controls work without a running engine or DOM."""

from pathlib import Path
import shutil
import subprocess

import pytest


NODE = shutil.which("node")
CONSOLE = Path(__file__).resolve().parents[1] / "src" / "console"


@pytest.mark.skipif(NODE is None, reason="Node is needed for console JavaScript tests")
def test_serving_controls_show_pool_local_states_and_no_replacement_ui():
    script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
globalThis.esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
globalThis.t = (key, vars = {}) => key.replace(/\{(\w+)\}/g, (match, name) => vars[name] ?? match);
vm.runInThisContext(fs.readFileSync(process.argv[1], 'utf8') + '\nglobalThis.policy = SourceServing;');
const source = {id: 'video', name: '<video "1">', type: 'vector', enabled: true};
const status = {source_id: 'video', serving_state: 'SERVING', effective_state: 'SERVING', status: 'pending'};
const a = {id: 'A', name: 'Pool A', source_statuses: [status]};
const b = {id: 'B', source_statuses: [{...status, serving_state: 'DEPRECATED', effective_state: 'DEPRECATED'}]};
const lib = {name: 'library "A"', sources: [source, {id: 'content', type: 'object'}], asset_pools: [a, b], default_content_source_id: 'content'};
assert.equal(policy.bindings(lib, 'video').length, 2);
let html = policy.sourceBindings(lib, 'video');
assert.match(html, /data-serving-pool="A"/);
assert.match(html, /data-serving-pool="B"/);
assert.match(html, /data-serving-library="library &quot;A&quot;"/);
assert.match(html, /&lt;video &quot;1&quot;&gt;/);
assert.match(html, /value="SERVING" selected/);
assert.match(html, /value="DEPRECATED" selected/);
assert.equal(policy.control(lib, a, 'content'), '');
assert.equal(policy.control(lib, a, 'missing'), '');
assert.equal(policy.sourceBindings(lib, 'unattached'), '<span class="hint">—</span>');
assert.equal(policy.polling(status), true);
assert.equal(policy.polling(b.source_statuses[0]), false);
assert.equal(policy.polling({...status, effective_state: 'DISABLED'}), false);
status.serving_state = status.effective_state = 'PREPARING';
html = policy.control(lib, a, 'video');
assert.match(html, /value="PREPARING" selected\s+disabled/);
assert.match(html, /value="SERVING"\s*>/);
assert.match(policy.chip(status), /PREPARING/);
assert.equal(policy.pending(a, 'video'), false);
status.replaces = 'old';
assert.equal(policy.pending(a, 'video'), true);
assert.equal(policy.pending(a, 'old'), true);
assert.match(policy.control(lib, a, 'video'), /pending replacement/);
status.replaces = null;
source.enabled = false;
html = policy.control(lib, a, 'video');
assert.match(html, /Source is disabled/);
assert.match(html, /disabled>/);
assert.match(html, /DISABLED/);
assert.equal(policy.effective(source, status), 'DISABLED');
globalThis.sourceStatusChip = binding => `<span>${binding.display_status}</span>`;
status.display_status = 'extraction_waiting';
assert.match(policy.sourceBindings(lib, 'video'), /extraction_waiting/);
console.log('Pool-local serving controls passed');
"""
    result = subprocess.run([NODE, "-e", script, str(CONSOLE / "source-serving.js")],
        text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr