def normalize_device(device_name: str) -> str:
    n = device_name.strip().lower()
    if n in {"gpu", "cuda"}:
        return "GPU"
    if n == "npu":
        return "NPU"
    return "CPU"


from components.tts.openvino import parler_tts, qwen_tts, speecht5  # noqa: E402

IMPLEMENTATIONS = [qwen_tts, parler_tts, speecht5]

__all__ = ["IMPLEMENTATIONS", "normalize_device"]