# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from functools import lru_cache


_SUPPORTED_DEVICES = {"CPU", "GPU", "NPU"}


@lru_cache(maxsize=16)
def resolve_tts_device(runtime: str, model_name: str, requested_device: str) -> str:
    normalized_runtime = str(runtime).strip().lower()
    normalized_model = str(model_name).strip().lower()
    device = str(requested_device).strip().upper()

    if device not in _SUPPORTED_DEVICES:
        raise ValueError(
            f"Unsupported TTS device '{requested_device}'. "
            f"Supported values: {', '.join(sorted(_SUPPORTED_DEVICES))}."
        )

    if "kokoro" in normalized_model:
        if device != "CPU":
            raise ValueError("The configured Kokoro model supports only CPU inference.")
        return device

    if normalized_runtime == "openvino":
        try:
            import openvino as ov
        except ImportError as exc:
            raise RuntimeError("OpenVINO runtime is not available.") from exc

        available_families = {
            str(item).strip().upper().split(".", maxsplit=1)[0]
            for item in ov.Core().available_devices
        }
        if device not in available_families:
            raise ValueError(
                f"Requested TTS device '{device}' is not visible in this runtime."
            )
        return device

    if normalized_runtime == "pytorch":
        if device == "NPU":
            raise ValueError("The PyTorch TTS runtime does not support NPU inference.")
        if device == "GPU":
            try:
                import torch
            except ImportError as exc:
                raise RuntimeError("PyTorch runtime is not available.") from exc
            if not torch.cuda.is_available():
                raise ValueError("Requested TTS device 'GPU' is not available to PyTorch.")
        return device

    raise ValueError(f"Unsupported TTS runtime: {runtime}")