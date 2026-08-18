# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
from types import SimpleNamespace

logger = logging.getLogger(__name__)

_SUPPORTED_ASR_PROVIDERS = {"openai", "openvino", "whispercpp"}
_SUPPORTED_ASR_DEVICES = {"CPU", "GPU", "NPU"}
_SUPPORTED_DIARIZATION_DEVICES = {"CPU", "GPU", "NPU"}
_ASR_PROVIDER_DEVICE_MATRIX = {
    "openai": {"CPU"},
    "openvino": {"CPU", "GPU", "NPU"},
    "whispercpp": {"CPU"},
}

# Models confirmed not to execute on NPU with OpenVINO 2026.1 on Intel Core Ultra
# (NPU architecture 3720 / "AI Boost"). The NPU driver returns
# ZE_RESULT_ERROR_UNINITIALIZED from pfnAppendGraphExecute during inference —
# the compiled graph cannot be executed at runtime regardless of compilation
# success. whisper-tiny/base/small/medium all pass NPU inference on this
# hardware; whisper-large (1.55B params, 32 decoder layers, ~5.9 GB FP32)
# exceeds a driver-level execution limit. CPU and GPU whisper-large both pass.
#
# If a future NPU driver update resolves the limitation, remove the affected
# entry here and rerun the validation matrix to confirm.
_OPENVINO_NPU_INFERENCE_UNSUPPORTED: frozenset = frozenset({
    "whisper-large",
})


def _is_npu_device(device: object) -> bool:
    return str(device or "").strip().upper().startswith("NPU")


def _normalize_asr_provider(cfg: SimpleNamespace) -> str:
    asr = getattr(getattr(cfg, "models", None), "asr", None)
    return str(getattr(asr, "provider", "")).strip().lower()


def _normalize_asr_device(cfg: SimpleNamespace) -> str:
    asr = getattr(getattr(cfg, "models", None), "asr", None)
    return str(getattr(asr, "device", "")).strip().upper()


def _normalize_asr_model_name(cfg: SimpleNamespace) -> str:
    asr = getattr(getattr(cfg, "models", None), "asr", None)
    return str(getattr(asr, "name", "") or "").strip().lower()


def _asr_uses_openvino_npu(cfg: SimpleNamespace) -> bool:
    if getattr(getattr(cfg, "models", None), "asr", None) is None:
        return False
    provider = _normalize_asr_provider(cfg)
    device = _normalize_asr_device(cfg)
    return provider == "openvino" and _is_npu_device(device)


def _sentiment_uses_openvino_npu(cfg: SimpleNamespace) -> bool:
    sentiment = getattr(cfg, "sentiment", None)
    if sentiment is None or not bool(getattr(sentiment, "enabled", False)):
        return False
    provider = str(getattr(sentiment, "provider", "")).strip().lower()
    device = getattr(sentiment, "device", "")
    return provider == "openvino" and _is_npu_device(device)


def _probe_openvino_npu_runtime() -> None:
    _probe_openvino_device_runtime("NPU")


def _probe_openvino_device_runtime(device: str) -> None:
    try:
        import openvino as ov
        from openvino import op
    except ImportError as exc:
        raise RuntimeError(
            "OpenVINO runtime is not installed in the environment. "
            "Install/verify OpenVINO runtime and Intel NPU user-space dependencies."
        ) from exc

    target = str(device).upper()
    core = ov.Core()

    # Compile a tiny identity graph to force initialization of the OpenVINO plugin stack.
    parameter = op.Parameter(ov.Type.f32, ov.Shape([1, 4]))
    result = op.Result(parameter.output(0))
    probe_model = ov.Model([result], [parameter])

    try:
        core.compile_model(probe_model, target)
    except Exception as exc:
        message = str(exc)
        if target == "NPU" and "libopenvino_intel_npu_compiler_loader.so" in message:
            raise RuntimeError(
                "Configured device is NPU but required OpenVINO NPU compiler library is missing: "
                "libopenvino_intel_npu_compiler_loader.so. Rebuild the Audio Analyzer image with Intel NPU "
                "user-space runtime/compiler dependencies and ensure the configured NPU device mapping is "
                "available inside the container."
            ) from exc

        if target == "NPU":
            raise RuntimeError(
                "Configured device is NPU, but OpenVINO NPU runtime/compiler initialization failed. "
                "Verify Intel NPU user-space runtime (linux-npu-driver userspace + libze1), the configured NPU "
                "device mapping, and host NPU driver compatibility. Original error: "
                f"{message}"
            ) from exc

        raise RuntimeError(
            f"Configured device is {target}, but OpenVINO runtime initialization failed for that device. "
            f"Original error: {message}"
        ) from exc


def validate_asr_runtime_configuration(cfg: SimpleNamespace) -> None:
    provider = _normalize_asr_provider(cfg)
    device = _normalize_asr_device(cfg)

    if provider not in _SUPPORTED_ASR_PROVIDERS:
        raise RuntimeError(
            "Invalid models.asr.provider value "
            f"'{provider}'. Supported values: {sorted(_SUPPORTED_ASR_PROVIDERS)}"
        )

    if device not in _SUPPORTED_ASR_DEVICES:
        raise RuntimeError(
            "Invalid models.asr.device value "
            f"'{device}'. Supported values: {sorted(_SUPPORTED_ASR_DEVICES)}"
        )

    supported_devices = _ASR_PROVIDER_DEVICE_MATRIX[provider]
    if device not in supported_devices:
        supported = ", ".join(sorted(supported_devices))
        raise RuntimeError(
            f"Invalid ASR provider/device combination: provider={provider}, device={device}. "
            f"Provider '{provider}' supports only: {supported}"
        )

    if provider != "openvino":
        return

    try:
        import openvino as ov
    except ImportError as exc:
        raise RuntimeError(
            "OpenVINO runtime is required when models.asr.provider=openvino, but it is not installed."
        ) from exc

    available_devices = [str(item).upper() for item in ov.Core().available_devices]
    if device not in available_devices:
        guidance = (
            "For GPU, ensure /dev/dri is exposed to the container and Intel/OpenVINO host GPU runtime is installed."
            if device == "GPU"
            else "For NPU, ensure ACCEL_MOUNT_PATH points to your host NPU device node and is mapped into "
            "/dev/accel/accel0 in the container, and ZE_ENABLE_ALT_DRIVERS=libze_intel_npu.so is set."
        )
        raise RuntimeError(
            f"Configured OpenVINO ASR device '{device}' is not visible in this runtime. "
            f"OpenVINO available_devices={available_devices}. {guidance}"
        )

    if device == "NPU":
        model_name = _normalize_asr_model_name(cfg)
        if model_name in _OPENVINO_NPU_INFERENCE_UNSUPPORTED:
            raise RuntimeError(
                f"Model '{model_name}' with device=NPU is not supported on this NPU hardware "
                "(confirmed ZE_RESULT_ERROR_UNINITIALIZED at pfnAppendGraphExecute on Intel Core "
                "Ultra NPU architecture 3720 with OpenVINO 2026.1). "
                "The NPU driver cannot execute the compiled graph at runtime — this is a "
                "driver/firmware limitation, not an Audio Analyzer bug. "
                f"Use device=CPU or device=GPU for {model_name}. "
                "See the troubleshooting guide for details and driver update guidance."
            )

    _probe_openvino_device_runtime(device)


def validate_openvino_npu_runtime(config: SimpleNamespace) -> None:
    if not (_asr_uses_openvino_npu(config) or _sentiment_uses_openvino_npu(config)):
        return

    logger.info("NPU device requested by configuration; validating OpenVINO NPU runtime availability")
    _probe_openvino_npu_runtime()


def resolve_diarization_torch_device(config_device: str) -> str:
    """Map the configured diarization device to the internal device string.

    For CPU: returns ``"CPU"`` (PyTorch CPU path, existing ``PyannoteDiarizer``).
    For GPU: returns ``"GPU"`` (OpenVINO GPU path, ``OVBackedPyannoteDiarizer``).
    For NPU: returns ``"NPU"`` (OpenVINO NPU path, ``OVBackedPyannoteDiarizer``).

    Raises ``RuntimeError`` for unrecognised values so the service fails fast.

    Note: the GPU and NPU paths route diarization inference through OpenVINO,
    not through PyTorch XPU/CUDA.  PyTorch is used only for the embedding model
    which always runs on CPU.  Actual device availability is validated by
    ``validate_diarization_device_configuration`` at startup.
    """
    upper = str(config_device).strip().upper()
    if upper in ("CPU", "GPU", "NPU"):
        return upper
    raise RuntimeError(
        f"Invalid diarization device '{config_device}'. "
        f"Supported values: {sorted(_SUPPORTED_DIARIZATION_DEVICES)}"
    )


def validate_diarization_device_configuration(cfg: SimpleNamespace) -> None:
    """Validate the diarization device at startup.

    * ``CPU``: always supported (PyTorch CPU path).
    * ``GPU``: validated via OpenVINO device enumeration (OV GPU path).
    * ``NPU``: validated via OpenVINO device enumeration (OV NPU path).

    Raises ``RuntimeError`` if the requested device is not available so that the
    service fails fast rather than silently disabling diarization at request time.
    """
    asr_cfg = getattr(getattr(cfg, "models", None), "asr", None)
    if not getattr(asr_cfg, "diarization", False):
        return  # diarization disabled — no validation needed

    diar_cfg = getattr(getattr(cfg, "models", None), "diarization", None)
    raw_device = str(getattr(diar_cfg, "device", "CPU") if diar_cfg else "CPU")
    device = resolve_diarization_torch_device(raw_device)  # validates device name

    if device == "CPU":
        return  # CPU is always available

    # GPU and NPU are served via OpenVINO.  Probe OV device availability.
    try:
        import openvino as ov
    except ImportError as exc:
        raise RuntimeError(
            "OpenVINO is required for diarization device=GPU/NPU but is not installed."
        ) from exc

    available = [str(d).upper() for d in ov.Core().available_devices]
    if device not in available:
        guidance = (
            "For GPU: ensure /dev/dri is exposed to the container and "
            "the host Intel GPU driver stack is installed."
            if device == "GPU"
            else "For NPU: set ACCEL_MOUNT_PATH to your host NPU device node and restart. "
            "Verify Compose maps it to /dev/accel/accel0 and ZE_ENABLE_ALT_DRIVERS=libze_intel_npu.so is set in the container."
        )
        raise RuntimeError(
            f"Diarization device={device} is configured but the OpenVINO device "
            f"'{device}' is not visible in this runtime. "
            f"OpenVINO available_devices={available}. {guidance}"
        )
    logger.info(
        "[DIARIZATION] OpenVINO device '%s' confirmed available for diarization",
        device,
    )


def validate_runtime_configuration(config: SimpleNamespace) -> None:
    validate_asr_runtime_configuration(config)
    validate_diarization_device_configuration(config)

    if _sentiment_uses_openvino_npu(config) and not _asr_uses_openvino_npu(config):
        logger.info("NPU device requested by sentiment configuration; validating OpenVINO NPU runtime availability")
        _probe_openvino_npu_runtime()
