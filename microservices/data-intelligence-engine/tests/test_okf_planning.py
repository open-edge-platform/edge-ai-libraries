# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Planning output limits must not turn a valid dense corpus into a task 422."""
import json
import io
import re
from copy import deepcopy

import pytest

from okf_extractor.config import Config
from okf_extractor import planning


class ModelResponses:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.limits = []
        self.messages = []

    def chat(self, messages, *, max_tokens):
        self.limits.append(max_tokens)
        self.messages.append(messages)
        return next(self.responses)


def _choice(text="Incomplete review", reason="length"):
    return {"message": {"content": text}, "finish_reason": reason}


@pytest.fixture
def cfg():
    return Config(deepcopy(Config.load().raw))


@pytest.mark.parametrize("system,initial", [
    (planning._REVIEW, 1500), (planning._REDUCE, 1500), (planning._PLAN, 4096),
])
def test_truncated_planning_response_retries_same_input_with_more_output_tokens(cfg, system, initial):
    model = ModelResponses([_choice(), _choice("Complete response", "stop")])

    assert planning._answer(cfg, model, system, "All source text", initial) == "Complete response"
    assert model.limits == [initial, initial * 2]
    assert model.messages[0] == model.messages[1], "retries must not truncate or skip source input"


def test_truncation_retries_are_bounded_and_report_the_exact_output_limit(cfg):
    cfg.raw["planning"]["max_response_tokens"] = 3500
    model = ModelResponses([_choice(), _choice(), _choice()])

    with pytest.raises(RuntimeError, match=r"truncated.*finish_reason=length.*max_tokens=3500"):
        planning._answer(cfg, model, planning._REVIEW, "Dense source", 1500)
    assert model.limits == [1500, 3000, 3500]


def test_response_retries_never_exceed_context_headroom(cfg):
    from okf_extractor.llmclient import approx_tokens

    messages = planning._messages(planning._REVIEW, "Source")
    cfg.raw["llm"]["context_window"] = approx_tokens(messages, cfg.batch["chars_per_token"]) + 2500 + 256
    model = ModelResponses([_choice(), _choice()])

    with pytest.raises(RuntimeError, match=r"max_tokens=2500"):
        planning._answer(cfg, model, planning._REVIEW, "Source", 1500)
    assert model.limits == [1500, 2500]


def test_empty_planning_response_reports_upstream_output_not_invalid_task(cfg):
    model = ModelResponses([_choice("", "stop")])
    with pytest.raises(RuntimeError, match=r"empty.*finish_reason=stop"):
        planning._answer(cfg, model, planning._REVIEW, "Source", 1500)


def test_successful_output_limit_is_reused_for_the_same_phase_only(cfg):
    budgets = {}
    original = deepcopy(cfg.raw)
    model = ModelResponses([
        _choice(), _choice("Complete reduction", "stop"),
        _choice("Next complete reduction", "stop"),
        _choice("Source review", "stop"), _choice("Instructions", "stop"),
    ])

    planning._answer(cfg, model, planning._REDUCE, "First group", 1500, response_budgets=budgets)
    planning._answer(cfg, model, planning._REDUCE, "Second group", 1500, response_budgets=budgets)
    planning._answer(cfg, model, planning._REVIEW, "Source", 1500, response_budgets=budgets)
    planning._answer(cfg, model, planning._PLAN, "All reviews", 4096, response_budgets=budgets)

    assert model.limits == [1500, 3000, 3000, 1500, 4096]
    assert model.messages[0] == model.messages[1]
    assert budgets == {"review reduction": 3000, "source review": 1500, "instruction synthesis": 4096}
    assert cfg.raw == original


@pytest.mark.parametrize("available,ceiling,expected", [(2500, 8192, 2500), (10000, 3500, 3500)])
def test_learned_budget_still_respects_current_request_headroom_and_ceiling(cfg, available, ceiling, expected):
    from okf_extractor.llmclient import approx_tokens

    messages = planning._messages(planning._REDUCE, "Another group")
    cfg.raw["llm"]["context_window"] = approx_tokens(messages, cfg.batch["chars_per_token"]) + available + 256
    cfg.raw["planning"]["max_response_tokens"] = ceiling
    budgets = {"review reduction": 6000}
    model = ModelResponses([_choice("Complete reduction", "stop")])

    assert planning._answer(
        cfg, model, planning._REDUCE, "Another group", 1500, response_budgets=budgets,
    ) == "Complete reduction"
    assert model.limits == [expected]


class DenseCorpusModel:
    """Many long reviews, with a reduction that needs more than 1500 tokens."""

    def __init__(self):
        self.reviews = []
        self.reductions = []
        self.plan_body = ""

    def chat(self, messages, *, max_tokens):
        system, body = (message["content"] for message in messages)
        if system == planning._REVIEW:
            source = json.loads(body)
            self.reviews.append(source)
            return _choice(source["content"] + "\n" + "Common design guidance; " * 100, "stop")
        if system == planning._REDUCE:
            self.reductions.append((body, max_tokens))
            if max_tokens < 3000:
                return _choice()
            # Preserve every distinct exception marker from this group.
            markers = dict.fromkeys(re.findall(r"EXCEPTION_\d+", body))
            return _choice(" ".join(markers) + " combined design rules.", "stop")
        assert system == planning._PLAN
        self.plan_body = body
        return _choice(json.dumps({"instructions": {
            key: f"Task-specific {key}" for key in planning.DEFAULT_INSTRUCTIONS
        }}), "stop")


def test_reduction_groups_learn_budget_without_skipping_sources_or_leaking_between_tasks(cfg, tmp_path, caplog):
    from okf_extractor.structure import scan
    from okf_extractor.ui import UI

    for index in range(16):
        (tmp_path / f"source-{index:02d}.md").write_text(f"EXCEPTION_{index:02d} must remain.", encoding="utf-8")
    cfg.raw["planning"]["chunk_tokens"] = 4000
    original = deepcopy(cfg.raw)
    stream = io.StringIO()
    model = DenseCorpusModel()

    planning.plan_instructions(cfg, model, scan(tmp_path, 3.0), ui=UI(stream=stream, enabled=False))

    assert len(model.reviews) == 16
    for source in model.reviews:
        assert source["offset"] == 0
        assert source["content"] == (tmp_path / source["source"]).read_text(encoding="utf-8")
    assert len(model.reductions) > 2
    assert [limit for _, limit in model.reductions] == [1500, *([3000] * (len(model.reductions) - 1))]
    assert model.reductions[0][0] == model.reductions[1][0], "retry exactly the same group"
    assert all(f"EXCEPTION_{index:02d}" in model.plan_body for index in range(16))
    assert sum("review reduction truncated at max_tokens=1500" in record.message for record in caplog.records) == 1
    assert "reducing reviews: pass 1, group 1/" in stream.getvalue()
    assert "condensed reviews" in stream.getvalue()
    assert cfg.raw == original

    another_task = DenseCorpusModel()
    planning.plan_instructions(cfg, another_task, scan(tmp_path, 3.0), ui=UI(stream=io.StringIO(), enabled=False))
    assert another_task.reductions[0][1] == 1500, "tasks must not share learned budgets"


def test_redirect_links_reports_kept_and_unresolved_links():
    from okf_extractor import stage2_merge
    from okf_extractor.concept import Concept

    ada = Concept(type="Person", title="Ada", source_files=["a.md"],
                  links=[("migration", "leads"), ("Unknown thing", "uses")])
    project = Concept(type="Project", title="Migration", source_files=["a.md"])
    merged = {("person", "ada"): ada, ("project", "migration"): project}

    stats = stage2_merge.redirect_links(merged)

    assert ada.links == [("Migration", "leads")]
    assert stats == {"kept": 1, "unresolved": 1, "examples": ["Ada -> Unknown thing"]}


def test_planning_reports_progress_per_review_part(tmp_path):
    import io
    from okf_extractor.structure import scan
    from okf_extractor.ui import UI

    (tmp_path / "big.md").write_text("Ada leads the migration. " * 4000, encoding="utf-8")
    raw = deepcopy(Config.load().raw)
    raw["planning"]["chunk_tokens"] = 3000
    stream = io.StringIO()

    class Model:
        def chat(self, messages, **kwargs):
            return {"finish_reason": "stop", "message": {"content": json.dumps({"instructions": {
                key: "x" for key in planning.DEFAULT_INSTRUCTIONS}})}}

    planning.plan_instructions(Config(raw), Model(), scan(tmp_path, 3.0), ui=UI(stream=stream, enabled=False))
    log = stream.getvalue()
    assert "reviewing big.md: part 1 · 0%" in log and "reviewing big.md: part 2" in log
    assert "reviewed all content: big.md" in log and "planning instructions from" in log
