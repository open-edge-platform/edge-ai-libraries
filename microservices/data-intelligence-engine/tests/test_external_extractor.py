# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Engine/task-service shared-file exchange; HTTP carries only metadata."""
import json
from types import SimpleNamespace

import httpx
import pytest

import config
from core.content import ContentBlock, ContentStream
from core.knowledge.extractor import ExternalExtractor, ExternalExtractorConfig
from core.knowledge import extractor as client_module
from core.knowledge.okf import parse_okf_bundle


@pytest.fixture(autouse=True)
def shared_dir(tmp_path, monkeypatch):
    root = tmp_path / "uploads"
    monkeypatch.setattr(config, "UPLOAD_DIR", str(root))
    return root


def _result(request, shared_dir):
    task = json.loads(request.content)
    relative = f"okf-extractor/{task['task_id']}/bundle"
    bundle = shared_dir / relative
    (bundle / "topic").mkdir(parents=True)
    (bundle / "index.md").write_text("# OKF Bundle Index\n", encoding="utf-8")
    (bundle / "topic/corpus.md").write_text(
        "---\ntype: Topic\ntitle: Corpus\n---\nCorpus summary.\n", encoding="utf-8",
    )
    (bundle / "instructions.yaml").write_text("instructions:\n  DOMAIN: task-specific\n", encoding="utf-8")
    return httpx.Response(200, json={
        "task_id": task["task_id"], "bundle_path": relative, "concept_count": 1,
    })


def _asset(asset_id="a", text="content"):
    return SimpleNamespace(
        asset_id=asset_id, origin="file:///old-machine/doc.pdf", file_name="doc.pdf",
        content=ContentStream(asset_id=asset_id, blocks=[ContentBlock("b", text=text)]),
    )


def _transport(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setattr(client_module.httpx, "Client", lambda **kwargs: original(
        transport=httpx.MockTransport(handler), **kwargs,
    ))


def test_all_documents_form_one_task_using_only_shared_file_references(tmp_path, monkeypatch, shared_dir):
    calls = []
    texts = []

    def handle(request):
        calls.append(request)
        task = json.loads(request.content)
        texts.extend((shared_dir / item["file_path"]).read_text() for item in task["items"])
        return _result(request, shared_dir)

    _transport(monkeypatch, handle)
    extractor = ExternalExtractor(ExternalExtractorConfig(
        url="http://extractor:8080", api_key="private", timeout=42,
        options={"language": "zh", "goal": "Keep recurring entities"},
    ))
    output = tmp_path / "cache"
    bundles = extractor.extract([_asset("a", "First source"), _asset("b", "Last source")], output)

    assert len(calls) == len(bundles) == 1
    request = calls[0]
    assert str(request.url) == "http://extractor:8080/v1/tasks"
    assert request.headers["authorization"] == "Bearer private"
    assert request.extensions["timeout"]["read"] == 42
    task = json.loads(request.content)
    assert texts == ["First source", "Last source"]
    assert request.headers["accept"] == "application/json"
    assert b"First source" not in request.content and b"Last source" not in request.content
    assert all("content" not in item and "data_base64" not in item for item in task["items"])
    assert [item["asset_id"] for item in task["items"]] == ["a", "b"]
    assert len({item["path"] for item in task["items"]}) == 2  # duplicate basenames are safe
    assert task["options"] == extractor.config.options
    assert [node.title for node in parse_okf_bundle(bundles[0])] == ["Corpus"]
    manifest = json.loads((bundles[0] / "task.json").read_text())
    assert manifest["sources"] == [{"path": item["path"], "asset_id": item["asset_id"]} for item in task["items"]]
    assert list(output.iterdir()) == bundles
    assert list((shared_dir / "okf-extractor").iterdir()) == [], "completed staging files are cleaned"


def test_content_stream_keeps_all_blocks_in_reading_order_and_figure_captions(tmp_path, monkeypatch, shared_dir):
    received = []
    asset = _asset()
    asset.content.blocks = [
        ContentBlock("last", text="tail", reading_order=2),
        ContentBlock("figure", kind="image", caption="A useful caption", reading_order=1),
        ContentBlock("first", text="head", reading_order=0),
    ]

    def handle(request):
        item = json.loads(request.content)["items"][0]
        received.append((shared_dir / item["file_path"]).read_text())
        assert item["path"].endswith("doc.pdf") and item["file_path"].endswith("content.txt")
        return _result(request, shared_dir)

    _transport(monkeypatch, handle)
    ExternalExtractor(ExternalExtractorConfig(url="http://extractor")).extract([asset], tmp_path)
    assert received == ["head\n\nA useful caption\n\ntail"]


def test_file_only_assets_are_staged_locally_not_uploaded_over_http(tmp_path, monkeypatch, shared_dir):
    source = tmp_path / "input.txt"
    source.write_text("file contents", encoding="utf-8")
    received = []

    def handle(request):
        item = json.loads(request.content)["items"][0]
        received.append(item)
        assert (shared_dir / item["file_path"]).read_bytes() == b"file contents"
        assert b"file contents" not in request.content
        return _result(request, shared_dir)

    _transport(monkeypatch, handle)
    asset = SimpleNamespace(asset_id="a", origin=source.as_uri())
    ExternalExtractor(ExternalExtractorConfig(url="http://extractor")).extract([asset], tmp_path / "out")
    assert received[0]["file_path"].startswith("okf-extractor/")
    assert "data_base64" not in received[0] and not received[0]["file_path"].startswith("/")
    assert source.read_text() == "file contents", "original files are never deleted"


def test_uploads_are_named_by_their_upload_path_and_others_by_asset(tmp_path, monkeypatch, shared_dir):
    upload = shared_dir / "library-1" / "02_theft.md"
    upload.parent.mkdir(parents=True)
    upload.write_text("Uploaded case", encoding="utf-8")
    hidden = shared_dir / ".private" / "02_theft.md"
    hidden.parent.mkdir()
    hidden.write_text("Hidden folder", encoding="utf-8")
    received = []

    def handle(request):
        received.extend(item["path"] for item in json.loads(request.content)["items"])
        return _result(request, shared_dir)

    _transport(monkeypatch, handle)
    ExternalExtractor(ExternalExtractorConfig(url="http://extractor")).extract([
        SimpleNamespace(asset_id="upload", origin=upload.as_uri(),
                        content=ContentStream(asset_id="upload", blocks=[ContentBlock("b", text="Uploaded case")])),
        SimpleNamespace(asset_id="hidden", origin=hidden.as_uri(),
                        content=ContentStream(asset_id="hidden", blocks=[ContentBlock("b", text="Hidden")])),
        _asset("elsewhere"),
    ], tmp_path / "out")

    assert received[0] == "library-1/02_theft.md"
    assert received[1].endswith("/02_theft.md") and not received[1].startswith(".")
    assert received[2].endswith("/doc.pdf") and received[2] != "doc.pdf"


def test_existing_shared_upload_is_referenced_in_place(tmp_path, monkeypatch, shared_dir):
    source = shared_dir / "original.txt"
    shared_dir.mkdir()
    source.write_text("Existing upload", encoding="utf-8")

    def handle(request):
        item = json.loads(request.content)["items"][0]
        assert item["file_path"] == "original.txt"
        return _result(request, shared_dir)

    _transport(monkeypatch, handle)
    asset = SimpleNamespace(asset_id="file", origin=source.as_uri())
    ExternalExtractor(ExternalExtractorConfig(url="http://extractor")).extract([asset], tmp_path / "cache")
    assert source.read_text() == "Existing upload"


@pytest.mark.parametrize("path", ["../escaped", "/absolute", "a/../../escape", "a\\b", "other-task/bundle"])
def test_unexpected_shared_bundle_paths_are_refused_without_touching_other_files(tmp_path, monkeypatch, path):
    output = tmp_path / "cache"

    def handle(request):
        return httpx.Response(200, json={"task_id": json.loads(request.content)["task_id"], "bundle_path": path})

    _transport(monkeypatch, handle)
    with pytest.raises(ValueError, match="unexpected task ID or shared bundle_path"):
        ExternalExtractor(ExternalExtractorConfig(url="http://extractor")).extract([_asset()], output)
    assert not output.exists()


def test_symlinked_bundle_files_are_refused(tmp_path, monkeypatch, shared_dir):
    private = tmp_path / "outside.md"
    private.write_text("private", encoding="utf-8")

    def handle(request):
        result = _result(request, shared_dir)
        bundle = shared_dir / result.json()["bundle_path"]
        (bundle / "link.md").symlink_to(private)
        return result

    _transport(monkeypatch, handle)
    with pytest.raises(ValueError, match="symlink"):
        ExternalExtractor(ExternalExtractorConfig(url="http://extractor")).extract([_asset()], tmp_path / "cache")
    assert private.read_text() == "private"


@pytest.mark.parametrize("status,payload,media_type,error", [
    (503, b"unavailable", "text/plain", httpx.HTTPStatusError),
    (200, b"not json", "application/json", ValueError),
    (200, b'{}', "application/json", ValueError),
    (200, b"archive bytes", "application/zip", ValueError),
])
def test_remote_failures_are_not_silently_treated_as_success(tmp_path, monkeypatch, status, payload, media_type, error):
    _transport(monkeypatch, lambda request: httpx.Response(
        status, content=payload, headers={"content-type": media_type},
    ))
    with pytest.raises(error):
        ExternalExtractor(ExternalExtractorConfig(url="http://extractor")).extract([_asset()], tmp_path / "cache")
    assert not (tmp_path / "cache").exists()


def test_remote_error_detail_is_reported_instead_of_only_the_http_status(tmp_path, monkeypatch, caplog):
    detail = "Instruction planning returned an empty or truncated response"
    _transport(monkeypatch, lambda request: httpx.Response(422, json={"detail": detail}))

    with pytest.raises(httpx.HTTPStatusError) as failed:
        ExternalExtractor(ExternalExtractorConfig(url="http://extractor")).extract([_asset()], tmp_path / "cache")

    assert "422" in str(failed.value) and detail in str(failed.value)
    assert detail in caplog.text
    assert not (tmp_path / "cache").exists()


def test_validation_error_reporting_does_not_echo_document_contents_or_credentials(tmp_path, monkeypatch, caplog):
    _transport(monkeypatch, lambda request: httpx.Response(422, json={"detail": [{
        "loc": ["body", "items", 0, "path"], "msg": "Invalid path",
        "input": "private document contents", "ctx": {"api_key": "private-token"},
    }]}))
    extractor = ExternalExtractor(ExternalExtractorConfig(url="http://extractor", api_key="private-token"))

    with pytest.raises(httpx.HTTPStatusError) as failed:
        extractor.extract([_asset()], tmp_path)

    message = str(failed.value) + caplog.text
    assert "body.items.0.path" in message and "Invalid path" in message
    assert "private document contents" not in message and "private-token" not in message


def test_remote_error_body_is_bounded_and_not_required_to_be_json(tmp_path, monkeypatch):
    _transport(monkeypatch, lambda request: httpx.Response(502, text="upstream failed " + "x" * 100000))

    with pytest.raises(httpx.HTTPStatusError) as failed:
        ExternalExtractor(ExternalExtractorConfig(url="http://extractor")).extract([_asset()], tmp_path)

    assert "upstream failed" in str(failed.value)
    assert len(str(failed.value)) < 5000


def test_an_empty_task_does_not_make_a_request_or_create_output(tmp_path):
    target = tmp_path / "absent"
    assert ExternalExtractor(ExternalExtractorConfig(url="http://extractor")).extract([], target) == []
    assert not target.exists()


def test_no_output_dir_leaves_a_ready_bundle_in_the_shared_folder(monkeypatch, shared_dir):
    _transport(monkeypatch, lambda request: _result(request, shared_dir))
    bundle = ExternalExtractor(ExternalExtractorConfig(url="http://extractor")).extract([_asset()])[0]
    assert bundle.is_relative_to(shared_dir)
    assert (bundle / "index.md").is_file()
    assert not (bundle.parent / "sources").exists()


def test_timeout_retains_staged_inputs_while_the_service_may_still_be_running(tmp_path, monkeypatch, shared_dir):
    def timeout(request):
        raise httpx.ReadTimeout("still extracting", request=request)

    _transport(monkeypatch, timeout)
    with pytest.raises(TimeoutError, match="may still be working"):
        ExternalExtractor(ExternalExtractorConfig(url="http://extractor")).extract([_asset()], tmp_path / "cache")
    assert len(list(shared_dir.rglob("content.txt"))) == 1
    assert not (tmp_path / "cache").exists()


@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), -1, 0])
def test_timeout_must_be_finite_and_positive(timeout):
    with pytest.raises(ValueError, match="finite and positive"):
        ExternalExtractorConfig.from_options({"url": "http://extractor", "timeout": timeout})

def test_a_timeout_says_the_extractor_may_still_be_working(tmp_path, monkeypatch, shared_dir):
    def slow(request):
        raise httpx.ReadTimeout("timed out", request=request)

    _transport(monkeypatch, slow)
    extractor = ExternalExtractor(ExternalExtractorConfig(url="http://extractor", timeout=300))
    with pytest.raises(TimeoutError, match=r"did not finish within 300s \(external_extractor.timeout\)"):
        extractor.extract([_asset()], tmp_path / "out")
    assert ExternalExtractorConfig.from_options({"url": "http://x"}).timeout == 3600
