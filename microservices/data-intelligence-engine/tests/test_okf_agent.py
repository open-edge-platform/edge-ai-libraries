# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Regressions for malformed concept calls, repeated reads and bounded model turns."""
import io
import json
from copy import deepcopy

import pytest

from okf_extractor.agent import AgentCtx, _parse_and_validate, _result_note, openai_tools, run_agent
from okf_extractor.config import Config
from okf_extractor.tools import _SCHEMAS, build_tools
from okf_extractor.ui import UI


@pytest.fixture
def cfg():
    raw = deepcopy(Config.load().raw)
    raw["tools"] = {name: {"enabled": True} for name in ("list_dir", "read_text", "write_concept")}
    return Config(raw)


def _context(tmp_path, text="First line\nLast line\n"):
    path = tmp_path / "case.md/000000.md"
    path.parent.mkdir()
    path.write_text(text, encoding="utf-8")
    return AgentCtx(data_dir=tmp_path, read_budget=10000, assigned_files={"case.md/000000.md"})


def _tools(cfg, ctx):
    return {tool.name: tool for tool in build_tools(cfg, ctx)}


def _arguments(**overrides):
    return {"type": "Person", "title": "Ada", "summary": "Leads the project.",
            "source_files": ["case.md/000000.md"], **overrides}


@pytest.mark.parametrize("values,field", [
    (_arguments(source_files="private source content"), "arguments.source_files: expected array"),
    (_arguments(source_files=[]), "arguments.source_files: must contain"),
    (_arguments(source_files=[23]), "arguments.source_files[0]: expected string"),
    (_arguments(type=" "), "arguments.type: must be a non-empty string"),
    (_arguments(links=["Other concept"]), "arguments.links[0]: expected object"),
    (_arguments(links=[{"rel": "owns"}]), "arguments.links[0]: missing required field(s): to_title"),
    (_arguments(links=[{"to_title": 23}]), "arguments.links[0].to_title: expected string"),
])
def test_argument_errors_name_the_bad_field_without_echoing_source_values(values, field):
    args, error = _parse_and_validate(json.dumps(values), _SCHEMAS["write_concept"])
    assert args is None and field in error
    assert "private source content" not in error


def test_object_valued_tool_arguments_from_compatible_servers_are_supported():
    values = _arguments(links=[{"to_title": "Project", "rel": "leads"}])
    assert _parse_and_validate(values, _SCHEMAS["write_concept"]) == (values, None)


@pytest.mark.parametrize("offset", [-1, True, "200"])
def test_offset_schema_does_not_accept_negative_or_non_integer_offsets(offset):
    args, error = _parse_and_validate({"path": "a", "offset": offset}, _SCHEMAS["read_text"])
    assert args is None and "offset" in error


def test_complete_fragment_is_not_reread_or_charged_again(cfg, tmp_path):
    ctx = _context(tmp_path)
    read = _tools(cfg, ctx)["read_text"].handler
    first = read({"path": "case.md/000000.md"}, ctx)
    used = ctx.read_tokens
    assert "End of file." in first
    assert ctx.completed_files == ctx.assigned_files
    for offset in (0, 1, 200):
        duplicate = read({"path": "case.md/000000.md", "offset": offset}, ctx)
        assert duplicate.startswith("Already read:")
        assert "read ok" not in _result_note("read_text", duplicate, ctx)
    assert ctx.read_tokens == used and ctx.files_read == ["case.md/000000.md"]


def test_final_blank_lines_do_not_leave_a_fully_read_fragment_marked_incomplete(cfg, tmp_path):
    ctx = _context(tmp_path, "text\n\n")
    result = _tools(cfg, ctx)["read_text"].handler({"path": "case.md/000000.md"}, ctx)
    assert "2: " in result and "End of file." in result
    assert ctx.completed_files == ctx.assigned_files


def test_capped_read_advances_at_the_returned_offset_and_keeps_global_line_numbers(cfg, tmp_path):
    cfg.raw["batch"]["per_file_read_lines"] = 2
    ctx = _context(tmp_path, "first\nsecond\nthird\nfourth\n")
    read = _tools(cfg, ctx)["read_text"].handler
    first = read({"path": "case.md/000000.md"}, ctx)
    assert "Output capped. Use offset=2" in first
    assert ctx.completed_files == set()
    used = ctx.read_tokens
    assert read({"path": "case.md/000000.md"}, ctx).startswith("Already read:")
    assert ctx.read_tokens == used
    last = read({"path": "case.md/000000.md", "offset": 2}, ctx)
    assert "3: third\n4: fourth" in last and "End of file." in last
    assert ctx.completed_files == ctx.assigned_files


def test_eof_and_negative_offsets_are_not_counted_as_successful_reads(cfg, tmp_path):
    ctx = _context(tmp_path)
    read = _tools(cfg, ctx)["read_text"].handler
    assert read({"path": "case.md/000000.md", "offset": -1}, ctx).startswith("Tool input rejected:")
    eof = read({"path": "case.md/000000.md", "offset": 200}, ctx)
    assert eof.startswith("End of file:") and "2 lines" in eof
    assert _result_note("read_text", eof, ctx).startswith("EOF")
    assert ctx.read_tokens == 0 and ctx.files_read == [] and not ctx.completed_files


def test_reading_a_tail_alone_does_not_mark_the_whole_source_complete(cfg, tmp_path):
    cfg.raw["batch"]["per_file_read_lines"] = 2
    ctx = _context(tmp_path, "first\nsecond\nthird\n")
    read = _tools(cfg, ctx)["read_text"].handler
    read({"path": "case.md/000000.md", "offset": 2}, ctx)
    assert not ctx.completed_files
    read({"path": "case.md/000000.md"}, ctx)
    assert ctx.completed_files == ctx.assigned_files


def test_other_batches_cannot_be_read_or_cited(cfg, tmp_path):
    ctx = _context(tmp_path)
    (tmp_path / "other.md").write_text("Unassigned source", encoding="utf-8")
    tools = _tools(cfg, ctx)
    assert "outside the assigned batch" in tools["read_text"].handler({"path": "other.md"}, ctx)
    listing = tools["list_dir"].handler({}, ctx)
    assert "other.md" not in listing
    assert tools["write_concept"].handler(_arguments(source_files=["other.md"]), ctx).startswith("Tool input rejected:")
    assert ctx.sink == []


def test_provenance_requires_full_read_fragment_paths_and_identical_writes_are_not_duplicated(cfg, tmp_path):
    ctx = _context(tmp_path)
    tools = _tools(cfg, ctx)
    write = tools["write_concept"].handler
    assert write(_arguments(), ctx).startswith("Tool input rejected:")  # not read yet
    tools["read_text"].handler({"path": "case.md/000000.md"}, ctx)
    assert write(_arguments(source_files=["case.md"]), ctx).startswith("Tool input rejected:")
    assert write(_arguments(), ctx).startswith("recorded concept:")
    assert write(_arguments(), ctx).startswith("Already recorded concept:")
    assert len(ctx.sink) == 1


class ModelTurns:
    def __init__(self, choices):
        self.choices = iter(choices)
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append((deepcopy(messages), deepcopy(kwargs)))
        return next(self.choices)


def _call(name, args, reason="tool_calls"):
    return {"finish_reason": reason, "message": {
        "role": "assistant", "content": None, "tool_calls": [{
            "id": "call", "type": "function", "function": {"name": name, "arguments": json.dumps(args)},
        }],
    }}


def _stop(reason="stop"):
    return {"finish_reason": reason, "message": {"role": "assistant", "content": "Finished"}}


def _run(model, cfg, ctx, stream=None, **kwargs):
    return run_agent(model, "Extract concepts", list(_tools(cfg, ctx).values()), ctx,
                     max_steps=20, first_user="Read the assigned fragment", ui=UI(stream=stream or io.StringIO(), enabled=False),
                     **kwargs)


def test_invalid_write_logs_field_and_type_and_allows_a_corrected_call(cfg, tmp_path):
    ctx = _context(tmp_path)
    model = ModelTurns([
        _call("read_text", {"path": "case.md/000000.md"}),
        _call("write_concept", _arguments(source_files="private source content")),
        _call("write_concept", _arguments()), _stop(),
    ])
    stream = io.StringIO()
    assert _run(model, cfg, ctx, stream) == "natural"
    assert "write_concept: invalid args" in stream.getvalue()
    assert "source_files: expected array" in stream.getvalue()
    assert "private source content" not in stream.getvalue()
    assert len(ctx.sink) == 1
    offered = {tool["function"]["name"] for tool in model.calls[1][1]["tools"]}
    assert offered == {"write_concept"}, "no more read/list tools after complete input coverage"


def _uncited_device(title="0000:da:00.0"):
    args = _arguments(type="PCIDevice", title=title)
    del args["source_files"]
    return args


def test_missing_source_files_correction_names_actual_read_paths_without_inventing_citations(cfg, tmp_path):
    ctx = _context(tmp_path)
    corrected = _arguments(type="PCIDevice", title="0000:da:00.0")
    model = ModelTurns([
        _call("read_text", {"path": "case.md/000000.md"}),
        _call("write_concept", _uncited_device()),
        _call("write_concept", corrected), _stop(),
    ])

    assert _run(model, cfg, ctx) == "natural"
    feedback = next(
        message["content"] for message in reversed(model.calls[2][0])
        if message["role"] == "tool"
    )
    assert "missing required field(s): source_files" in feedback
    assert "case.md/000000.md" in feedback
    assert "support" in feedback and "Do not guess" in feedback
    assert ctx.sink[0].source_files == ["case.md/000000.md"]
    assert ctx.files_read == ["case.md/000000.md"]


def test_write_schema_lists_only_successfully_read_paths_without_mutating_shared_schema(cfg, tmp_path):
    ctx = _context(tmp_path)
    unread = "case.md/000001.md"
    (tmp_path / unread).write_text("An unread fragment\n", encoding="utf-8")
    ctx.assigned_files.add(unread)
    tools = list(_tools(cfg, ctx).values())
    original = deepcopy(_SCHEMAS["write_concept"])
    _tools(cfg, ctx)["read_text"].handler({"path": "case.md/000000.md"}, ctx)

    advertised = next(tool["function"] for tool in openai_tools(tools, ctx) if tool["function"]["name"] == "write_concept")

    assert advertised["parameters"]["properties"]["source_files"]["items"]["enum"] == ["case.md/000000.md"]
    assert "source_files" in advertised["parameters"]["required"]
    assert _SCHEMAS["write_concept"] == original
    assert "enum" not in _SCHEMAS["write_concept"]["properties"]["source_files"]["items"]


@pytest.mark.parametrize("same_response", [False, True])
def test_valid_other_concept_does_not_clear_a_rejected_devices_missing_provenance(cfg, tmp_path, same_response):
    ctx = _context(tmp_path)
    other = _arguments(title="Project", links=[{"to_title": "0000:da:00.0", "rel": "uses"}])
    invalid = _call("write_concept", _uncited_device())
    valid = _call("write_concept", other)
    if same_response:
        valid["message"]["tool_calls"][0]["id"] = "other-call"
        invalid["message"]["tool_calls"].extend(valid["message"]["tool_calls"])
        writes = [invalid]
    else:
        writes = [invalid, valid]
    model = ModelTurns([
        _call("read_text", {"path": "case.md/000000.md"}),
        *writes, _stop(), _stop(),
    ])

    assert _run(model, cfg, ctx, max_idle_steps=2) == "invalid_args"
    assert [concept.title for concept in ctx.sink] == ["Project"]
    assert "0000:da:00.0" in ctx.last_tool_error and "source_files" in ctx.last_tool_error


def test_correction_of_one_device_does_not_clear_another_rejected_device(cfg, tmp_path):
    ctx = _context(tmp_path)
    model = ModelTurns([
        _call("read_text", {"path": "case.md/000000.md"}),
        _call("write_concept", _uncited_device()),
        _call("write_concept", _uncited_device("0000:e7:03.0")),
        _call("write_concept", _arguments(type="PCIDevice", title="0000:e7:03.0")),
        _stop(), _stop(), _stop(),
    ])

    assert _run(model, cfg, ctx, max_idle_steps=3) == "invalid_args"
    assert [concept.title for concept in ctx.sink] == ["0000:e7:03.0"]
    assert "0000:da:00.0" in ctx.last_tool_error


def test_stopping_with_a_rejected_write_prompts_bounded_correction_for_the_same_concept(cfg, tmp_path):
    ctx = _context(tmp_path)
    model = ModelTurns([
        _call("read_text", {"path": "case.md/000000.md"}),
        _call("write_concept", _uncited_device()), _stop(),
        _call("write_concept", _arguments(type="PCIDevice", title="0000:da:00.0")), _stop(),
    ])

    assert _run(model, cfg, ctx) == "natural"
    correction = model.calls[3][0][-1]["content"]
    assert "0000:da:00.0" in correction and "source_files" in correction
    assert [concept.title for concept in ctx.sink] == ["0000:da:00.0"]
    assert ctx.last_tool_error == ""


def test_correcting_a_rejected_duplicate_counts_as_recovery_not_an_idle_turn(cfg, tmp_path):
    ctx = _context(tmp_path)
    tools = _tools(cfg, ctx)
    tools["read_text"].handler({"path": "case.md/000000.md"}, ctx)
    tools["write_concept"].handler(_arguments(), ctx)
    missing = _arguments()
    del missing["source_files"]
    model = ModelTurns([
        _call("write_concept", missing),
        _call("write_concept", _arguments(source_files="not an array")),
        _call("write_concept", _arguments(source_files=[])),
        _call("write_concept", _arguments()), _stop(),
    ])

    assert _run(model, cfg, ctx, max_idle_steps=4) == "natural"
    assert len(ctx.sink) == 1 and ctx.last_tool_error == ""


def test_truncated_tool_output_retries_the_same_history_without_executing_partial_writes(cfg, tmp_path):
    ctx = _context(tmp_path)
    _tools(cfg, ctx)["read_text"].handler({"path": "case.md/000000.md"}, ctx)
    model = ModelTurns([
        _call("write_concept", _arguments(title="Partial"), reason="length"),
        _call("write_concept", _arguments(title="Complete")), _stop(),
    ])
    assert _run(model, cfg, ctx) == "natural"
    assert [node.title for node in ctx.sink] == ["Complete"]
    assert [options["max_tokens"] for _, options in model.calls] == [4096, 8192, 8192]
    assert model.calls[0][0] == model.calls[1][0]


def test_repeated_bad_calls_stop_before_max_steps(cfg, tmp_path):
    ctx = _context(tmp_path)
    invalid = _call("write_concept", _arguments(source_files="not an array"))
    model = ModelTurns([invalid] * 10)
    assert _run(model, cfg, ctx, max_idle_steps=4) == "invalid_args"
    assert len(model.calls) == 4 and not ctx.sink
    assert "source_files" in ctx.last_tool_error


def test_output_limit_is_not_misreported_as_natural_completion(cfg, tmp_path):
    ctx = _context(tmp_path)
    model = ModelTurns([_call("write_concept", _arguments(), reason="length")])
    assert _run(model, cfg, ctx, max_response_tokens=4096) == "output_limit"
    assert len(model.calls) == 1 and ctx.sink == []
    assert "truncated at max_tokens=4096" in ctx.last_tool_error


def test_nonstop_finish_without_tool_calls_is_not_a_complete_extraction(cfg, tmp_path):
    ctx = _context(tmp_path)
    assert _run(ModelTurns([_stop("content_filter")]), cfg, ctx) == "invalid_response"

def test_a_session_without_any_links_is_asked_for_relations_once(cfg, tmp_path):
    ctx = _context(tmp_path)
    linked = _arguments(links=[{"to_title": "Migration", "rel": "leads"}])
    model = ModelTurns([
        _call("read_text", {"path": "case.md/000000.md"}),
        _call("write_concept", _arguments()),
        _call("write_concept", _arguments(type="Project", title="Migration")),
        _stop(), _call("write_concept", linked), _stop(),
    ])

    assert _run(model, cfg, ctx) == "natural"
    assert "None of the recorded concepts has links" in model.calls[4][0][-1]["content"]
    assert [concept.links for concept in ctx.sink][-1] == [("Migration", "leads")]


def test_a_session_still_without_links_after_the_request_finishes(cfg, tmp_path):
    ctx = _context(tmp_path)
    model = ModelTurns([
        _call("read_text", {"path": "case.md/000000.md"}),
        _call("write_concept", _arguments()),
        _call("write_concept", _arguments(type="Project", title="Migration")),
        _stop(), _stop(),
    ])

    assert _run(model, cfg, ctx) == "natural"
    assert len(model.calls) == 5 and len(ctx.sink) == 2


def test_only_repeating_recorded_concepts_after_reading_everything_finishes_the_batch(cfg, tmp_path):
    """A one-sentence document: the model records its concepts, then re-sends
    them instead of stopping. That is a complete batch, not a stall."""
    ctx = _context(tmp_path)
    write = _call("write_concept", _arguments())
    model = ModelTurns([_call("read_text", {"path": "case.md/000000.md"}), write, write, write, write, write])

    assert _run(model, cfg, ctx, max_idle_steps=4) == "natural"
    assert len(ctx.sink) == 1 and len(model.calls) == 4


def test_repeating_before_everything_is_read_is_still_a_stall(cfg, tmp_path):
    ctx = _context(tmp_path)
    ctx.assigned_files = {"case.md/000000.md", "case.md/000001.md"}
    (tmp_path / "case.md/000001.md").write_text("More\n", encoding="utf-8")
    write = _call("write_concept", _arguments())
    model = ModelTurns([_call("read_text", {"path": "case.md/000000.md"}), *[write] * 6])

    assert _run(model, cfg, ctx, max_idle_steps=4) == "stalled"
