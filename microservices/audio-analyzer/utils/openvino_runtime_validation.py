# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
from types import SimpleNamespace

logger = logging.getLogger(__name__)


def _is_npu_device(device: object) -> bool:
    return str(device or "").strip().upper().startswith("NPU")


def _asr_uses_openvino_npu(cfg: SimpleNamespace) -> bool:
    asr = getattr(getattr(cfg, "models", None), "asr", None)
    if asr is None:
        return False
    provider = str(getattr(asr, "provider", "")).strip().lower()
    device = getattr(asr, "device", "")
    return provider == "openvino" and _is_npu_device(device)


def _sentiment_uses_openvino_npu(cfg: SimpleNamespace) -> bool:
    sentiment = getattr(cfg, "sentiment", None)
    if sentiment is None or not bool(getattr(sentiment, "enabled", False)):
        return False
    provider = str(getattr(sentiment, "provider", "")).strip().lower()
    device = getattr(sentiment, "device", "")
    return provider == "openvino" and _is_npu_device(device)


def _probe_openvino_npu_runtime() -> None:
    try:
        import openvino as ov
        from openvino import op
    except ImportError as exc:
        raise RuntimeError(
            "OpenVINO runtime is not installed in the environment. "
            "Install/verify OpenVINO runtime and Intel NPU user-space dependencies."
        ) from exc

    core = ov.Core()
    available_devices = [str(device).upper() for device in core.available_devices]
    if "NPU" not in available_devices:
        raise RuntimeError(
            "OpenVINO does not report an NPU device. Ensure the container has Intel NPU user-space runtime "
            "(linux-npu-driver userspace + libze1), that the configured NPU device mapping is passed through "
            "to the container (for Docker Compose, check ACCEL_MOUNT_PATH), and that the host Intel NPU driver "
            "is loaded."
        )

    # Compile a tiny identity graph to force initialization of the NPU compiler stack.
    parameter = op.Parameter(ov.Type.f32, ov.Shape([1, 4]))
    result = op.Result(parameter.output(0))
    probe_model = ov.Model([result], [parameter])

    try:
        core.compile_model(probe_model, "NPU")
    except Exception as exc:
        message = str(exc)
        if "libopenvino_intel_npu_compiler_loader.so" in message:
            raise RuntimeError(
                "Configured device is NPU but required OpenVINO NPU compiler library is missing: "
                "libopenvino_intel_npu_compiler_loader.so. Rebuild the Audio Analyzer image with Intel NPU "
                "user-space runtime/compiler dependencies and ensure the configured NPU device mapping is "
                "available inside the container."
            ) from exc

        raise RuntimeError(
            "Configured device is NPU, but OpenVINO NPU runtime/compiler initialization failed. "
            "Verify Intel NPU user-space runtime (linux-npu-driver userspace + libze1), the configured NPU "
            "device mapping, and host NPU driver compatibility. Original error: "
            f"{message}"
        ) from exc


def validate_openvino_npu_runtime(config: SimpleNamespace) -> None:
    if not (_asr_uses_openvino_npu(config) or _sentiment_uses_openvino_npu(config)):
        return

    logger.info("NPU device requested by configuration; validating OpenVINO NPU runtime availability")
    _probe_openvino_npu_runtime()
