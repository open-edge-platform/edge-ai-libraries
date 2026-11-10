# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence, Tuple


@dataclass
class Figure:
    """A document figure; `bbox` is pixels (PDF) or a synthetic document-order box."""

    data: bytes = b""
    content_type: str = ""
    region_text: str = ""
    page: int = 0
    bbox: Tuple[float, ...] = ()
    label: str = "image"
    caption: Optional[str] = None
    caption_line: Optional[str] = None


def caption_for(
    figure: Figure,
    page_candidates: Sequence[Mapping[str, Any]],
    all_candidates: Sequence[Mapping[str, Any]],
) -> str:
    """The figure's preset caption or its nearest referencing text; `""` when nothing matches."""
    from core.fused import reference_text_for

    if figure.caption is not None:
        return figure.caption
    return reference_text_for(
        {"bbox": figure.bbox, "page": figure.page, "text": figure.region_text},
        page_candidates,
        all_candidates,
        no_text="",
    )
