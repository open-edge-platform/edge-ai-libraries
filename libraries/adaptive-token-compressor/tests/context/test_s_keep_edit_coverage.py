"""Boundary and counting checks for the offline edit-coverage analysis."""
import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def analysis(monkeypatch):
    directory = Path(__file__).resolve().parents[2] / "dev_tests/context_compressor_dev/analysis"
    monkeypatch.syspath_prepend(str(directory))
    spec = importlib.util.spec_from_file_location("s_keep_edit_coverage", directory / "s_keep_edit_coverage.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def call(cid, name, args):
    return {"id": cid, "function": {"name": name, "arguments": json.dumps(args)}}


def request(gap, stub):
    messages = [
        {"role": "assistant", "tool_calls": [call("read0", "read", {"path": "/testbed/a.py"})]},
        {"role": "tool", "tool_call_id": "read0", "content": stub},
    ]
    for i in range(gap - 1):
        messages.extend([
            {"role": "assistant", "tool_calls": [call(f"other{i}", "exec", {"command": "true"})]},
            {"role": "tool", "tool_call_id": f"other{i}", "content": "ok"},
        ])
    return {
        "run": "run", "trial": "trial", "task": "task", "rid": "rid",
        "body": {"messages": messages},
        "out": {"tool_calls": [call("edit0", "edit", {"file": "a.py", "oldText": "exact text"})]},
    }


@pytest.mark.parametrize("gap", [1, 2, 3, 4, 6, 8, 12, 16, 32, 40, 64, 65])
def test_keep_boundary_at_edit_prompt(analysis, gap):
    raw = "exact text\n" * 3000
    row = request(gap, analysis.STUB)
    keeps = (1, 2, 3, 4, 6, 8, 12, 16, 32, 64)
    result, = analysis.analyze_request(
        row, {"read0": raw, "edit0": "Could not find the exact text"}, 2000, keeps
    )
    assert result["nearest_stub_gap"] == gap
    assert result["exact_failure"]
    for keep in keeps:
        assert result[f"retained_k{keep}"] == (gap <= keep)
        assert result[f"actual_newly_k{keep}"] == (1 < gap <= keep)
        assert result[f"actual_newly_exact_k{keep}"] == (1 < gap <= keep)


def test_same_file_coverage_is_not_exact_text_coverage(analysis):
    row = request(2, analysis.STUB)
    row["out"]["tool_calls"][0]["function"]["arguments"] = json.dumps({
        "path": "a.py", "old_string": "invented source",
    })
    result, = analysis.analyze_request(row, {"read0": "x\n" * 10000, "edit0": "ok"}, 2000)
    assert result["actual_newly_k2"]
    assert not result["actual_newly_exact_k2"]


def test_multiple_reads_do_not_double_count_edit(analysis):
    row = request(2, analysis.STUB)
    row["body"]["messages"][0]["tool_calls"].append(call("read1", "read", {"path": "a.py"}))
    row["body"]["messages"].insert(2, {
        "role": "tool", "tool_call_id": "read1", "content": analysis.STUB,
    })
    records = analysis.analyze_request(
        row, {"read0": "x\n" * 10000, "read1": "x\n" * 10000, "edit0": "ok"}, 2000
    )
    assert len(records) == 1
    assert records[0]["actual_newly_k2"]
