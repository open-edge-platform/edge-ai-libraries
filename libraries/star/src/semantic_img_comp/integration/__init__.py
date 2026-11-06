from semantic_img_comp.integration.semantic_codec_bridge import DecodeResult
from semantic_img_comp.integration.semantic_codec_bridge import EncodeResult
from semantic_img_comp.integration.semantic_codec_bridge import SemanticCodecBridge

__all__ = [
    "SemanticCodecBridge",
    "EncodeResult",
    "DecodeResult",
    "SemanticImageManager",
]


def __getattr__(name: str):
    if name == "SemanticImageManager":
        from semantic_img_comp.integration.semantic_image_manager import SemanticImageManager

        return SemanticImageManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
