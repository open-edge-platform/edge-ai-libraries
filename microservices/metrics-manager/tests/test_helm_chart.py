# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Drift guard for the Helm chart at helm/metrics-manager/.

Ensures the independently versioned chart metadata stays consistent:
  * Chart.version == "<Chart.appVersion>-helm"
  * Chart.appVersion is a release no newer than VERSION
  * Chart.name == "metrics-manager"

If `helm` is on PATH the test additionally runs `helm lint` and
`helm template` to catch syntax / rendering regressions.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest
import yaml

from docker_collectors import OPTIONS, validate_environment

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = REPO_ROOT / "VERSION"
CHART_DIR = REPO_ROOT / "helm" / "metrics-manager"
CHART_FILE = CHART_DIR / "Chart.yaml"


@pytest.fixture(scope="module")
def chart() -> dict:
    assert CHART_FILE.is_file(), f"Missing {CHART_FILE}"
    with CHART_FILE.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@pytest.fixture(scope="module")
def project_version() -> str:
    return VERSION_FILE.read_text(encoding="utf-8").strip()


def test_chart_name(chart: dict) -> None:
    assert chart["name"] == "metrics-manager"


def test_chart_app_version_is_supported_release(chart: dict, project_version: str) -> None:
    app_version = str(chart["appVersion"])
    assert re.fullmatch(
        r"\d+\.\d+\.\d+", app_version
    ), f"Chart.yaml appVersion must identify a release, got {app_version!r}"
    assert tuple(map(int, app_version.split("."))) <= tuple(map(int, project_version.split("."))), (
        f"Chart.yaml appVersion ({app_version!r}) is newer than "
        f"the current application release ({project_version!r})"
    )


def test_chart_version_carries_helm_suffix(chart: dict) -> None:
    expected = f"{chart['appVersion']}-helm"
    assert chart["version"] == expected, (
        f"Chart.yaml version ({chart['version']!r}) must equal "
        f"'<appVersion>-helm' = {expected!r}. Update chart metadata together."
    )


@pytest.mark.skipif(shutil.which("make") is None, reason="make CLI not installed")
@pytest.mark.parametrize("app_version", ["2026.2.0", "2026.4.0"])
def test_make_preserves_independent_chart_version(
    tmp_path: Path, chart: dict, app_version: str
) -> None:
    for name in ("Makefile", "VERSION", "versions.env"):
        shutil.copyfile(REPO_ROOT / name, tmp_path / name)
    chart_dir = tmp_path / "helm" / "metrics-manager"
    chart_dir.mkdir(parents=True)
    metadata = dict(chart, appVersion=app_version, version=f"{app_version}-helm")
    (chart_dir / "Chart.yaml").write_text(yaml.safe_dump(metadata), encoding="utf-8")
    package = subprocess.run(
        ["make", "--dry-run", "helm-push"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert package.returncode == 0, package.stderr
    assert f"helm push dist/helm/metrics-manager-{app_version}-helm.tgz " in package.stdout
    bump = subprocess.run(
        ["make", "--dry-run", "bump", "NEW=2026.9.0"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert bump.returncode == 0, bump.stderr
    assert "Chart.yaml" not in bump.stdout
    assert "docs/HELM.md" not in bump.stdout


def test_chart_api_version_v2(chart: dict) -> None:
    assert chart.get("apiVersion") == "v2"


def test_helmignore_present() -> None:
    assert (CHART_DIR / ".helmignore").is_file()


def test_values_file_present() -> None:
    assert (CHART_DIR / "values.yaml").is_file()


@pytest.mark.skipif(shutil.which("helm") is None, reason="helm CLI not installed")
def test_helm_lint_passes() -> None:
    result = subprocess.run(
        ["helm", "lint", str(CHART_DIR)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert (
        result.returncode == 0
    ), f"helm lint failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"


@pytest.mark.skipif(shutil.which("helm") is None, reason="helm CLI not installed")
def test_helm_template_renders() -> None:
    result = subprocess.run(
        ["helm", "template", "test", str(CHART_DIR)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert (
        result.returncode == 0
    ), f"helm template failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    rendered = result.stdout
    assert "kind: Deployment" in rendered
    assert "kind: Service" in rendered
    assert "hostPID: false" in rendered
    assert "privileged: false" in rendered
    assert "runAsNonRoot: true" in rendered
    assert "readOnlyRootFilesystem: true" in rendered
    assert "allowPrivilegeEscalation: false" in rendered
    assert "type: RuntimeDefault" in rendered
    assert "hostPath:" not in rendered


@pytest.mark.skipif(shutil.which("helm") is None, reason="helm CLI not installed")
def test_helm_template_hardware_telemetry_profile() -> None:
    result = subprocess.run(
        [
            "helm",
            "template",
            "test",
            str(CHART_DIR),
            "--set",
            "hardware.telemetry.enabled=true",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    rendered = result.stdout
    assert "hostPID: true" in rendered
    assert "privileged: true" in rendered
    assert "runAsNonRoot: false" in rendered
    assert "readOnlyRootFilesystem: false" in rendered
    assert "mountPath: /sys" in rendered
    assert "mountPath: /dev/dri" in rendered


@pytest.mark.skipif(shutil.which("helm") is None, reason="helm CLI not installed")
def test_helm_template_daemonset_mode() -> None:
    result = subprocess.run(
        [
            "helm",
            "template",
            "test",
            str(CHART_DIR),
            "--set",
            "controller.kind=DaemonSet",
            "--set",
            "hardware.gpu.enabled=false",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "kind: DaemonSet" in result.stdout
    # GPU disabled => /dev/dri host path must not be mounted.
    assert "/dev/dri" not in result.stdout


@pytest.fixture
def render(tmp_path):
    if shutil.which("helm") is None:
        pytest.skip("helm CLI not installed")

    def run(values=None, *, kube_version="1.30.0", succeeds=True, chart_path=CHART_DIR):
        path = tmp_path / "values.yaml"
        path.write_text(yaml.safe_dump(values or {}), encoding="utf-8")
        result = subprocess.run(
            [
                "helm",
                "template",
                "test",
                str(chart_path),
                "--namespace",
                "telemetry",
                "--kube-version",
                kube_version,
                "-f",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if not succeeds:
            assert result.returncode != 0, result.stdout
            return result.stderr
        assert result.returncode == 0, result.stderr
        return [doc for doc in yaml.safe_load_all(result.stdout) if doc]

    return run


def workload(docs):
    return next(doc for doc in docs if doc["kind"] in ("Deployment", "DaemonSet"))


def pod(docs):
    return workload(docs)["spec"]["template"]["spec"]


def environment(docs):
    return {entry["name"]: entry for entry in pod(docs)["containers"][0]["env"]}


@pytest.mark.parametrize("hardware", [False, True])
def test_native_environment_matches_image(render, hardware):
    docs = render({"hardware": {"telemetry": {"enabled": hardware}}})
    env = environment(docs)
    values = {key: item["value"] for key, item in env.items() if "value" in item}
    parsed = validate_environment(values)
    assert {key.removeprefix("ENABLE_") for key in env if key.startswith("ENABLE_")} == set(OPTIONS)
    assert parsed["HARDWARE_TELEMETRY_ENABLED"] is hardware
    assert values["QMASSA_FIFO_PATH"] == "/tmp/qmassa.fifo"
    assert "NPU_READER_LOG_FILE" not in env and "QMASSA_LOG_TO_STDERR" not in env
    assert pod(docs)["containers"][0]["image"] == "docker.io/intel/metrics-manager:2026.3.0"
    if hardware:
        assert (
            env["METRICS_MANAGER_HOSTNAME"]["valueFrom"]["fieldRef"]["fieldPath"] == "spec.nodeName"
        )
        assert not any(doc["kind"] == "ConfigMap" for doc in docs)
    else:
        config = next(doc["data"]["telegraf.conf"] for doc in docs if doc["kind"] == "ConfigMap")
        parsed_config = tomllib.loads(config)
        commands = {item["command"][0] for item in parsed_config["inputs"]["execd"]}
        assert commands == {
            "/usr/libexec/metrics-manager/mm-plugin-cpu",
            "/usr/libexec/metrics-manager/mm-plugin-proc",
        }
        assert "intel_powerstat" not in parsed_config["inputs"]
        assert (
            parsed_config["inputs"]["http_listener_v2"][0]["service_address"]
            == ":${TELEGRAF_HTTP_PORT}"
        )
        mounts = pod(docs)["containers"][0]["volumeMounts"]
        assert next(m for m in mounts if m["name"] == "telegraf-config")["readOnly"]


@pytest.mark.parametrize(
    "key",
    [
        "enableRaplPower",
        "enableDramBw",
        "enableDiskIo",
        "enableNetIo",
        "enableTempStats",
        "enablePsysPower",
        "enableGpuThrottle",
        "hardwareTelemetryEnabled",
    ],
)
@pytest.mark.parametrize("enabled", [False, True])
def test_removed_values_are_not_silently_ignored(render, key, enabled):
    message = render({"config": {key: enabled}}, succeeds=False)
    assert f"config.{key} was removed in 2026.3.0" in message
    assert "--reuse-values" in message


def test_reused_legacy_defaults_report_migration_before_new_fields(render, tmp_path):
    chart_dir = tmp_path / "legacy-defaults-chart"
    shutil.copytree(CHART_DIR, chart_dir)
    values_path = chart_dir / "values.yaml"
    values = yaml.safe_load(values_path.read_text(encoding="utf-8"))
    for key in ("npu", "msr", "turbostat"):
        del values["hardware"][key]
    values["config"]["enableRaplPower"] = False
    values_path.write_text(yaml.safe_dump(values), encoding="utf-8")

    message = render(chart_path=chart_dir, succeeds=False)
    assert "config.enableRaplPower was removed in 2026.3.0" in message
    assert "--reuse-values" in message
    assert "nil pointer" not in message


@pytest.mark.parametrize("kube_version", ["1.25.0", "1.29.0", "1.30.0", "1.34.0"])
@pytest.mark.parametrize("hardware", [False, True])
def test_effective_apparmor_profiles(render, kube_version, hardware):
    docs = render({"hardware": {"telemetry": {"enabled": hardware}}}, kube_version=kube_version)
    template = workload(docs)["spec"]["template"]
    security = pod(docs)["containers"][0]["securityContext"]
    assert security["privileged"] is hardware
    assert security["allowPrivilegeEscalation"] is hardware
    assert security["runAsNonRoot"] is not hardware
    if int(kube_version.split(".")[1]) >= 30:
        assert security["appArmorProfile"]["type"] == (
            "Unconfined" if hardware else "RuntimeDefault"
        )
        assert "container.apparmor.security.beta.kubernetes.io/metrics-manager" not in (
            template["metadata"]["annotations"] or {}
        )
    else:
        assert "appArmorProfile" not in security
        assert template["metadata"]["annotations"][
            "container.apparmor.security.beta.kubernetes.io/metrics-manager"
        ] == ("unconfined" if hardware else "runtime/default")


def test_hardware_devices_and_disabled_gpu(render):
    docs = render(
        {
            "hardware": {
                "telemetry": {"enabled": True},
                "gpu": {"enabled": False},
                "npu": {"enabled": True},
                "msr": {"enabled": True},
                "turbostat": {"hostPath": "/usr/bin/turbostat"},
            },
            "config": {"enableTurbostat": True, "hostnameOverride": "node-a"},
            "pod": {"supplementalGroups": [1234]},
            "image": {"tag": "2026.3.0-extended-rc1"},
        }
    )
    paths = {v["hostPath"]["path"] for v in pod(docs)["volumes"] if "hostPath" in v}
    assert paths == {"/sys", "/run", "/dev/accel", "/dev/cpu", "/usr/bin/turbostat"}
    assert environment(docs)["HARDWARE_TELEMETRY_ENABLED"]["value"] == "false"
    assert environment(docs)["METRICS_MANAGER_HOSTNAME"]["value"] == "node-a"
    assert pod(docs)["securityContext"]["supplementalGroups"] == [1234]
    assert pod(docs)["containers"][0]["image"].endswith(":2026.3.0-extended-rc1")


@pytest.mark.parametrize("kind", ["Deployment", "DaemonSet"])
def test_network_ports_and_service_monitor(render, kind):
    docs = render(
        {
            "controller": {"kind": kind},
            "pod": {"hostNetwork": True},
            "config": {"enableNetwork": True},
            "service": {"metricsPort": 19090, "telegrafPort": 19273, "telegrafHttpPort": 18186},
            "serviceMonitor": {"enabled": True, "namespace": "monitoring"},
        }
    )
    assert pod(docs)["dnsPolicy"] == "ClusterFirstWithHostNet"
    env = environment(docs)
    assert env["TELEGRAF_HTTP_ENDPOINT"]["value"] == "http://localhost:18186/write"
    assert env["PROMETHEUS_TELEGRAF_ENDPOINT"]["value"] == "http://localhost:19273"
    assert env["ENABLE_NETWORK"]["value"] == "true"
    monitor = next(doc for doc in docs if doc["kind"] == "ServiceMonitor")
    assert monitor["metadata"]["namespace"] == "monitoring"
    assert monitor["spec"]["namespaceSelector"]["matchNames"] == ["telemetry"]
    service = next(doc for doc in docs if doc["kind"] == "Service")
    assert {port["port"] for port in service["spec"]["ports"]} == {19090, 19273, 18186}


def test_custom_configs_are_readonly_and_roll_pods(render):
    custom = "[[inputs.mem]]\n"
    docs = render({"telegraf": {"config": custom, "extraConfigs": {"custom.conf": custom}}})
    data = {doc["metadata"]["name"]: doc["data"] for doc in docs if doc["kind"] == "ConfigMap"}
    assert data["test-metrics-manager-telegraf"]["telegraf.conf"] == custom.rstrip()
    assert data["test-metrics-manager-dropins"]["custom.conf"] == custom.rstrip()
    mounts = {m["name"]: m for m in pod(docs)["containers"][0]["volumeMounts"]}
    assert mounts["telegraf-config"]["readOnly"] and mounts["telegraf-dropins"]["readOnly"]
    checksums = workload(docs)["spec"]["template"]["metadata"]["annotations"]
    changed = render(
        {
            "telegraf": {
                "config": custom + "# changed\n",
                "extraConfigs": {"custom.conf": "# changed\n"},
            }
        }
    )
    other = workload(changed)["spec"]["template"]["metadata"]["annotations"]
    assert checksums["checksum/telegraf-config"] != other["checksum/telegraf-config"]
    assert checksums["checksum/telegraf-dropins"] != other["checksum/telegraf-dropins"]


@pytest.mark.parametrize(
    "values,message",
    [
        ({"controller": {"kind": "StatefulSet"}}, "controller.kind"),
        ({"customMetrics": {"storage": "invalid"}}, "customMetrics.storage"),
        ({"service": {"telegrafPort": 9090}}, "service ports"),
        ({"service": {"metricsPort": 65536}}, "service ports"),
        ({"hardware": {"telemetry": {"enabled": "false"}}}, "YAML boolean"),
        ({"config": {"enableNetwork": "yes"}}, "config.enableNetwork"),
        ({"config": {"enableTurbostat": True}}, "Turbostat requires"),
        ({"config": {"turbostatInterval": "0"}}, "positive integer"),
        ({"hardware": {"npu": {"enabled": True}}}, "host mounts require"),
        ({"telegraf": {"extraConfigs": {"../bad.conf": "test"}}}, "*.conf filenames"),
        (
            {"config": {"extraEnv": [{"name": "ENABLE_NET_IO", "value": "true"}]}},
            "legacy or duplicate",
        ),
        (
            {"config": {"extraEnv": [{"name": "TELEGRAF_PORT", "value": "9999"}]}},
            "legacy or duplicate",
        ),
        (
            {
                "config": {
                    "extraEnv": [{"name": "TEST", "value": "a"}, {"name": "TEST", "value": "b"}]
                }
            },
            "legacy or duplicate",
        ),
    ],
)
def test_invalid_values_fail_before_install(render, values, message):
    assert message in render(values, succeeds=False)


def test_packaged_chart_contains_restricted_config(render, tmp_path):
    subprocess.run(
        ["helm", "package", str(CHART_DIR), "--destination", str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    docs = render(chart_path=tmp_path / "metrics-manager-2026.3.0-helm.tgz")
    config = next(doc["data"]["telegraf.conf"] for doc in docs if doc["kind"] == "ConfigMap")
    assert "mm-plugin-proc" in config


@pytest.mark.parametrize("storage", ["emptyDir", "pvc", "none"])
@pytest.mark.parametrize("existing", ["", "operator-claim"])
def test_custom_metrics_volume_modes(render, storage, existing):
    docs = render({"customMetrics": {"storage": storage, "existingClaim": existing}})
    volumes = {v["name"]: v for v in pod(docs)["volumes"]}
    claims = [doc for doc in docs if doc["kind"] == "PersistentVolumeClaim"]
    if storage == "none":
        assert "custom-metrics" not in volumes and not claims
    elif storage == "emptyDir":
        assert "emptyDir" in volumes["custom-metrics"] and not claims
    else:
        assert volumes["custom-metrics"]["persistentVolumeClaim"]["claimName"] == (
            existing or "test-metrics-manager-custom-metrics"
        )
        assert len(claims) == (0 if existing else 1)


def test_extra_env_secret_reference_and_supplemental_groups(render):
    entry = {
        "name": "APPLICATION_TOKEN",
        "valueFrom": {
            "secretKeyRef": {"name": "existing-secret", "key": "token"},
        },
    }
    docs = render(
        {
            "config": {"extraEnv": [entry]},
            "hardware": {"telemetry": {"enabled": True}},
            "pod": {"supplementalGroups": [1234]},
        }
    )
    assert environment(docs)["APPLICATION_TOKEN"] == entry
    assert pod(docs)["securityContext"]["supplementalGroups"] == [992, 1234]
