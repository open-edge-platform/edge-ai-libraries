# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Exercise the shared source-form policy without a server or Node packages."""

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from core.loader import SUPPORTED_EXTS


NODE = shutil.which("node")
CONSOLE = Path(__file__).resolve().parents[1] / "src" / "console"


@pytest.mark.skipif(NODE is None, reason="Node is needed for console JavaScript tests")
def test_source_asset_type_defaults_choices_and_submission():
    script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
// Run in this realm so arrays can be compared normally. DOM use is deferred
// until mount(); policy tests never contact a server or load a real model.
vm.runInThisContext(source + '\nglobalThis.policy = SourceAssetTypes;');
globalThis.t = (key, vars = {}) => key.replace(/\{(\w+)\}/g, (match, name) => vars[name] ?? match);
const types = policy.supported('vector');
assert.deepEqual(types, [...JSON.parse(process.argv[2]), 'document', 'image', 'video', 'audio']);
assert.deepEqual(policy.supported('graph'), ['okf', 'document']);
assert.deepEqual(policy.defaults('vector'), ['document']);
assert.deepEqual(policy.defaults('graph'), ['okf']);
assert.deepEqual(policy.defaults('object'), []);
assert.deepEqual(policy.supported('object'), []);
policy.defaults('vector').push('video');
policy.supported('graph').push('video');
assert.deepEqual(policy.defaults('vector'), ['document']);
assert.deepEqual(policy.supported('graph'), ['okf', 'document']);
for (const value of types) {
  assert.deepEqual(policy.options('vector', [value], {}), {asset_types: [value]});
}
assert.deepEqual(policy.options('vector', ['pdf', 'md', 'pdf'], {chunk_size: 256}),
  {chunk_size: 256, asset_types: ['pdf', 'md']});
assert.deepEqual(policy.options('vector', ['video'], {block_roles: ['l2_caption'], embedding_model: 'gme-int8'}),
  {block_roles: ['l2_caption'], embedding_model: 'gme-int8', asset_types: ['video']});
assert.throws(() => policy.options('vector', ['video'], {precision: 'fp16'}), /precision.*embedding_model/);
assert.throws(() => policy.options('vector', ['pdf'], {precision: null}), /precision.*embedding_model/);
for (const type of ['vector', 'graph', 'object']) {
  for (const value of [null, '', '/explicit/model', 'relative/model']) {
    assert.throws(() => policy.options(type, policy.defaults(type), {embedding_model_path: value}),
      /embedding_model_path.*embedding_model/);
  }
}
assert.deepEqual(policy.options('graph', ['okf', 'document'], {external_extractor: {url: 'http://example.invalid'}}),
  {external_extractor: {url: 'http://example.invalid'}, asset_types: ['okf', 'document']});
for (const value of [[], null, undefined, 'pdf']) {
  assert.throws(() => policy.options('vector', value, {}), /Select at least one/);
}
assert.throws(() => policy.options('vector', ['okf'], {}), /Invalid content type/);
assert.throws(() => policy.options('graph', ['pdf'], {}), /Invalid content type/);
assert.throws(() => policy.options('vector', ['pdf'], {asset_types: ['video']}), /above, not in the JSON/);
const extra = {path: '/object-store'};
assert.equal(policy.options('object', [], extra), extra);
assert.deepEqual(extra, {path: '/object-store'});
console.log('Source-form defaults, catalog and submission checks passed');
"""
    result = subprocess.run(
        [NODE, "-e", script, str(CONSOLE / "source-options.js"),
         json.dumps([extension.lstrip(".") for extension in SUPPORTED_EXTS])],
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(NODE is None, reason="Node is needed for console JavaScript tests")
def test_structured_editor_and_extraction_status_regressions():
    tests = Path(__file__).resolve().parent
    result = subprocess.run(
        [NODE, "--test", str(tests / "console_source_options.test.cjs"),
         str(tests / "console_source_status.test.cjs")],
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(NODE is None, reason="Node is needed for console JavaScript tests")
def test_checkbox_payloads_pass_real_source_creation_without_models_or_databases(tmp_path):
    from core.file_asset_library import FileAssetLibrary
    from tests import dbhub

    result = subprocess.run(
        [NODE, str(Path(__file__).with_name("console_source_options.test.cjs"))],
        env={**os.environ, "CONSOLE_SOURCE_OPTIONS_CONTRACT": "1"},
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payloads = [
        line.removeprefix("SOURCE_OPTIONS_CONTRACT=")
        for line in result.stdout.splitlines()
        if line.startswith("SOURCE_OPTIONS_CONTRACT=")
    ]
    assert len(payloads) == 1, result.stdout
    hub = dbhub.with_graph(dbhub.with_vector(dbhub.object_hub(root=str(tmp_path / "content"))))
    library = FileAssetLibrary(name="checkbox-contract", databasehub=hub)
    cases = json.loads(payloads[0])
    assert len(cases) == 34
    for index, case in enumerate(cases):
        source = library.create_source(
            f"checkbox-{index}",
            dbhub.VECTOR_DATABASE if case["type"] == "vector" else dbhub.GRAPH_DATABASE,
            configuration=case["options"],
            register=False,
        )
        assert source.configuration == case["options"]
        assert source.profile