# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Figure-to-text pairing over blocks `{"bbox": (x1, y1, x2, y2), "page": int, "text": str}` in page pixels."""

import re
from typing import Any, List, Mapping, Sequence

#: `Figure 3`, `Fig. 2a`, `Table 10`, `Equation 1`, `图1`, `表 2`, `公式 1`.
CAPTION_PATTERN = re.compile(
    r"(fig(?:ure)?|table|equation|formula|图|表|公式)"
    r"\s*[.．:]?\s*[(（]?\s*(\d+[a-z]?)(?![0-9A-Za-z])",
    re.IGNORECASE,
)
#: A caption marker followed by its number, anywhere in the line.
CAPTION_LIKE_PATTERN = re.compile(
    r"(?:fig(?:ure)?|table|equation|formula|图|表|公式)\s*[.．]?\s*\d+[a-z]?",
    re.IGNORECASE,
)

NO_RELEVANT_TEXTS = "(no relevant texts)"

#: Caption prefixes folded to one head; anything unlisted maps to `"fig"`.
_CAPTION_HEADS = {
    "table": "table",
    "表": "table",
    "equation": "eq",
    "formula": "eq",
    "公式": "eq",
}


def extract_caption_keys(text: str) -> List[str]:
    """Normalized caption keys in `text`, like `fig 3` / `table 2`."""
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


#: A period followed by whitespace and a capital; does not split `Fig. 1`.
_SENTENCE_BOUNDARY = re.compile(r"\.(?=\s+[A-Z])")


def _split_text_for_matching(text: str) -> List[str]:
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
    """Every sentence-level segment of `text` whose caption keys overlap `keys`."""
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
    """The prose that references `image`, joined nearest-first."""
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
        # No keyed match: fall back to every caption-like text on the page.
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
