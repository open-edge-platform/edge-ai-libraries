import torch


def normalize_device(device_name: str) -> str:
    n = device_name.strip().lower()
    return "cuda" if n in {"gpu", "cuda"} and torch.cuda.is_available() else "cpu"


def resolve_dtype(dtype_name: str, *, cpu_fallback: bool = False) -> torch.dtype:
    dtype_map = {
        "float32": torch.float32, "fp32": torch.float32,
        "float16": torch.float16, "fp16": torch.float16,
        "bfloat16": torch.bfloat16, "bf16": torch.bfloat16,
    }
    dtype = dtype_map.get(dtype_name.lower(), torch.float32)
    if cpu_fallback and dtype in {torch.float16, torch.bfloat16}:
        return torch.float32
    return dtype


from components.tts.pytorch import parler_tts, qwen_tts, speecht5  # noqa: E402

IMPLEMENTATIONS = [qwen_tts, parler_tts, speecht5]

__all__ = ["IMPLEMENTATIONS", "normalize_device", "resolve_dtype"]