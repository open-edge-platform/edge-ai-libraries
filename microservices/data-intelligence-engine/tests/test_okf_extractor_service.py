# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Exercise the real task pipeline with a deterministic tool-calling model."""
import json
import re
from copy import deepcopy

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient

from okf_extractor import service
from okf_extractor.agent import ExtractionResponseError
from okf_extractor.config import Config
from okf_extractor.llmclient import ContextOverflowError
from okf_extractor.planning import _PLAN, _REDUCE, _REVIEW
from okf_extractor.prompts import DEFAULT_INSTRUCTIONS
from okf_extractor.schemas import ExtractionTask
from okf_extractor.shared import upload_directory


class TaskModel:
    instances = []

    def __init__(self, config):
        self.events = []
        self.closed = False
        self.instances.append(self)

    def close(self):
        self.closed = True

    def chat(self, messages, tools=None, **kwargs):
        system = messages[0]["content"]
        if system == _REVIEW:
            source = json.loads(messages[1]["content"])
            self.events.append(("review", source))
            return self._choice(f"Corpus has recurring entities. Source {source['source']} at {source['offset']}.")
        if system == _REDUCE:
            self.events.append(("reduce", messages[1]["content"]))
            return self._choice("Combined domain/identity/relation rules from every review.")
        if system == _PLAN:
            self.events.append(("plan", messages[1]["content"]))
            return self._choice(json.dumps({"instructions": {
                key: f"Task-specific {key}: recurring corpus entities, records are evidence."
                for key in DEFAULT_INSTRUCTIONS
            }}))
        assert tools is not None
        assert "Task-specific DOMAIN" in system
        assert "Task-specific RELATION_RULES" in system
        self.events.append(("extract", messages))
        calls = [message for message in messages if message.get("role") == "tool"]
        if not calls:
            paths = re.findall(r"^- (.+?)  \(~", messages[1]["content"], re.MULTILINE)
            return self._tool_calls("read_text", [{"path": path} for path in paths])
        if not any("recorded concept:" in message["content"] for message in calls):
            paths = [message["content"].split(" (lines from", 1)[0] for message in calls]
            return self._tool_calls("write_concept", [{
                "type": "Topic", "title": "Corpus", "summary": "A task-specific corpus concept.",
                "source_files": paths,
            }])
        return self._choice("Finished.")

    @staticmethod
    def _choice(text):
        return {"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}

    @staticmethod
    def _tool_calls(name, arguments):
        return {"message": {"role": "assistant", "content": None, "tool_calls": [
            {"id": f"{name}-{number}", "type": "function", "function": {
                "name": name, "arguments": json.dumps(args),
            }} for number, args in enumerate(arguments)
        ]}, "finish_reason": "tool_calls"}


@pytest.fixture
def cfg():
    raw = deepcopy(Config.load().raw)
    raw["merge"]["llm_canonicalize"] = False
    return Config(raw)


@pytest.fixture
def model(monkeypatch):
    TaskModel.instances = []
    monkeypatch.setattr(service, "LLMClient", TaskModel)
    return TaskModel


@pytest.fixture(autouse=True)
def shared_dir(monkeypatch, tmp_path):
    root = tmp_path / "uploads"
    monkeypatch.setenv("ENGINE_UPLOAD_DIR", str(root))
    return root


def _task(**options):
    return {"task_id": "sample-task", "items": [
        {"path": "records/first.pdf", "asset_id": "first", "content": "First full source."},
        {"path": "profiles/last.md", "asset_id": "last", "content": "Last full source."},
    ], "options": options}


def _bundle(response):
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/json"
    result = response.json()
    assert result["concept_count"] >= 1
    assert result["bundle_path"] == f"okf-extractor/{result['task_id']}/bundle"
    bundle = upload_directory() / result["bundle_path"]
    return {path.relative_to(bundle).as_posix(): path.read_text(encoding="utf-8")
            for path in bundle.rglob("*") if path.is_file()}


def test_task_reviews_every_source_before_generating_instructions_and_extracting(cfg, model, shared_dir):
    with TestClient(service.create_app(cfg, api_key="")) as client:
        response = client.post("/v1/tasks", json=_task(language="zh"))
    bundle = _bundle(response)
    assert response.headers["x-okf-task-id"] == "sample-task"
    assert {"index.md", "topic/corpus.md", "instructions.yaml", "task.json"} <= bundle.keys()
    instructions = yaml.safe_load(bundle["instructions.yaml"])["instructions"]
    assert set(instructions) == set(DEFAULT_INSTRUCTIONS)
    assert "in zh" in instructions["DOMAIN"]
    concept = yaml.safe_load(bundle["topic/corpus.md"].split("---", 2)[1])
    assert concept["source_files"] == ["records/first.pdf", "profiles/last.md"]
    assert json.loads(bundle["task.json"])["sources"] == [
        {"path": "records/first.pdf", "asset_id": "first"},
        {"path": "profiles/last.md", "asset_id": "last"},
    ]
    assert "api_key" not in "".join(bundle.values())
    events = model.instances[0].events
    assert [event[0] for event in events[:3]] == ["review", "review", "plan"]
    assert all(event[0] == "extract" for event in events[3:])
    assert model.instances[0].closed
    assert (shared_dir / response.json()["bundle_path"] / "index.md").is_file()
    assert not list(shared_dir.rglob(".work-*")), "private normalization/work files are cleaned"
    assert not list(shared_dir.rglob("*.zip"))


def test_large_source_tails_are_reviewed_without_sampling(cfg, model):
    task = _task()
    text = "HEAD\n" + "x" * 85000 + "\nTAIL-MUST-BE-REVIEWED"
    task["items"][0]["content"] = text
    with TestClient(service.create_app(cfg, api_key="")) as client:
        _bundle(client.post("/v1/tasks", json=task))
    events = model.instances[0].events
    reviews = [body for kind, body in events if kind == "review" and body["source"] == "records/first.pdf"]
    assert len(reviews) > 1
    assert "".join(item["content"] for item in reviews) == text
    assert events.index(next(event for event in events if event[0] == "plan")) > len(reviews)
    reads = [message["content"] for kind, messages in events if kind == "extract"
             for message in messages if message["role"] == "tool"]
    assert any("TAIL-MUST-BE-REVIEWED" in read for read in reads), "extraction must read the tail too"


def test_operator_overrides_are_used_after_planning(cfg, model):
    with TestClient(service.create_app(cfg, api_key="")) as client:
        response = client.post("/v1/tasks", json=_task(instructions={"TITLE_RULES": "Keep stable identifiers."}))
    bundle = _bundle(response)
    assert yaml.safe_load(bundle["instructions.yaml"])["instructions"]["TITLE_RULES"] == "Keep stable identifiers."
    extraction = next(body for kind, body in model.instances[0].events if kind == "extract")
    assert "Keep stable identifiers." in extraction[0]["content"]


def test_shared_files_and_inline_blobs_use_the_same_pipeline(cfg, model, shared_dir):
    (shared_dir / "nested").mkdir(parents=True)
    (shared_dir / "nested/a.txt").write_text("The first file", encoding="utf-8")
    (shared_dir / "b.md").write_text("The last file", encoding="utf-8")
    with TestClient(service.create_app(cfg, api_key="")) as client:
        files = _bundle(client.post("/v1/tasks", json={"task_id": "files-task", "items": [
            {"path": "nested/a.txt", "file_path": "nested/a.txt"},
            {"path": "original.pdf", "file_path": "b.md"},
        ], "options": {"language": "en"}}))
        blob = _bundle(client.post("/v1/tasks", json={"items": [{
            "path": "blob.txt", "content": "Whole blob",
        }]}))
    assert "nested/a.txt" in files["topic/corpus.md"] and "original.pdf" in files["topic/corpus.md"]
    assert "blob.txt" in blob["topic/corpus.md"]
    assert (shared_dir / "nested/a.txt").read_text() == "The first file"
    assert (shared_dir / "b.md").read_text() == "The last file"
    assert len(model.instances) == 2 and all(instance.closed for instance in model.instances)


@pytest.mark.parametrize("path", ["../a", "/tmp/a", "a/../../b", "a\\b", ".hidden", "a//b", "C:/a", "a\x00b"])
def test_unsafe_source_paths_are_refused_before_the_model_is_created(cfg, model, path):
    with TestClient(service.create_app(cfg, api_key="")) as client:
        response = client.post("/v1/tasks", json={"items": [{"path": path, "content": "x"}]})
    assert response.status_code == 422
    assert not model.instances


@pytest.mark.parametrize("items", [
    [], [{"path": "a"}], [{"path": "a", "content": "x", "file_path": "a.txt"}],
    [{"path": "a", "content": "x"}, {"path": "a", "content": "y"}],
    [{"path": "a", "content": "x"}, {"path": "a/b", "content": "y"}],
])
def test_invalid_task_shapes_are_refused(cfg, model, items):
    with TestClient(service.create_app(cfg, api_key="")) as client:
        assert client.post("/v1/tasks", json={"items": items}).status_code == 422
    assert not model.instances


@pytest.mark.parametrize("item", [
    {"path": "a", "file_path": "missing.txt"}, {"path": "a", "content": "  "},
    {"path": "a", "data_base64": "files-must-use-shared-paths"},
])
def test_unreadable_sources_fail_explicitly(cfg, model, item):
    with TestClient(service.create_app(cfg, api_key="")) as client:
        assert client.post("/v1/tasks", json={"items": [item]}).status_code == 422
    assert not model.instances


def test_limits_and_bearer_authentication(cfg, model, shared_dir):
    shared_dir.mkdir()
    (shared_dir / "too-large.txt").write_bytes(b"123456789")
    with TestClient(service.create_app(cfg, api_key="secret", max_task_bytes=8)) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.post("/v1/tasks", json=_task()).status_code == 401
        response = client.post("/v1/tasks", json={"items": [{"path": "a", "content": "123456789"}]},
                               headers={"Authorization": "Bearer secret"})
        assert response.status_code == 413
        response = client.post("/v1/tasks", json={"items": [{"path": "a", "file_path": "too-large.txt"}]},
                               headers={"Authorization": "Bearer secret"})
        assert response.status_code == 413
    assert not model.instances


def test_model_failure_cleans_up_and_is_not_reported_as_an_empty_bundle(cfg, model, monkeypatch, shared_dir):
    def fail(*args, **kwargs):
        raise httpx.ConnectError("upstream failed")

    monkeypatch.setattr(model, "chat", fail)
    with TestClient(service.create_app(cfg, api_key="")) as client:
        assert client.post("/v1/tasks", json=_task()).status_code == 502
    assert model.instances[0].closed
    assert not list(shared_dir.rglob(".work-*"))
    assert not list(shared_dir.rglob("bundle")), "failed extraction must not publish an output folder"
    assert not list(shared_dir.rglob(".running"))


def test_task_schema_does_not_allow_backend_or_tool_config_overrides():
    with pytest.raises(ValueError):
        ExtractionTask.model_validate(_task(llm={"base_url": "http://untrusted"}))


def test_many_sources_are_reduced_before_instruction_synthesis_without_sampling(cfg, model):
    cfg.raw["planning"]["chunk_tokens"] = 4000
    task = {"items": [{"path": f"doc-{number}.txt", "content": f"Source {number}."} for number in range(200)]}
    with TestClient(service.create_app(cfg, api_key="")) as client:
        _bundle(client.post("/v1/tasks", json=task))
    events = model.instances[0].events
    reviews = [body for kind, body in events if kind == "review"]
    assert len(reviews) == 200
    assert {review["source"] for review in reviews} == {item["path"] for item in task["items"]}
    assert any(kind == "reduce" for kind, _ in events)
    plan_index = next(index for index, event in enumerate(events) if event[0] == "plan")
    assert all(kind != "extract" for kind, _ in events[:plan_index])


def test_server_context_overflow_retries_the_same_source_range_without_losing_text(cfg, model, monkeypatch):
    original_chat = model.chat
    rejected = []

    def chat(self, messages, **kwargs):
        if messages[0]["content"] == _REVIEW:
            body = json.loads(messages[1]["content"])
            if len(body["content"]) > 2000:
                rejected.append(body)
                raise ContextOverflowError("server has a smaller context window")
        return original_chat(self, messages, **kwargs)

    monkeypatch.setattr(model, "chat", chat)
    text = "start" + "x" * 9000 + "end"
    with TestClient(service.create_app(cfg, api_key="")) as client:
        _bundle(client.post("/v1/tasks", json={"items": [{"path": "large.txt", "content": text}]}))
    accepted = [body for kind, body in model.instances[0].events if kind == "review"]
    assert rejected
    assert "".join(body["content"] for body in accepted) == text


def test_openapi_describes_json_shared_bundle_paths_instead_of_file_transfer(cfg):
    with TestClient(service.create_app(cfg, api_key="")) as client:
        document = client.get("/openapi.json").json()
    content = document["paths"]["/v1/tasks"]["post"]["responses"]["200"]["content"]
    assert set(content) == {"application/json"}
    assert content["application/json"]["schema"]["$ref"].endswith("/ExtractionResult")
    assert "bundle_path" in document["components"]["schemas"]["ExtractionResult"]["properties"]
    assert "/v1/tasks/files" not in document["paths"]


def test_truncated_review_recovers_instead_of_rejecting_a_valid_task(cfg, model, monkeypatch):
    original = model.chat
    review_limits = []

    def chat(self, messages, **kwargs):
        if messages[0]["content"] == _REVIEW:
            review_limits.append(kwargs["max_tokens"])
            if len(review_limits) == 1:
                return {"message": {"content": "Truncated review"}, "finish_reason": "length"}
        return original(self, messages, **kwargs)

    monkeypatch.setattr(model, "chat", chat)
    with TestClient(service.create_app(cfg, api_key="")) as client:
        _bundle(client.post("/v1/tasks", json=_task()))
    assert review_limits[:2] == [1500, 3000]


def test_exhausted_model_output_is_a_logged_upstream_error_not_task_validation(cfg, model, monkeypatch, caplog):
    cfg.raw["planning"]["max_response_tokens"] = 3000
    monkeypatch.setattr(model, "chat", lambda *args, **kwargs: {
        "message": {"content": "Incomplete review"}, "finish_reason": "length",
    })
    with TestClient(service.create_app(cfg, api_key="")) as client:
        response = client.post("/v1/tasks", json=_task())

    assert response.status_code == 502
    assert "truncated" in response.json()["detail"]
    assert "max_tokens=3000" in response.json()["detail"]
    assert response.headers["x-okf-task-id"] == "sample-task"
    assert "sample-task" in caplog.text and "truncated" in caplog.text
    assert model.instances[0].closed


@pytest.mark.parametrize("path", ["../outside.txt", "/etc/passwd", "a/../../escape", "a\\b", "a//b", ".private"])
def test_file_paths_cannot_escape_the_shared_upload_root(cfg, model, path):
    with TestClient(service.create_app(cfg, api_key="")) as client:
        response = client.post("/v1/tasks", json={"items": [{"path": "a", "file_path": path}]})
    assert response.status_code == 422
    assert not model.instances


@pytest.mark.parametrize("directory_link", [False, True])
def test_shared_symlinks_are_rejected_without_reading_their_target(cfg, model, shared_dir, tmp_path, directory_link):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "private.txt").write_text("Private source", encoding="utf-8")
    shared_dir.mkdir()
    if directory_link:
        (shared_dir / "linked").symlink_to(outside, target_is_directory=True)
        source = "linked/private.txt"
    else:
        (shared_dir / "linked.txt").symlink_to(outside / "private.txt")
        source = "linked.txt"
    with TestClient(service.create_app(cfg, api_key="")) as client:
        response = client.post("/v1/tasks", json={"items": [{"path": "a", "file_path": source}]})
    assert response.status_code == 422 and "Symlinks" in response.json()["detail"]
    assert not model.instances


def test_completed_task_is_not_overwritten_by_a_duplicate_request(cfg, model, shared_dir):
    with TestClient(service.create_app(cfg, api_key="")) as client:
        first = client.post("/v1/tasks", json=_task())
        bundle = _bundle(first)
        duplicate = client.post("/v1/tasks", json=_task())
    assert duplicate.status_code == 409
    assert _bundle(first) == bundle
    assert len(model.instances) == 1


def test_running_task_is_not_started_a_second_time(cfg, model, shared_dir):
    task_dir = shared_dir / "okf-extractor/sample-task"
    task_dir.mkdir(parents=True)
    (task_dir / ".running").touch()
    with TestClient(service.create_app(cfg, api_key="")) as client:
        response = client.post("/v1/tasks", json=_task())
    assert response.status_code == 409
    assert (task_dir / ".running").is_file(), "a competing request must not remove the original lock"
    assert not model.instances


def test_exhausted_concept_extraction_reports_model_error_not_invalid_task(cfg, model, monkeypatch, shared_dir):
    def fail(*args, **kwargs):
        raise ExtractionResponseError("Extraction batch stalled; write_concept: source_files expected array")

    monkeypatch.setattr(service, "extract_bundle", fail)
    with TestClient(service.create_app(cfg, api_key="")) as client:
        response = client.post("/v1/tasks", json=_task())
    assert response.status_code == 502
    assert "source_files expected array" in response.json()["detail"]
    assert response.headers["x-okf-task-id"] == "sample-task"
    assert not list(shared_dir.rglob("bundle")) and not list(shared_dir.rglob(".running"))