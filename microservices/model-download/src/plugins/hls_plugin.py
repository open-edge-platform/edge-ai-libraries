# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""HLS plugin for downloading fixed medical demo assets.

This plugin acts as a thin wrapper that invokes existing helper scripts under
`scripts/` to prepare assets for three task families:

* 3D pose estimation demo (human-pose-estimation-3d-0001)
* Remote photoplethysmography (MTTS-CAN) demo
* AI ECG demo models (pre-converted IR pairs)

The heavy lifting remains inside the original scripts so we minimize the risk
of regressions and keep maintenance localized.
"""

import asyncio
import os
import subprocess
import venv
from pathlib import Path
from typing import Dict, Any

from src.core.interfaces import ModelDownloadPlugin
from src.utils.logging import logger

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

SUPPORTED_TYPES = {
    "3d-pose": SCRIPTS_DIR / "3d_pose_model_convert.py",
    "rppg": SCRIPTS_DIR / "rppg_download_assets.py",
    "ai-ecg": SCRIPTS_DIR / "ecg_download_assets.sh",
}
#corresponding models for each type are expected to be downloaded/converted by the above scripts into:
Models_Supported={
    "3d-pose": "human-pose-estimation-3d-0001",
    "rppg": "mtts_can",
    "ai-ecg": ["ecg_17920_ir10_fp16", "ecg_8960_ir10_fp16"],
}

# HLS-dedicated virtual environment
HLS_VENV_PATH = Path("/opt/hls_venv")
HLS_VENV_PYTHON = HLS_VENV_PATH / "bin" / "python"
HLS_VENV_MARKER = HLS_VENV_PATH / ".hls_deps_installed"
HLS_DEPENDENCIES = [
    "openvino==2025.4.0",
    "torch==2.9.1+cpu",
    "torchvision==0.24.1+cpu",
    "tensorflow",
    "tqdm>=4.67",
]

_hls_venv_lock = asyncio.Lock()


class HlsPlugin(ModelDownloadPlugin):
    """Downloader plugin that orchestrates fixed HLS assets."""

    @property
    def plugin_name(self) -> str:
        return "hls"

    def can_handle(self, model_name: str, hub: str, **kwargs) -> bool:
        model_type = (kwargs.get("type") or "").lower()
        return hub.lower() == "hls" and model_type in SUPPORTED_TYPES

    async def _ensure_hls_venv(self) -> Path:
        """Return the HLS venv Python executable, creating the venv and
        installing dependencies on the very first call.  Subsequent calls
        return immediately once the marker file exists."""
        async with _hls_venv_lock:
            if HLS_VENV_MARKER.exists():
                logger.info("hls_venv_reuse", path=str(HLS_VENV_PATH))
                return HLS_VENV_PYTHON

            logger.info("hls_venv_create", path=str(HLS_VENV_PATH))
            await asyncio.to_thread(self._create_hls_venv)
            return HLS_VENV_PYTHON

    def _create_hls_venv(self) -> None:
        """Blocking: create venv and pip-install HLS dependencies inside it."""
        venv.create(str(HLS_VENV_PATH), with_pip=True, clear=True)
        logger.info("hls_venv_pip_install", packages=HLS_DEPENDENCIES)
        pip_cmd = [
            str(HLS_VENV_PYTHON),
            "-m", "pip", "install",
            "--timeout", "120",
            "--retries", "5",
            "--extra-index-url", "https://download.pytorch.org/whl/cpu",
            *HLS_DEPENDENCIES,
        ]
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            logger.info("hls_venv_pip_attempt", attempt=attempt, max=max_attempts)
            proc = subprocess.run(pip_cmd, capture_output=True, text=True)
            if proc.returncode == 0:
                HLS_VENV_MARKER.touch()
                logger.info("hls_venv_ready", path=str(HLS_VENV_PATH))
                return
            logger.warning(
                "hls_venv_pip_attempt_failed",
                attempt=attempt,
                stderr=proc.stderr[-500:],
            )
        logger.error("hls_venv_install_failed", stderr=proc.stderr)
        raise RuntimeError(
            f"Failed to install HLS venv dependencies after {max_attempts} attempts"
        )

    async def download(self, model_name: str, output_dir: str, **kwargs) -> Dict[str, Any]:
        model_type = (kwargs.get("type") or "").lower()
        if model_type not in SUPPORTED_TYPES:
            raise ValueError(f"Unsupported HLS model type: {model_type}")

        expected = Models_Supported.get(model_type)
        allowed = expected if isinstance(expected, list) else [expected]
        if model_name not in allowed:
            raise ValueError(
                f"Invalid model name '{model_name}' for type '{model_type}'. "
                f"Expected one of: {allowed}."
            )

        # Ensure (or reuse) the isolated HLS virtual environment.
        hls_python = await self._ensure_hls_venv()

        script_path = SUPPORTED_TYPES[model_type]
        models_dir = self._compute_output_dir(output_dir, model_type)
        args = self._build_args(model_type, kwargs, models_dir)
        logger.info(
            "hls_plugin_invocation",
            script=str(script_path),
            model_name=model_name,
            model_type=model_type,
            args=args,
        )

        result = await asyncio.to_thread(
            self._run_script,
            script=script_path,
            args=args,
            cwd=str(Path(output_dir).resolve()),
            python_executable=hls_python,
        )

        host_path = str(models_dir)
        if host_path.startswith("/opt/models/"):
            host_prefix = os.getenv("MODEL_PATH", "models")
            host_path = host_path.replace("/opt/models/", f"{host_prefix}/")

        return {
            "model_name": model_name,
            "source": "hls",
            "type": model_type,
            "download_path": host_path,
            "success": result == 0,
        }

    def _compute_output_dir(self, output_dir: str, model_type: str) -> Path:
        base_dir = Path(output_dir).resolve()
        models_dir = base_dir / model_type.replace("/", "_")
        models_dir.mkdir(parents=True, exist_ok=True)
        return models_dir

    def _build_args(
        self,
        model_type: str,
        kwargs: Dict[str, Any],
        models_dir: Path,
    ) -> list:
        args: list[str] = []
        if model_type in {"3d-pose", "rppg"}:
            args.extend([
                "--models-dir",
                str(models_dir),
            ])
        if model_type == "ai-ecg":
            args.append(str(models_dir))
        return args

    def _run_script(
        self,
        script: Path,
        args: list,
        cwd: str,
        python_executable: Path = None,
    ) -> int:
        """Run *script* inside a subprocess that has the HLS venv activated.

        For `.py` scripts the venv Python is used directly.
        For `.sh` scripts bash is used but PATH and VIRTUAL_ENV are set so
        that any `python` / `python3` calls inside the shell script resolve
        to the HLS venv interpreter.
        """
        script_path = str(script)

        # Build an environment that mirrors an activated venv.
        env = os.environ.copy()
        if python_executable is not None and python_executable.exists():
            venv_bin = str(python_executable.parent)
            env["VIRTUAL_ENV"] = str(python_executable.parent.parent)
            env["PATH"] = f"{venv_bin}:{env.get('PATH', '')}"
            env.pop("PYTHONHOME", None)

        if script_path.endswith(".sh"):
            cmd = ["bash", script_path, *args]
        else:
            py = str(python_executable) if python_executable else "python3"
            cmd = [py, script_path, *args]

        logger.info("hls_script_start", cmd=" ".join(cmd))
        proc = subprocess.run(cmd, cwd=cwd, env=env)
        if proc.returncode != 0:
            logger.error("hls_script_failed", cmd=" ".join(cmd), returncode=proc.returncode)
            raise RuntimeError(f"HLS script {script_path} failed with code {proc.returncode}")
        logger.info("hls_script_complete", cmd=" ".join(cmd))
        return proc.returncode
