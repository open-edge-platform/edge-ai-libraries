# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import ast
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENT = ROOT / "deployment/docker"
ENGINE_COMPOSE = "docker-compose.yml"
MILVUS_COMPOSE = "docker-compose-milvus.yml"
NEBULA_COMPOSE = "docker-compose-nebula.yml"
OKF_COMPOSE = "docker-compose-okf-extractor.yml"


@pytest.fixture
def compose_config(tmp_path):
    if shutil.which("docker") is None:
        pytest.skip("Docker Compose is not installed")
    version = subprocess.run(["docker", "compose", "version"], capture_output=True)
    if version.returncode:
        pytest.skip("Docker Compose plugin is not installed")
    env_file = tmp_path / "compose.env"
    env_file.write_text("", encoding="utf-8")

    def render(filename, *, env_values=None, **overrides):
        env_file.write_text(
            "\n".join(f"{key}={value}" for key, value in (env_values or {}).items()),
            encoding="utf-8",
        )
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("ENGINE_", "MINIO_", "MILVUS_", "ETCD_", "NEBULA_", "OKF_EXTRACTOR_"))
            and key not in {"VIDEOGROUPID", "RENDERGROUPID", "TZ", "HF_ENDPOINT"}
        }
        environment.update(overrides)
        result = subprocess.run(
            [
                "docker", "compose", "--env-file", str(env_file),
                "-f", str(DEPLOYMENT / filename), "config", "--format", "json",
            ],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )
        return json.loads(result.stdout)

    return render


@pytest.mark.parametrize(
    ("username", "password"),
    [
        ("minioadmin", "minioadmin"),
        ("service-user", "test:password@with/slash?#"),
        ("", ""),
    ],
)
def test_minio_and_milvus_share_configurable_credentials(compose_config, username, password):
    services = compose_config(
        MILVUS_COMPOSE, MINIO_ROOT_USER=username, MINIO_ROOT_PASSWORD=password
    )["services"]
    minio = services["minio"]["environment"]
    milvus = services["milvus-standalone"]["environment"]

    assert minio["MINIO_ROOT_USER"] == (username or "minioadmin")
    assert minio["MINIO_ROOT_PASSWORD"] == (password or "minioadmin")
    assert milvus["MINIO_ACCESS_KEY_ID"] == minio["MINIO_ROOT_USER"]
    assert milvus["MINIO_SECRET_ACCESS_KEY"] == minio["MINIO_ROOT_PASSWORD"]


def test_every_engine_environment_setting_is_forwarded_and_documented():
    tree = ast.parse((ROOT / "src/config.py").read_text(encoding="utf-8"))
    settings = {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            isinstance(node.func, ast.Attribute) and node.func.attr == "getenv"
            or isinstance(node.func, ast.Name)
            and (node.func.id.startswith("_env_") or node.func.id == "_backend")
        )
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
        and node.args[0].value.startswith("ENGINE_")
    }
    compose = yaml.safe_load((DEPLOYMENT / ENGINE_COMPOSE).read_text(encoding="utf-8"))
    forwarded = {
        name
        for name in compose["services"]["engine"]["environment"]
        if name.startswith("ENGINE_")
    }

    # Both ways: a forwarded variable config.py no longer reads is a dead knob.
    assert settings == forwarded
    guide = (ROOT / "docs/user-guide/user-guide.md").read_text(encoding="utf-8")
    assert all(f"`{setting}`" in guide for setting in settings)


def test_every_engine_environment_setting_has_a_compose_default():
    compose = yaml.safe_load((DEPLOYMENT / ENGINE_COMPOSE).read_text(encoding="utf-8"))
    environment = compose["services"]["engine"]["environment"]
    # ENGINE_PORT is fed by ENGINE_CONTAINER_PORT, the one variable not named after itself.
    source = {"ENGINE_PORT": "ENGINE_CONTAINER_PORT"}
    # Whisper uses an explicitly empty language for automatic detection. It has
    # a default for unset environments, but must not replace an empty override.
    separator = {"ENGINE_ASR_LANGUAGE": "-"}

    assert {
        name: value
        for name, value in environment.items()
        if name.startswith("ENGINE_")
        and not str(value).startswith(
            "${%s%s" % (source.get(name, name), separator.get(name, ":-"))
        )
    } == {}


@pytest.mark.parametrize(("language", "expected"), [(None, "zh"), ("", ""), ("en", "en")])
def test_asr_language_preserves_explicit_auto_detection(compose_config, language, expected):
    overrides = {} if language is None else {"ENGINE_ASR_LANGUAGE": language}
    service = compose_config(ENGINE_COMPOSE, **overrides)["services"]["engine"]

    assert service["environment"]["ENGINE_ASR_LANGUAGE"] == expected


def test_compose_has_no_model_download_endpoint():
    compose = yaml.safe_load((DEPLOYMENT / ENGINE_COMPOSE).read_text(encoding="utf-8"))

    assert "HF_ENDPOINT" not in compose["services"]["engine"]["environment"]


@pytest.mark.parametrize("endpoint", [None, "", "https://unused.invalid"])
def test_model_download_endpoint_is_not_forwarded_to_engine(compose_config, endpoint):
    overrides = {} if endpoint is None else {"HF_ENDPOINT": endpoint}
    service = compose_config(ENGINE_COMPOSE, **overrides)["services"]["engine"]

    assert "HF_ENDPOINT" not in service["environment"]


def test_dotenv_runtime_values_override_compose_defaults(compose_config):
    service = compose_config(
        ENGINE_COMPOSE,
        env_values={"ENGINE_DOC_EMBEDDING_MODEL_ID": "example/dense", "ENGINE_RERANK_BACKEND": "remote_openai_compatible"},
    )["services"]["engine"]

    assert service["environment"]["ENGINE_DOC_EMBEDDING_MODEL_ID"] == "example/dense"
    assert service["environment"]["ENGINE_RERANK_BACKEND"] == "remote_openai_compatible"
    assert service["environment"]["ENGINE_LAYOUT_DEVICE"] == "CPU"
    assert service["environment"]["ENGINE_UPLOAD_DIR"] == "/workspace/uploads"
    assert service["environment"]["ENGINE_MODEL_ROOT_PATH"] == "/workspace/models"


@pytest.mark.parametrize("overrides,expected", [
    ({}, "/workspace/models"),
    ({"ENGINE_WORKSPACE": "/srv/engine-state"}, "/srv/engine-state/models"),
    ({"ENGINE_MODEL_ROOT_PATH": ""}, "/workspace/models"),
    ({"ENGINE_WORKSPACE": "/srv/engine-state", "ENGINE_MODEL_ROOT_PATH": ""}, "/srv/engine-state/models"),
    ({"ENGINE_MODEL_ROOT_PATH": "/shared/models"}, "/shared/models"),
])
def test_compose_model_root_follows_workspace_unless_overridden(compose_config, overrides, expected):
    service = compose_config(ENGINE_COMPOSE, **overrides)["services"]["engine"]

    assert service["environment"]["ENGINE_MODEL_ROOT_PATH"] == expected


def test_compose_forwards_document_embedding_settings(compose_config):
    overrides = {
        "ENGINE_DOC_EMBEDDING_BACKEND": "remote_openai_compatible",
        "ENGINE_DOC_EMBEDDING_MODEL_ID": "example/documents",
        "ENGINE_DOC_EMBEDDING_DEVICE": "CPU",
        "ENGINE_DOC_EMBEDDING_API_BASE": "http://embedding.internal/v1",
        "ENGINE_DOC_EMBEDDING_API_KEY": "test-key",
    }
    service = compose_config(ENGINE_COMPOSE, env_values=overrides)["services"]["engine"]

    assert {name: service["environment"][name] for name in overrides} == overrides


def test_compose_uses_one_model_root_instead_of_per_model_paths():
    compose = yaml.safe_load((DEPLOYMENT / ENGINE_COMPOSE).read_text(encoding="utf-8"))
    environment = compose["services"]["engine"]["environment"]

    assert "ENGINE_MODEL_ROOT_PATH" in environment
    assert not any(name.startswith("ENGINE_EMBEDDING_") for name in environment)
    assert not any(name.endswith("_MODEL_PATH") for name in environment)


def test_engine_ports_workspace_and_runtime_overrides_are_consistent(compose_config):
    service = compose_config(
        ENGINE_COMPOSE,
        ENGINE_PORT="26022",
        ENGINE_CONTAINER_PORT="18022",
        ENGINE_WORKSPACE="/srv/engine-state",
        ENGINE_LAYOUT_DEVICE="GPU",
        ENGINE_RERANK_API_BASE="http://reranker.internal",
        ENGINE_RERANK_API_KEY="rerank-key",
        ENGINE_DOC_EMBEDDING_MODEL_ID="example/dense",
    )["services"]["engine"]

    assert service["environment"]["ENGINE_PORT"] == "18022"
    assert service["ports"][0]["published"] == "26022"
    assert service["ports"][0]["target"] == 18022
    assert service["environment"]["ENGINE_WORKSPACE"] == "/srv/engine-state"
    assert service["volumes"][0]["target"] == "/srv/engine-state"
    assert service["environment"]["ENGINE_LAYOUT_DEVICE"] == "GPU"
    assert service["environment"]["ENGINE_RERANK_API_BASE"] == "http://reranker.internal"
    assert service["environment"]["ENGINE_RERANK_API_KEY"] == "rerank-key"
    assert service["environment"]["ENGINE_DOC_EMBEDDING_MODEL_ID"] == "example/dense"
    assert service["environment"]["ENGINE_MODEL_ROOT_PATH"] == "/srv/engine-state/models"
    assert "${ENGINE_PORT}" in " ".join(service["healthcheck"]["test"])


def test_minio_endpoint_overrides_reach_milvus_and_healthcheck(compose_config):
    services = compose_config(
        MILVUS_COMPOSE, MINIO_API_PORT="19000", MINIO_CONSOLE_PORT="19001"
    )["services"]

    assert services["milvus-standalone"]["environment"]["MINIO_ADDRESS"] == "minio:19000"
    assert ":19000" in services["minio"]["command"]
    assert ":19001" in services["minio"]["command"]
    # `mc ready` takes an alias, not a URL; the alias carries the port.
    assert services["minio"]["environment"]["MC_HOST_local"] == "http://localhost:19000"
    assert services["minio"]["healthcheck"]["test"][-2:] == ["ready", "local"]


@pytest.mark.parametrize(
    ("env_values", "owner"),
    [({}, "65532:65532"), ({"MINIO_UID": "1234", "MINIO_GID": "5678"}, "1234:5678")],
)
def test_minio_data_directory_is_handed_to_the_minio_user_first(
    compose_config, env_values, owner
):
    services = compose_config(MILVUS_COMPOSE, env_values=env_values)["services"]
    init, minio = services["minio-init"], services["minio"]

    assert minio["user"] == owner
    assert minio["depends_on"]["minio-init"]["condition"] == "service_completed_successfully"
    assert init["user"] == "0:0"
    assert init["volumes"][0]["target"] == "/minio_data"
    assert init["volumes"][0]["source"] == minio["volumes"][0]["source"]
    assert f"chown -h {owner} " in init["command"][0]


def test_etcd_port_and_limits_are_forwarded_consistently(compose_config):
    services = compose_config(
        MILVUS_COMPOSE,
        ETCD_CLIENT_PORT="12379",
        ETCD_AUTO_COMPACTION_RETENTION="2000",
        ETCD_QUOTA_BACKEND_BYTES="8589934592",
        MILVUS_HEALTHCHECK_RETRIES="5",
    )["services"]
    etcd = services["etcd"]

    assert etcd["environment"]["ETCD_AUTO_COMPACTION_RETENTION"] == "2000"
    assert etcd["environment"]["ETCD_QUOTA_BACKEND_BYTES"] == "8589934592"
    assert "http://0.0.0.0:12379" in etcd["command"]
    assert "--endpoints=http://localhost:12379" in etcd["healthcheck"]["test"]
    assert services["milvus-standalone"]["environment"]["ETCD_ENDPOINTS"] == "etcd:12379"
    long_running = [service for service in services.values() if "healthcheck" in service]
    assert len(long_running) == 3
    assert all(service["healthcheck"]["retries"] == 5 for service in long_running)


def test_nebula_internal_ports_update_dependents_and_healthchecks(compose_config):
    services = compose_config(
        NEBULA_COMPOSE,
        NEBULA_META_INTERNAL_PORT="20559",
        NEBULA_GRAPH_INTERNAL_PORT="20669",
        NEBULA_STORAGE_INTERNAL_PORT="20779",
        NEBULA_GRAPH_INTERNAL_HTTP_PORT="29669",
        NEBULA_VERSION="test-version",
        NEBULA_NOFILE_LIMIT="32768",
    )["services"]

    for name in ("nebula-metad0", "nebula-storaged0", "nebula-graphd"):
        service = services[name]
        assert "--meta_server_addrs=nebula-metad0:20559" in service["command"]
        assert service["image"].endswith(":test-version")
        assert service["ulimits"]["nofile"] == {"soft": 32768, "hard": 32768}
    graph = services["nebula-graphd"]
    assert graph["ports"][0]["target"] == 20669
    assert "--ws_http_port=29669" in graph["command"]
    assert "http://nebula-graphd:29669/status" in graph["healthcheck"]["test"]
    initialization = services["nebula-storage-init"]["command"]
    assert initialization[initialization.index("-port") + 1] == "20669"
    assert 'ADD HOSTS "nebula-storaged0":20779' in initialization


@pytest.mark.parametrize("filename", [ENGINE_COMPOSE, MILVUS_COMPOSE, NEBULA_COMPOSE, OKF_COMPOSE])
def test_compose_stacks_use_the_configured_shared_network(compose_config, filename):
    compose = compose_config(
        filename,
        ENGINE_NETWORK="custom-engine-network",
        ENGINE_NO_PROXY="localhost,service.internal",
    )

    assert compose["networks"]["default"]["name"] == "custom-engine-network"
    for service in compose["services"].values():
        if "environment" in service:
            assert service["environment"]["no_proxy"] == "localhost,service.internal"
            assert service["environment"]["NO_PROXY"] == "localhost,service.internal"


@pytest.mark.parametrize("overrides", [
    {},
    {"ENGINE_WORKSPACE_PATH": "/srv/state", "ENGINE_WORKSPACE": "/data"},
    {"ENGINE_UPLOAD_PATH": "/srv/shared-uploads", "ENGINE_UPLOAD_DIR": "/shared/uploads"},
])
def test_engine_and_extractor_share_the_same_writable_upload_directory(compose_config, overrides):
    engine = compose_config(ENGINE_COMPOSE, **overrides)["services"]["engine"]
    extractor = compose_config(OKF_COMPOSE, **overrides)["services"]["okf-extractor"]
    target = engine["environment"]["ENGINE_UPLOAD_DIR"]
    engine_upload = next(volume for volume in engine["volumes"] if volume["target"] == target)
    extractor_upload = next(volume for volume in extractor["volumes"] if volume["target"] == target)

    assert extractor["environment"]["ENGINE_UPLOAD_DIR"] == target
    assert engine_upload["source"] == extractor_upload["source"]
    assert not engine_upload.get("read_only") and not extractor_upload.get("read_only")
    assert extractor["environment"]["OKF_EXTRACTOR_HOST"] == "0.0.0.0"
    assert extractor["user"] == "1000:1000"


def test_user_guide_does_not_contain_developer_home_paths():
    guide = (ROOT / "docs/user-guide/user-guide.md").read_text(encoding="utf-8")

    assert "/home/" not in guide
    assert "/Users/" not in guide


def test_shell_helpers_use_shared_environment_defaults():
    environment = dict(os.environ)
    environment.pop("ENGINE_URL", None)
    environment.update(
        ENGINE_PORT="26022", CURL_TIMEOUT="45", ASSET_LOOKUP_PAGE_SIZE="5000"
    )
    result = subprocess.run(
        [
            "bash", "-c",
            'source "$1"; printf "%s\\n" "$ENGINE_URL" "$CURL_TIMEOUT" "$ASSET_LOOKUP_PAGE_SIZE"',
            "_", str(ROOT / "scripts/lib.sh"),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.stdout.splitlines() == ["http://localhost:26022", "45", "5000"]


@pytest.mark.parametrize("path", [ROOT / "README.md", ROOT / "docs/user-guide/user-guide.md"])
def test_documented_shell_examples_have_valid_syntax(path):
    document = path.read_text(encoding="utf-8")
    examples = re.findall(
        r"^[ \t]*```bash\n(.*?)^[ \t]*```[ \t]*$",
        document,
        flags=re.DOTALL | re.MULTILINE,
    )
    assert examples
    for example in examples:
        result = subprocess.run(
            ["bash", "-n"], input=example, capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr
    for example in re.findall(r"python3 - <<'PY'\n(.*?)\nPY", document, flags=re.DOTALL):
        ast.parse(example)
