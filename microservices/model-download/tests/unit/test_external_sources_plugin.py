# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import os
import tempfile
from pathlib import Path

import pytest

import src.plugins.external_sources_plugin as esp
from src.plugins.external_sources_plugin import ExternalSourcesPlugin
from src.core.interfaces import ListingNotSupportedError


@pytest.fixture
def plugin():
    return ExternalSourcesPlugin()


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


class TestPluginProperties:
    def test_plugin_properties(self, plugin):
        assert plugin.plugin_name == "external-sources"
        assert plugin.plugin_type == "downloader"

    def test_supported_hubs(self, plugin):
        hubs = plugin.plugin_supported_hubs()
        assert "pipeline-zoo-models" in hubs
        assert "remote-url" in hubs
        assert "omz" in hubs

    def test_listing_properties(self, plugin):
        assert plugin.supports_listing is True
        assert plugin.listing_filter_fields == ["search"]

    @pytest.mark.parametrize(
        "hub,expected",
        [
            ("omz", True),
            ("OMZ", True),
            ("pipeline-zoo-models", True),
            ("pipeline_zoo_models", True),
            ("remote-url", True),
            ("huggingface", False),
            ("", False),
        ],
    )
    def test_can_handle(self, plugin, hub, expected):
        assert plugin.can_handle("model_a", hub) is expected

    def test_task_based_api_not_supported(self, plugin):
        with pytest.raises(NotImplementedError):
            plugin.get_download_tasks("model_a")
        with pytest.raises(NotImplementedError):
            plugin.download_task(object(), "/tmp")


class TestDownloadValidation:
    def test_missing_hub(self, plugin, temp_dir):
        with pytest.raises(ValueError, match="requires 'hub'"):
            plugin.download("model_a", temp_dir)

    def test_unsupported_hub(self, plugin, temp_dir):
        with pytest.raises(ValueError, match="Unsupported hub"):
            plugin.download("model_a", temp_dir, hub="does-not-exist")

    @pytest.mark.parametrize("bad_name", ["", "   "])
    def test_empty_model_name(self, plugin, temp_dir, bad_name):
        with pytest.raises(ValueError, match="Model name is required"):
            plugin.download(bad_name, temp_dir, hub="omz")

    @pytest.mark.parametrize("bad_name", ["foo/bar", "../escape", ".hidden"])
    def test_invalid_model_name(self, plugin, temp_dir, bad_name):
        with pytest.raises(ValueError, match="Invalid model name"):
            plugin.download(bad_name, temp_dir, hub="omz")


class TestTarballDownload:
    _ALLOWED_URL = (
        "https://github.com/open-edge-platform/edge-ai-resources/raw/main/"
        "timeseries-udf-deployment-packages/{name}.tar"
    )

    def test_runtime_url_tarball(self, plugin, temp_dir, monkeypatch):
        captured = {}

        def fake_extract(url, target):
            captured["url"] = url
            os.makedirs(target, exist_ok=True)
            Path(target, "model.xml").write_text("<xml/>", encoding="utf-8")

        monkeypatch.setattr(plugin, "_download_and_extract_tarball", fake_extract)

        result = plugin.download(
            "pkg-a", temp_dir, hub="remote-url", config={"url": self._ALLOWED_URL}
        )

        # {name} is substituted before download.
        assert captured["url"].endswith("/pkg-a.tar")
        target = Path(temp_dir) / "remote-url" / "pkg-a"
        assert (target / "model.xml").is_file()
        assert result["success"] is True
        assert result["source"] == "remote-url"

    def test_shared_archive_tarball(self, plugin, temp_dir, monkeypatch):
        # Build a fake extracted shared archive and skip the network fetch.
        extract_root = Path(temp_dir) / "extracted"
        model_src = extract_root / "pipeline-zoo-models-main" / "storage" / "dbnet"
        os.makedirs(model_src, exist_ok=True)
        Path(model_src, "model.xml").write_text("<xml/>", encoding="utf-8")

        monkeypatch.setattr(
            plugin, "_ensure_shared_archive_extracted", lambda hub, profile: str(extract_root)
        )

        result = plugin.download("dbnet", temp_dir, hub="pipeline-zoo-models")

        target = Path(temp_dir) / "pipeline-zoo-models" / "dbnet"
        assert (target / "model.xml").is_file()
        assert result["success"] is True

    def test_shared_archive_tarball_all_downloads_each_model_under_its_name(self, plugin, temp_dir, monkeypatch):
        extract_root = Path(temp_dir) / "extracted"
        storage_dir = extract_root / "pipeline-zoo-models-main" / "storage"
        for name in ["dbnet", "yolov5m-320"]:
            model_src = storage_dir / name
            model_src.mkdir(parents=True, exist_ok=True)
            Path(model_src, "model.xml").write_text("<xml/>", encoding="utf-8")

        monkeypatch.setattr(
            plugin, "_ensure_shared_archive_extracted", lambda hub, profile: str(extract_root)
        )

        result = plugin.download("all", temp_dir, hub="pipeline-zoo-models")

        dbnet = Path(temp_dir) / "pipeline-zoo-models" / "dbnet"
        yolo = Path(temp_dir) / "pipeline-zoo-models" / "yolov5m-320"
        assert (dbnet / "model.xml").is_file()
        assert (yolo / "model.xml").is_file()
        # multi-model requests should resolve to hub root, not all/
        assert not (Path(temp_dir) / "pipeline-zoo-models" / "all").exists()
        assert result["download_path"].endswith("pipeline-zoo-models")
        assert result["success"] is True

    def test_shared_archive_tarball_comma_separated_downloads_each_model_under_its_name(self, plugin, temp_dir, monkeypatch):
        extract_root = Path(temp_dir) / "extracted"
        storage_dir = extract_root / "pipeline-zoo-models-main" / "storage"
        for name in ["dbnet", "yolov5m-320"]:
            model_src = storage_dir / name
            model_src.mkdir(parents=True, exist_ok=True)
            Path(model_src, "model.xml").write_text("<xml/>", encoding="utf-8")

        monkeypatch.setattr(
            plugin, "_ensure_shared_archive_extracted", lambda hub, profile: str(extract_root)
        )

        result = plugin.download("dbnet,yolov5m-320", temp_dir, hub="pipeline-zoo-models")

        dbnet = Path(temp_dir) / "pipeline-zoo-models" / "dbnet"
        yolo = Path(temp_dir) / "pipeline-zoo-models" / "yolov5m-320"
        assert (dbnet / "model.xml").is_file()
        assert (yolo / "model.xml").is_file()
        # multi-model requests should resolve to hub root, not comma-joined folder
        assert not (Path(temp_dir) / "pipeline-zoo-models" / "dbnet,yolov5m-320").exists()
        assert result["download_path"].endswith("pipeline-zoo-models")
        assert result["success"] is True

    def test_download_cleans_up_on_failure(self, plugin, temp_dir, monkeypatch):
        def boom(url, target):
            os.makedirs(target, exist_ok=True)
            Path(target, "partial.bin").write_text("x", encoding="utf-8")
            raise RuntimeError("network down")

        monkeypatch.setattr(plugin, "_download_and_extract_tarball", boom)

        with pytest.raises(RuntimeError, match="network down"):
            plugin.download(
                "pkg-a", temp_dir, hub="remote-url", config={"url": self._ALLOWED_URL}
            )

        assert not (Path(temp_dir) / "remote-url" / "pkg-a").exists()


class TestListModels:
    def test_pipeline_zoo_listing(self, plugin, temp_dir, monkeypatch):
        extract_root = Path(temp_dir) / "extracted"
        storage_dir = extract_root / "pipeline-zoo-models-main" / "storage"
        (storage_dir / "dbnet").mkdir(parents=True)
        (storage_dir / "yolov5m-320").mkdir()

        monkeypatch.setattr(
            plugin, "_ensure_shared_archive_extracted", lambda hub, profile: str(extract_root)
        )

        result = plugin.list_models(hub="pipeline-zoo-models", filters={"search": "yolo"})

        assert result["total"] == 1
        assert result["items"][0]["name"] == "yolov5m-320"
        assert result["items"][0]["owner"] == "dlstreamer"
        assert set(result["items"][0]) == {"name", "owner"}

    def test_pipeline_zoo_listing_stringifies_search(self, plugin, temp_dir, monkeypatch):
        extract_root = Path(temp_dir) / "extracted"
        storage_dir = extract_root / "pipeline-zoo-models-main" / "storage"
        (storage_dir / "123-model").mkdir(parents=True)
        (storage_dir / "abc-model").mkdir()

        monkeypatch.setattr(
            plugin, "_ensure_shared_archive_extracted", lambda hub, profile: str(extract_root)
        )

        result = plugin.list_models(hub="pipeline-zoo-models", filters={"search": 123})

        assert result["total"] == 1
        assert result["items"][0]["name"] == "123-model"

    def test_pipeline_zoo_listing_pagination(self, plugin, temp_dir, monkeypatch):
        extract_root = Path(temp_dir) / "extracted"
        storage_dir = extract_root / "pipeline-zoo-models-main" / "storage"
        for name in ["a", "b", "c"]:
            (storage_dir / name).mkdir(parents=True)

        monkeypatch.setattr(
            plugin, "_ensure_shared_archive_extracted", lambda hub, profile: str(extract_root)
        )

        result = plugin.list_models(hub="pipeline-zoo-models", limit=1, offset=1)

        assert result["total"] == 3
        assert [item["name"] for item in result["items"]] == ["b"]

    @pytest.mark.parametrize("hub", ["remote-url", "omz"])
    def test_listing_unsupported_external_hubs(self, plugin, hub):
        with pytest.raises(ListingNotSupportedError):
            plugin.list_models(hub=hub)


class TestRuntimeUrlValidation:
    _ALLOWLIST = [
        "github.com/open-edge-platform/edge-ai-resources/",
        "github.com/vkb1/edge-ai-resources/",
    ]

    def test_allowed_url_passes(self):
        url = (
            "https://github.com/open-edge-platform/edge-ai-resources/raw/main/"
            "timeseries-udf-deployment-packages/m.tar"
        )
        # Should not raise.
        ExternalSourcesPlugin._validate_runtime_url(url, self._ALLOWLIST)

    def test_vkb_github_raw_url_passes(self):
        url = (
            "https://github.com/vkb1/edge-ai-resources/raw/refs/heads/feature/vkb1/new-udf/"
            "timeseries-udf-deployment-packages/wind-turbine-anomaly-detection.tar"
        )
        # Should not raise.
        ExternalSourcesPlugin._validate_runtime_url(url, self._ALLOWLIST)

    def test_non_https_rejected(self):
        url = "http://github.com/open-edge-platform/edge-ai-resources/m.tar"
        with pytest.raises(ValueError, match="https"):
            ExternalSourcesPlugin._validate_runtime_url(url, self._ALLOWLIST)

    def test_disallowed_host_rejected(self):
        url = "https://evil.com/open-edge-platform/edge-ai-resources/m.tar"
        with pytest.raises(ValueError, match="not in allowlist"):
            ExternalSourcesPlugin._validate_runtime_url(url, self._ALLOWLIST)

    def test_disallowed_path_rejected(self):
        url = "https://github.com/other-org/some-repo/m.tar"
        with pytest.raises(ValueError, match="not in allowlist"):
            ExternalSourcesPlugin._validate_runtime_url(url, self._ALLOWLIST)

    def test_substring_bypass_rejected(self):
        # Allowlist prefix appears in the query, not the host+path.
        url = "https://evil.com/x?github.com/open-edge-platform/edge-ai-resources/m.tar"
        with pytest.raises(ValueError, match="not in allowlist"):
            ExternalSourcesPlugin._validate_runtime_url(url, self._ALLOWLIST)

    def test_embedded_credentials_rejected(self):
        url = (
            "https://user:pass@github.com/open-edge-platform/edge-ai-resources/m.tar"
        )
        with pytest.raises(ValueError, match="credentials"):
            ExternalSourcesPlugin._validate_runtime_url(url, self._ALLOWLIST)

    def test_empty_allowlist_rejects_all(self):
        url = (
            "https://github.com/open-edge-platform/edge-ai-resources/m.tar"
        )
        with pytest.raises(ValueError, match="disabled"):
            ExternalSourcesPlugin._validate_runtime_url(url, [])

    def test_resolve_allowlist_from_profile(self, monkeypatch):
        monkeypatch.delenv("EXTERNAL_SOURCES_URL_ALLOWLIST", raising=False)
        profile = {"allowed_prefixes": ["github.com/open-edge-platform/edge-ai-resources/"]}
        assert ExternalSourcesPlugin._resolve_allowlist(profile) == [
            "github.com/open-edge-platform/edge-ai-resources/"
        ]

    def test_env_replaces_profile_allowlist(self, monkeypatch):
        monkeypatch.setenv(
            "EXTERNAL_SOURCES_URL_ALLOWLIST",
            "github.com/myorg/, raw.githubusercontent.com/myorg/",
        )
        profile = {"allowed_prefixes": ["github.com/open-edge-platform/edge-ai-resources/"]}
        assert ExternalSourcesPlugin._resolve_allowlist(profile) == [
            "github.com/myorg/",
            "raw.githubusercontent.com/myorg/",
        ]

    def test_resolved_config_overrides_env_and_profile(self, monkeypatch):
        monkeypatch.setenv(
            "EXTERNAL_SOURCES_URL_ALLOWLIST",
            "github.com/envorg/",
        )
        profile = {"allowed_prefixes": ["github.com/open-edge-platform/edge-ai-resources/"]}
        resolved_config = {
            "EXTERNAL_SOURCES_URL_ALLOWLIST": "github.com/reqorg/, raw.githubusercontent.com/reqorg/",
        }
        assert ExternalSourcesPlugin._resolve_allowlist(profile, resolved_config) == [
            "github.com/reqorg/",
            "raw.githubusercontent.com/reqorg/",
        ]

    def test_resolved_config_empty_falls_back_to_env(self, monkeypatch):
        monkeypatch.setenv(
            "EXTERNAL_SOURCES_URL_ALLOWLIST",
            "github.com/envorg/",
        )
        profile = {"allowed_prefixes": ["github.com/open-edge-platform/edge-ai-resources/"]}
        # Blank/whitespace override is ignored; env wins.
        assert ExternalSourcesPlugin._resolve_allowlist(profile, {"EXTERNAL_SOURCES_URL_ALLOWLIST": "   "}) == [
            "github.com/envorg/",
        ]

    def test_config_keys_declares_allowlist(self, plugin):
        keys = {key.name: key for key in plugin.config_keys()}
        assert "EXTERNAL_SOURCES_URL_ALLOWLIST" in keys
        assert keys["EXTERNAL_SOURCES_URL_ALLOWLIST"].sensitive is False

    def test_url_hub_requires_config_url(self, plugin, temp_dir):
        with pytest.raises(ValueError, match="requires 'url'"):
            plugin.download("pkg-a", temp_dir, hub="remote-url")


class TestOmzDownload:
    @pytest.fixture
    def fake_omz_bin(self, tmp_path, monkeypatch):
        bin_dir = tmp_path / "venv-omz" / "bin"
        bin_dir.mkdir(parents=True)
        (bin_dir / "omz_downloader").write_text("")
        (bin_dir / "omz_converter").write_text("")
        monkeypatch.setattr(esp, "_OMZ_VENV_BIN", bin_dir)
        return bin_dir

    def test_omz_tools_missing(self, plugin, temp_dir, tmp_path, monkeypatch):
        monkeypatch.setattr(esp, "_OMZ_VENV_BIN", tmp_path / "no-venv" / "bin")
        with pytest.raises(RuntimeError, match="OMZ tools not found"):
            plugin.download("some-model", temp_dir, hub="omz")

    def test_omz_download_and_materialize(
        self, plugin, temp_dir, fake_omz_bin, monkeypatch
    ):
        model_name = "some-model"

        def fake_run(command):
            if command[0].endswith("omz_converter"):
                out_dir = command[command.index("--output_dir") + 1]
                model_dir = Path(out_dir) / "public" / model_name
                model_dir.mkdir(parents=True, exist_ok=True)
                (model_dir / f"{model_name}.xml").write_text("<xml/>", encoding="utf-8")
                (model_dir / f"{model_name}.bin").write_text("bin", encoding="utf-8")

        monkeypatch.setattr(plugin, "_run_omz_tool", fake_run)
        # Model not in rules -> post-processing is skipped (no network).
        monkeypatch.setattr(esp, "_load_omz_rules", lambda: {})

        result = plugin.download(model_name, temp_dir, hub="omz")

        target = Path(temp_dir) / "omz" / model_name
        assert (target / f"{model_name}.xml").is_file()
        assert (target / f"{model_name}.bin").is_file()
        assert result["success"] is True
        assert result["source"] == "omz"

    def test_omz_converter_no_output_raises(
        self, plugin, temp_dir, fake_omz_bin, monkeypatch
    ):
        monkeypatch.setattr(plugin, "_run_omz_tool", lambda command: None)
        monkeypatch.setattr(esp, "_load_omz_rules", lambda: {})

        with pytest.raises(FileNotFoundError, match="produced no output"):
            plugin.download("some-model", temp_dir, hub="omz")


class TestRunOmzTool:
    def test_path_injection(self, monkeypatch, tmp_path):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        monkeypatch.setattr(esp, "_OMZ_VENV_BIN", bin_dir)

        captured = {}

        class FakeCompleted:
            returncode = 0
            stdout = ""
            stderr = ""

        def fake_run(command, capture_output, text, check, env):
            captured["env_path"] = env["PATH"]
            return FakeCompleted()

        monkeypatch.setattr(esp.subprocess, "run", fake_run)

        ExternalSourcesPlugin._run_omz_tool(["omz_downloader", "--name", "x"])

        assert captured["env_path"].startswith(str(bin_dir) + os.pathsep)

    def test_nonzero_return_raises(self, monkeypatch):
        class FakeCompleted:
            returncode = 1
            stdout = ""
            stderr = "boom"

        monkeypatch.setattr(
            esp.subprocess, "run", lambda *a, **k: FakeCompleted()
        )

        with pytest.raises(RuntimeError, match="OMZ tool failed"):
            ExternalSourcesPlugin._run_omz_tool(["omz_converter"])

    def test_executable_missing_raises(self, monkeypatch):
        def raise_fnf(*a, **k):
            raise FileNotFoundError()

        monkeypatch.setattr(esp.subprocess, "run", raise_fnf)

        with pytest.raises(RuntimeError, match="OMZ tool not found"):
            ExternalSourcesPlugin._run_omz_tool(["missing_tool"])


class TestPostProcessing:
    def test_is_remote_source(self):
        assert ExternalSourcesPlugin._is_remote_source("https://x/y.json") is True
        assert ExternalSourcesPlugin._is_remote_source("http://x/y.json") is True
        assert ExternalSourcesPlugin._is_remote_source("/opt/x/y.json") is False

    def test_skip_when_no_rule(self, plugin, temp_dir, monkeypatch):
        monkeypatch.setattr(esp, "_load_omz_rules", lambda: {})
        # Should not raise; simply skips.
        plugin._apply_omz_post_processing("unknown-model", temp_dir)

    def test_missing_model_proc_src_raises(self, plugin, temp_dir, monkeypatch):
        monkeypatch.setattr(
            esp, "_load_omz_rules", lambda: {"m": {"model_proc_dst": "m.json"}}
        )
        with pytest.raises(ValueError, match="missing required 'model_proc_src'"):
            plugin._apply_omz_post_processing("m", temp_dir)

    def test_copy_model_proc_local(self, temp_dir):
        src = Path(temp_dir) / "src.json"
        src.write_text('{"a": 1}', encoding="utf-8")

        ExternalSourcesPlugin._copy_model_proc(
            model_name="m",
            target_dir=temp_dir,
            model_proc_src=str(src),
            model_proc_dst="out.json",
        )

        assert (Path(temp_dir) / "out.json").read_text(encoding="utf-8") == '{"a": 1}'

    def test_copy_model_proc_local_missing(self, temp_dir):
        with pytest.raises(FileNotFoundError, match="model_proc source not found"):
            ExternalSourcesPlugin._copy_model_proc(
                model_name="m",
                target_dir=temp_dir,
                model_proc_src=str(Path(temp_dir) / "nope.json"),
                model_proc_dst="out.json",
            )

    def test_copy_model_proc_url(self, temp_dir, monkeypatch):
        def fake_urlretrieve(url, destination):
            Path(destination).write_text('{"from": "url"}', encoding="utf-8")

        monkeypatch.setattr(esp.urllib.request, "urlretrieve", fake_urlretrieve)

        ExternalSourcesPlugin._copy_model_proc(
            model_name="m",
            target_dir=temp_dir,
            model_proc_src="https://example/model_proc.json",
            model_proc_dst="out.json",
        )

        assert (Path(temp_dir) / "out.json").read_text(encoding="utf-8") == '{"from": "url"}'

    def test_inject_labels_local(self, temp_dir):
        json_path = Path(temp_dir) / "mp.json"
        json_path.write_text(json.dumps({"output_postproc": [{}]}), encoding="utf-8")

        labels_path = Path(temp_dir) / "labels.txt"
        labels_path.write_text("0 tench\n1 goldfish\n", encoding="utf-8")

        ExternalSourcesPlugin._inject_labels_into_model_proc(
            model_name="m",
            labels_path=str(labels_path),
            json_path=str(json_path),
        )

        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert data["output_postproc"][0]["labels"] == ["tench", "goldfish"]

    def test_inject_labels_url(self, temp_dir, monkeypatch):
        json_path = Path(temp_dir) / "mp.json"
        json_path.write_text(json.dumps({"output_postproc": [{}]}), encoding="utf-8")

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b"cat\ndog\n"

        monkeypatch.setattr(
            esp.urllib.request, "urlopen", lambda url: FakeResponse()
        )

        ExternalSourcesPlugin._inject_labels_into_model_proc(
            model_name="m",
            labels_path="https://example/labels.txt",
            json_path=str(json_path),
        )

        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert data["output_postproc"][0]["labels"] == ["cat", "dog"]

    def test_inject_labels_id_without_label_raises(self, temp_dir):
        json_path = Path(temp_dir) / "mp.json"
        json_path.write_text(json.dumps({"output_postproc": [{}]}), encoding="utf-8")

        labels_path = Path(temp_dir) / "labels.txt"
        labels_path.write_text("42\n", encoding="utf-8")

        with pytest.raises(ValueError, match="ID without label"):
            ExternalSourcesPlugin._inject_labels_into_model_proc(
                model_name="m",
                labels_path=str(labels_path),
                json_path=str(json_path),
            )

    def test_full_post_processing_with_labels(self, plugin, temp_dir, monkeypatch):
        # End-to-end: copy model_proc + inject labels, all local.
        src = Path(temp_dir) / "src.json"
        src.write_text(json.dumps({"output_postproc": [{}]}), encoding="utf-8")

        labels_path = Path(temp_dir) / "labels.txt"
        labels_path.write_text("0 a\n1 b\n", encoding="utf-8")

        monkeypatch.setattr(
            esp,
            "_load_omz_rules",
            lambda: {
                "m": {
                    "model_proc_src": str(src),
                    "model_proc_dst": "m.json",
                    "labels_src": str(labels_path),
                    "inject_labels": True,
                }
            },
        )

        plugin._apply_omz_post_processing("m", temp_dir)

        data = json.loads((Path(temp_dir) / "m.json").read_text(encoding="utf-8"))
        assert data["output_postproc"][0]["labels"] == ["a", "b"]

    def test_missing_model_proc_dst_raises(self, plugin, temp_dir, monkeypatch):
        monkeypatch.setattr(
            esp,
            "_load_omz_rules",
            lambda: {"m": {"model_proc_src": "https://example/mp.json"}},
        )
        with pytest.raises(ValueError, match="missing required 'model_proc_dst'"):
            plugin._apply_omz_post_processing("m", temp_dir)

    def test_inject_labels_missing_labels_file(self, temp_dir):
        json_path = Path(temp_dir) / "mp.json"
        json_path.write_text(json.dumps({"output_postproc": [{}]}), encoding="utf-8")

        with pytest.raises(FileNotFoundError, match="labels source not found"):
            ExternalSourcesPlugin._inject_labels_into_model_proc(
                model_name="m",
                labels_path=str(Path(temp_dir) / "nope.txt"),
                json_path=str(json_path),
            )

    def test_inject_labels_missing_json(self, temp_dir):
        labels_path = Path(temp_dir) / "labels.txt"
        labels_path.write_text("0 a\n", encoding="utf-8")

        with pytest.raises(FileNotFoundError, match="model_proc JSON not found"):
            ExternalSourcesPlugin._inject_labels_into_model_proc(
                model_name="m",
                labels_path=str(labels_path),
                json_path=str(Path(temp_dir) / "missing.json"),
            )

    def test_inject_labels_malformed_postproc(self, temp_dir):
        json_path = Path(temp_dir) / "mp.json"
        json_path.write_text(json.dumps({"output_postproc": []}), encoding="utf-8")

        labels_path = Path(temp_dir) / "labels.txt"
        labels_path.write_text("0 a\n", encoding="utf-8")

        with pytest.raises(ValueError, match="non-empty output_postproc"):
            ExternalSourcesPlugin._inject_labels_into_model_proc(
                model_name="m",
                labels_path=str(labels_path),
                json_path=str(json_path),
            )

    def test_inject_labels_postproc_not_object(self, temp_dir):
        json_path = Path(temp_dir) / "mp.json"
        json_path.write_text(json.dumps({"output_postproc": ["x"]}), encoding="utf-8")

        labels_path = Path(temp_dir) / "labels.txt"
        labels_path.write_text("0 a\n", encoding="utf-8")

        with pytest.raises(ValueError, match="must be an object"):
            ExternalSourcesPlugin._inject_labels_into_model_proc(
                model_name="m",
                labels_path=str(labels_path),
                json_path=str(json_path),
            )


class TestMaterializeAndHostPath:
    def test_materialize_overwrites_existing(self, temp_dir):
        tmp_src = Path(temp_dir) / "tmp"
        model_dir = tmp_src / "public" / "m"
        model_dir.mkdir(parents=True)
        (model_dir / "m.xml").write_text("new", encoding="utf-8")

        target = Path(temp_dir) / "target"
        target.mkdir()
        # Pre-existing file that must be replaced.
        (target / "m.xml").write_text("old", encoding="utf-8")

        ExternalSourcesPlugin._materialize_omz_artefacts("m", str(tmp_src), str(target))

        assert (target / "m.xml").read_text(encoding="utf-8") == "new"

    def test_host_path_rewrite(self, plugin, temp_dir, monkeypatch):
        # download() rewrites /opt/models/ to the MODEL_PATH host prefix.
        monkeypatch.setenv("MODEL_PATH", "hostmodels")
        monkeypatch.setattr(esp, "_load_omz_rules", lambda: {})
        # Pretend the real conversion happened; assert only the host-path mapping.
        monkeypatch.setattr(plugin, "_fetch_omz", lambda *a, **k: None)

        result = plugin.download("m", "/opt/models/sub", hub="omz")

        assert result["download_path"].startswith("hostmodels/")
        assert "/opt/models/" not in result["download_path"]
