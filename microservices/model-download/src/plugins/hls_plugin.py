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


class HlsPlugin(ModelDownloadPlugin):
    """Downloader plugin that orchestrates fixed HLS assets."""

    @property
    def plugin_name(self) -> str:
        return "hls"

    def can_handle(self, model_name: str, hub: str, **kwargs) -> bool:
        model_type = (kwargs.get("type") or "").lower()
        return hub.lower() == "hls" and model_type in SUPPORTED_TYPES

    async def download(self, model_name: str, output_dir: str, **kwargs) -> Dict[str, Any]:
        model_type = (kwargs.get("type") or "").lower()
        if model_type not in SUPPORTED_TYPES:
            raise ValueError(f"Unsupported HLS model type: {model_type}")

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

    def _run_script(self, script: Path, args: list, cwd: str) -> int:
        script_path = str(script)
        if script_path.endswith(".sh"):
            cmd = ["bash", script_path, *args]
        else:
            cmd = ["python3", script_path, *args]

        logger.info("hls_script_start", cmd=" ".join(cmd))
        proc = subprocess.run(cmd, cwd=cwd)
        if proc.returncode != 0:
            logger.error("hls_script_failed", cmd=" ".join(cmd), returncode=proc.returncode)
            raise RuntimeError(f"HLS script {script_path} failed with code {proc.returncode}")
        logger.info("hls_script_complete", cmd=" ".join(cmd))
        return proc.returncode
