# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""The slow path's shared core: a located figure, and the prose it is paired with.

A figure is *found* differently per format -- a PDF detects a region in a rendered
page, a docx resolves a drawing relationship, an HTML reads an `<img>` -- but once
found, *captioning* it is the same everywhere: find the prose that references it
(`fused.reference_text_for`), scoring candidate text blocks by distance. This
module is that shared step, so the PDF path (`extractor.digital_visual_blocks`)
and the structured-document path (`structured`) caption figures through one
function rather than two copies of the rule.

"Distance" is pixels for a PDF (real boxes from the text layer) and document order
for a structured file (a synthetic one-unit box per block position), but
`reference_text_for` only ever reads `bbox`, so the same scoring serves both -- a
caller supplies whichever coordinates it has.
"""

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence, Tuple


@dataclass
class Figure:
    """A picture found in a document, before it is paired with its prose.

    `bbox` is real pixels (PDF) or a synthetic order-box (a structured file, which
    has no coordinates). `region_text` is any text the figure carries itself (a PDF
    OCRs its crop; a structured figure rarely has any), from which caption keys
    like `Figure 3` are read. `caption`, when already known (an HTML `alt` or
    `<figcaption>`), is used verbatim and skips pairing; left `None`, it is found
    from the surrounding text. `caption_line` is the caption paragraph a format
    located from its own geometry (a pptx slide's shape boxes), standing in for
    the reading-order neighbour search that layout cannot be trusted to.
    """

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
    """The prose that captions `figure`: its preset caption, or the paired reference.

    `page_candidates` are the text blocks on the figure's own page (scored for
    nearness); `all_candidates` is every text block in the document (so a
    `Figure 3` reference on another page is still found). Returns `""`, never the
    `reference_text_for` sentinel, when nothing matches -- a placeholder string
    would pollute the vector the caption is embedded into.
    """
    from core.fused import reference_text_for

    if figure.caption is not None:
        return figure.caption
    return reference_text_for(
        {"bbox": figure.bbox, "page": figure.page, "text": figure.region_text},
        page_candidates,
        all_candidates,
        no_text="",
    )
