# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Figure-to-text pairing: what prose a figure should be searched through.

A figure's own pixels are not enough to find it -- a query matches the words
*about* it. So each visual block (image/table/figure) is paired with the body
text that references it, and that text becomes the block's caption, which the
projection embeds jointly with the crop. Ported from mmdir
`utils/fused_layout_helper.py`, trimmed to the pairing
itself -- rendering, OCR and I/O live in the extractor.

The rule, in order:
1. pull caption keys (`figure 3`, `table 2`) out of the figure's own OCR text;
2. find text blocks carrying the same key, same page first, then the whole doc;
3. failing that, fall back to caption-styled text on the figure's page;
4. keep each candidate's best key-matching line, rank candidates by spatial
    nearness, and join those lines; `"(no relevant texts)"` if nothing matches.

A block here is a light dict: `{"bbox": (x1, y1, x2, y2), "page": int,
"text": str}` -- coordinates in the page image's pixels, `text` its OCR.
"""

import re
from typing import Any, List, Mapping, Sequence

#: `Figure 3`, `Fig. 2a`, `Table 10`, `Equation 1`, `图1`, `表 2`, `公式 1`.
#: Equations are paired like figures because the layout path treats a formula as a
#: visual block (its glyphs are routinely garbled in the text layer), so a
#: reference such as `Equation 1` / `公式 (1)` has to find its crop the same way.
CAPTION_PATTERN = re.compile(
    r"(fig(?:ure)?|table|equation|formula|图|表|公式)"
    r"\s*[.．:]?\s*[(（]?\s*(\d+[a-z]?)(?![0-9A-Za-z])",
    re.IGNORECASE,
)
#: A line that *looks like* a caption: a figure/table/equation marker followed by
#: its number, matched anywhere in the line (the POC's relaxed, un-anchored form --
#: no `^` anchor, and a number is required). CJK prefixes are kept so a 中文 caption
#: still matches.
CAPTION_LIKE_PATTERN = re.compile(
    r"(?:fig(?:ure)?|table|equation|formula|图|表|公式)\s*[.．]?\s*\d+[a-z]?",
    re.IGNORECASE,
)

NO_RELEVANT_TEXTS = "(no relevant texts)"

#: The caption prefixes that mean the same thing, folded to one head so an image's
#: key matches a reference however either was spelled. Anything not listed (the
#: `fig`/`figure` family, plus the CJK 图) falls through to `"fig"`.
_CAPTION_HEADS = {
    "table": "table",
    "表": "table",
    "equation": "eq",
    "formula": "eq",
    "公式": "eq",
}


def extract_caption_keys(text: str) -> List[str]:
    """Normalized caption keys in `text`, like `fig 3` / `table 2`.

    Spacing is regularized first (`Figure3` and `figure 3` must yield the same
    key) so a match does not depend on how the OCR happened to break tokens.
    """
    raw = (text or "").strip()
    if not raw:
        return []
    normalized = re.sub(r"([a-z])([A-Z])", r"\1 \2", raw)
    normalized = re.sub(r"([A-Za-z])(\d)", r"\1 \2", normalized)
    normalized = re.sub(r"(\d)([A-Za-z])", r"\1 \2", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    keys: List[str] = []
    seen = set()
    for prefix, number in CAPTION_PATTERN.findall(normalized):
        head = _CAPTION_HEADS.get(prefix.lower(), "fig")
        key = f"{head} {number.lower()}"
        if key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def _bbox_center(bbox: Sequence[float]):
    x1, y1, x2, y2 = bbox
    return (x1 + x2) / 2.0, (y1 + y2) / 2.0


def _vertical_gap(image_bbox: Sequence[float], text_bbox: Sequence[float]) -> float:
    _, iy1, _, iy2 = image_bbox
    _, ty1, _, ty2 = text_bbox
    if ty1 >= iy2:
        return ty1 - iy2
    if iy1 >= ty2:
        return iy1 - ty2
    return 0.0


def score_text_candidate(image: Mapping[str, Any], text: Mapping[str, Any]) -> float:
    """Lower is nearer: vertical distance dominates, horizontal offset breaks ties."""
    image_bbox = image["bbox"]
    text_bbox = text["bbox"]
    icx, _ = _bbox_center(image_bbox)
    tcx, _ = _bbox_center(text_bbox)
    gap = _vertical_gap(image_bbox, text_bbox)
    width = max(1.0, image_bbox[2] - image_bbox[0])
    return gap * 2.0 + abs(icx - tcx) / width


def _dedup(candidates: List[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    """Drop repeats -- the same block can arrive via the page and global passes."""
    seen = set()
    unique = []
    for candidate in candidates:
        marker = (int(candidate.get("page", -1)), tuple(candidate.get("bbox", ())))
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(candidate)
    return unique


#: A sentence boundary for the POC's `line` mode: a period followed by whitespace
#: and a capital. It deliberately does NOT split `Fig. 1` / `Table 2.` (the period
#: there is followed by a digit or line end), so a caption marker stays on its line.
_SENTENCE_BOUNDARY = re.compile(r"\.(?=\s+[A-Z])")


def _split_text_for_matching(text: str) -> List[str]:
    """Split a layout's text into sentence-level segments, the POC's way.

    Each line is split on `_SENTENCE_BOUNDARY` (CJK `。` folded to `.` first), so a
    block of prose becomes the individual sentences a caption reference lives in,
    while `Fig. 3` stays intact. Mirrors `related_text_helper.split_text_for_matching`.
    """
    content = (text or "").strip()
    if not content:
        return []
    segments: List[str] = []
    for line in content.splitlines():
        line = line.replace("。", ".")
        for chunk in _SENTENCE_BOUNDARY.split(line):
            segment = chunk.strip()
            if segment:
                segments.append(segment)
    return segments


def _matching_lines(text: str, keys: set) -> List[str]:
    """Every sentence-level segment of `text` whose caption keys overlap `keys`.

    The POC's `line` mode (`collect_related_texts_line`): not the single best line,
    but all caption-key-bearing sentences, kept in order.
    """
    return [
        segment
        for segment in _split_text_for_matching(text)
        if keys & set(extract_caption_keys(segment))
    ]


def reference_text_for(
    image: Mapping[str, Any],
    page_texts: Sequence[Mapping[str, Any]],
    all_texts: Sequence[Mapping[str, Any]],
    no_text: str = NO_RELEVANT_TEXTS,
) -> str:
    """The prose that references `image`, joined nearest-first.

    `page_texts` are the text blocks on the figure's own page; `all_texts` is
    every text block in the document (a figure and its caption occasionally land
    on different pages).
    """
    keys = set(extract_caption_keys(image.get("text", "")))
    candidates: List[Mapping[str, Any]] = []
    keyed_match = False
    if keys:
        keyed = [
            text
            for text in list(page_texts) + list(all_texts)
            if keys & set(extract_caption_keys(text.get("text", "")))
        ]
        candidates = _dedup(keyed)
        keyed_match = bool(candidates)
    if not candidates:
        # Fallback for an image with no caption key, or a key that matched
        # nothing: keep every caption-like line on the page (not just the nearest
        # one); the distance sort below orders them.
        candidates = _dedup(
            [
                text
                for text in page_texts
                if CAPTION_LIKE_PATTERN.search(text.get("text", "") or "")
            ]
        )
    if not candidates:
        return no_text
    ordered = sorted(candidates, key=lambda text: score_text_candidate(image, text))
    if keyed_match:
        # POC `line` mode: collect every caption-key-bearing sentence across the
        # matched layouts (nearest first), de-duplicated in reading order.
        seen: set = set()
        selected: List[str] = []
        for text in ordered:
            for segment in _matching_lines(text.get("text", ""), keys):
                if segment not in seen:
                    seen.add(segment)
                    selected.append(segment)
    else:
        selected = [text.get("text", "") for text in ordered]
    joined = "\n".join(text for text in selected if text)
    return joined or no_text


__all__ = [
    "CAPTION_PATTERN",
    "CAPTION_LIKE_PATTERN",
    "NO_RELEVANT_TEXTS",
    "extract_caption_keys",
    "reference_text_for",
    "score_text_candidate",
]
