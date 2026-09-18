# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import itertools
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any
import unittest


ROOT = Path(__file__).resolve().parents[3]
PROFILES = ("cpu", "gpu", "npu", "igpu-wsl")


class HardwareDetectionTest(unittest.TestCase):
    def test_hardware_precedence(self) -> None:
        for npu, wsl, gpu in itertools.product(("0", "1"), repeat=3):
            expected = (
                "npu"
                if npu == "1"
                else "igpu-wsl"
                if wsl == "1"
                else "gpu"
                if gpu == "1"
                else "cpu"
            )
            with (
                self.subTest(npu=npu, wsl=wsl, gpu=gpu),
                tempfile.TemporaryDirectory() as directory,
            ):
                subprocess.run(
                    ["bash", "-s", "--", str(ROOT / "setup_env.sh")],
                    cwd=directory,
                    env=dict(os.environ, HAS_NPU=npu, HAS_WSL=wsl, HAS_GPU=gpu),
                    input=r"""
compgen() {
    case "$2" in
        /dev/accel/*) [[ "$HAS_NPU" == 1 ]] ;;
        /dev/dri/*) [[ "$HAS_GPU" == 1 ]] ;;
        *) return 1 ;;
    esac
}
function [ {
    if [[ "$1" == -c && "$2" == /dev/dxg ]]; then
        [[ "$HAS_WSL" == 1 ]]
    else
        builtin [ "$@"
    fi
}
getent() { printf 'render:x:992:\n'; }
source "$1"
""",
                    text=True,
                    capture_output=True,
                    check=True,
                )
                settings = dict(
                    line.split("=", 1)
                    for line in (Path(directory) / ".env").read_text().splitlines()
                    if "=" in line
                )
                self.assertEqual(settings["COMPOSE_PROFILES"], expected)
                self.assertEqual(
                    settings["RENDER_GROUP_ID"],
                    "992" if expected in ("gpu", "npu") else "",
                )


class ComposeProfileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not shutil.which("docker"):
            raise unittest.SkipTest("Docker Compose is required for config validation")
        result = subprocess.run(["docker", "compose", "version"], capture_output=True)
        if result.returncode:
            raise unittest.SkipTest("Docker Compose is required for config validation")

    def compose_config(self, profile: str, mode: str) -> dict[str, Any]:
        files = ["compose.yml", f"compose.{profile}.yml"]
        if mode == "dev":
            files.append("compose.dev.yml")
        elif mode == "voice":
            files.append("compose.voice.yml")
            if profile != "cpu":
                files.append(f"compose.voice.{profile}.yml")
        elif mode == "experimental":
            files = [
                "compose.yml",
                "compose.experimental.yml",
                f"compose.{profile}.yml",
            ]
            if profile == "igpu-wsl":
                files.append("compose.experimental.igpu-wsl.yml")
        command = ["docker", "compose", "--env-file", os.devnull]
        for filename in files:
            command.extend(["-f", filename])
        command.extend(["config", "--format", "json"])
        env = dict(
            os.environ,
            COMPOSE_PROFILES=profile,
            DOCKER_TAG="test",
            RENDER_GROUP_ID="992",
            NPU_GROUP_ID="993",
            VOICE_ASR_DEVICE="",
            VOICE_TTS_DEVICE="",
            VOICE_TTS_DTYPE="",
            TIMESERIES_USER_NAME="timeseries_user",
            TIMESERIES_UID="2999",
        )
        result = subprocess.run(
            command, cwd=ROOT, env=env, capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)["services"]

    def test_profile_matrix(self) -> None:
        for profile, mode in itertools.product(
            PROFILES, ("base", "dev", "voice", "experimental")
        ):
            with self.subTest(profile=profile, mode=mode):
                services = self.compose_config(profile, mode)
                self.assertEqual(services["vippet"]["profiles"], [profile])
                if profile == "igpu-wsl":
                    selected = ["vippet", "metrics-manager"]
                    if mode == "voice":
                        selected.extend(["audio-analyzer", "text-to-speech"])
                    if mode == "experimental":
                        selected.append("ia-time-series-analytics-microservice")
                        timeseries = services["ia-time-series-analytics-microservice"]
                        self.assertFalse(timeseries.get("group_add"))
                        self.assertTrue(
                            any(
                                mount["type"] == "volume"
                                for mount in timeseries["volumes"]
                            )
                        )
                    for name in selected:
                        service = services[name]
                        self.assertEqual(
                            [device["source"] for device in service["devices"]],
                            ["/dev/dxg"],
                        )
                        mounts = {
                            mount["target"]: mount for mount in service["volumes"]
                        }
                        self.assertEqual(
                            mounts["/usr/lib/wsl"]["source"], "/usr/lib/wsl"
                        )
                        self.assertTrue(mounts["/usr/lib/wsl"]["read_only"])
                        self.assertNotIn("/dev/dri", mounts)
                else:
                    expected_devices = {
                        "cpu": [],
                        "gpu": ["/dev/dri"],
                        "npu": ["/dev/dri", "/dev/accel"],
                    }
                    self.assertEqual(
                        [
                            device["source"]
                            for device in services["vippet"].get("devices", [])
                        ],
                        expected_devices[profile],
                    )
                if mode == "voice":
                    asr = services["audio-analyzer"]
                    tts = services["text-to-speech"]
                    asr_device = {
                        "cpu": "CPU",
                        "gpu": "GPU",
                        "npu": "NPU",
                        "igpu-wsl": "GPU",
                    }[profile]
                    self.assertEqual(
                        asr["environment"]["AUDIO_ANALYZER__MODELS__ASR__DEVICE"],
                        asr_device,
                    )
                    self.assertEqual(
                        tts["environment"]["TEXT_TO_SPEECH__MODELS__TTS__DEVICE"],
                        "CPU" if profile in ("cpu", "igpu-wsl") else "GPU",
                    )
                    self.assertEqual(
                        tts["environment"]["TEXT_TO_SPEECH__MODELS__TTS__DTYPE"],
                        "int8" if profile in ("cpu", "igpu-wsl") else "fp16",
                    )
                    for service in (asr, tts):
                        self.assertEqual(service["user"], "1000:1000")
                        self.assertIn("ALL", service["cap_drop"])
                        self.assertFalse(service.get("privileged", False))


class MakeRoutingTest(unittest.TestCase):
    def test_hardware_overrides_for_lifecycle_targets(self) -> None:
        voice_targets = (
            "run-voice",
            "build-voice",
            "pull-voice",
            "stop-voice",
        )
        experimental_targets = (
            "build-experimental",
            "run-experimental",
            "stop-experimental",
            "clean-experimental",
        )
        targets = (
            *voice_targets,
            *experimental_targets,
            "run",
            "stop",
            "build",
            "build-dev",
            "run-dev",
        )
        commands = {
            "run": ["up", "-d"],
            "run-voice": ["up", "-d", "--no-build"],
            "build-voice": ["build"],
            "pull-voice": ["pull"],
            "stop": ["down"],
            "stop-voice": ["down"],
            "build-experimental": ["build"],
            "run-experimental": ["up", "-d", "--remove-orphans"],
            "stop-experimental": ["down"],
            "clean-experimental": ["down", "-v"],
            "build": ["build"],
            "build-dev": ["build"],
            "run-dev": ["up", "-d"],
        }
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            docker = temporary / "docker"
            docker.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
            docker.chmod(0o700)
            for profile, target in itertools.product(PROFILES, targets):
                with self.subTest(profile=profile, target=target):
                    (temporary / ".env").write_text(f"COMPOSE_PROFILES={profile}\n")
                    result = subprocess.run(
                        [
                            "make",
                            "--silent",
                            "-f",
                            str(ROOT / "Makefile"),
                            "-o",
                            "env-setup",
                            target,
                        ],
                        cwd=temporary,
                        env=dict(
                            os.environ,
                            PATH=f"{temporary}{os.pathsep}{os.environ['PATH']}",
                        ),
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    args = result.stdout.splitlines()
                    expected = ["compose.yml", f"compose.{profile}.yml"]
                    if target in voice_targets:
                        expected.append("compose.voice.yml")
                        if profile != "cpu":
                            expected.append(f"compose.voice.{profile}.yml")
                    elif target in experimental_targets:
                        expected.insert(1, "compose.experimental.yml")
                        if profile == "igpu-wsl":
                            expected.append("compose.experimental.igpu-wsl.yml")
                    elif target in ("build-dev", "run-dev"):
                        expected.append("compose.dev.yml")
                    expected_args = ["compose"]
                    for filename in expected:
                        expected_args.extend(["-f", filename])
                    self.assertEqual(args, [*expected_args, *commands[target]])


if __name__ == "__main__":
    unittest.main()
