# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Failed extraction batches must reduce work, not repeat the same eight files."""
import io
from copy import deepcopy

import pytest

from okf_extractor import stage1_extract
from okf_extractor.agent import ExtractionResponseError
from okf_extractor.concept import Concept
from okf_extractor.config import Config
from okf_extractor.structure import FileInfo, Tree
from okf_extractor.ui import UI


def _files(root, count=8):
    return [FileInfo(rel_path=f"case.md/{number:06d}.md", abs_path=root / f"{number}.md",
                     size_bytes=300, approx_tokens=100, ext="md") for number in range(count)]


def _config():
    raw = deepcopy(Config.load().raw)
    raw["tools"] = {name: {"enabled": True} for name in ("read_text", "write_concept")}
    raw["batch"]["max_files_per_batch"] = 8
    return Config(raw)


def test_retry_reduces_file_count_even_when_all_files_still_fit_the_token_budget(tmp_path):
    remaining = _files(tmp_path)
    budget, smaller = stage1_extract._smaller_batch(remaining, remaining, 33321, 4000)
    assert budget == 16660
    assert len(smaller) == 4
    budget, smaller = stage1_extract._smaller_batch(remaining, smaller, budget, 4000)
    assert len(smaller) == 2
    budget, smaller = stage1_extract._smaller_batch(remaining, smaller, budget, 4000)
    assert len(smaller) == 1


def test_successful_reduced_cap_is_reused_and_no_fragments_are_dropped(tmp_path, monkeypatch):
    files = _files(tmp_path)
    attempts = []

    def run(client, system, tools, ctx, **kwargs):
        paths = sorted(ctx.assigned_files)
        attempts.append(paths)
        if len(paths) > 2:
            return "max_steps"
        ctx.files_read.extend(paths)
        ctx.completed_files.update(paths)
        ctx.sink.extend(Concept(type="Topic", title=path, source_files=[path]) for path in paths)
        return "natural"

    monkeypatch.setattr(stage1_extract, "run_agent", run)
    concepts = stage1_extract.extract(_config(), object(), Tree(root=tmp_path, files=files),
                                     strict=True, ui=UI(stream=io.StringIO(), enabled=False))

    assert [len(paths) for paths in attempts] == [8, 4, 2, 2, 2, 2]
    assert {node.source_files[0] for node in concepts} == {source.rel_path for source in files}
    assert len(concepts) == 8


def test_strict_extraction_does_not_accept_a_partially_read_fragment(tmp_path, monkeypatch):
    def run(client, system, tools, ctx, **kwargs):
        ctx.files_read.extend(ctx.assigned_files)  # first capped window only; no completed_files
        return "natural"

    monkeypatch.setattr(stage1_extract, "run_agent", run)
    with pytest.raises(ExtractionResponseError, match="fully read 0/1"):
        stage1_extract.extract(_config(), object(), Tree(root=tmp_path, files=_files(tmp_path, 1)),
                               strict=True, ui=UI(stream=io.StringIO(), enabled=False))


def test_final_batch_failure_keeps_the_actual_tool_schema_error(tmp_path, monkeypatch):
    def run(client, system, tools, ctx, **kwargs):
        ctx.last_tool_error = "write_concept: arguments.source_files: expected array, got str"
        return "invalid_args"

    monkeypatch.setattr(stage1_extract, "run_agent", run)
    with pytest.raises(ExtractionResponseError, match="source_files: expected array"):
        stage1_extract.extract(_config(), object(), Tree(root=tmp_path, files=_files(tmp_path, 1)),
                               strict=True, ui=UI(stream=io.StringIO(), enabled=False))