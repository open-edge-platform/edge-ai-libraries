# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import mimetypes
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

#: A `media_key` with this prefix names a local file rather than a content-store blob.
FILE_SCHEME = "file://"


def file_uri(path: str) -> str:
    """The `file://` URI for `path`, absolute."""
    return f"{FILE_SCHEME}{os.path.abspath(path)}"


def is_file_uri(key: str) -> bool:
    return bool(key) and key.startswith(FILE_SCHEME)


def file_uri_path(uri: str) -> str:
    """The filesystem path inside a `file://` URI."""
    return uri[len(FILE_SCHEME):]


TEXT = "text"
IMAGE = "image"
TABLE = "table"
AUDIO = "audio"
VIDEO = "video"

#: Blocks whose payload is bytes in the object store rather than text in the record.
BINARY_KINDS = frozenset({IMAGE, AUDIO, VIDEO})

#: The family of a file that is not media: what a text source takes.
DOCUMENT = "document"


def asset_family(selector: str) -> str:
    """The family (image/video/audio/document) of a family name, extension or MIME type."""
    selector = selector.strip().lower().lstrip('.')
    if selector in BINARY_KINDS:
        return selector
    mime = selector if '/' in selector else mimetypes.guess_type(f"asset.{selector}")[0]
    family = (mime or '').split('/')[0]
    return family if family in BINARY_KINDS else DOCUMENT

# `metadata.role`: how a block is processed, set by the system; `kind` stays the content type.
ROLE_IMAGE = "image"                  # a standalone image file
ROLE_DOC_IMAGE = "doc_image"          # a figure extracted from a document (PDF page)
ROLE_SHORT_VIDEO = "short_video"      # a clip short enough to embed whole
ROLE_LONG_VIDEO = "long_video"        # a longer recording; needs L1 segments first
ROLE_AUDIO = "audio"                  # a standalone audio file
ROLE_L1_SEGMENT = "l1_segment"        # a time range cut from a long video
ROLE_L2_CAPTION = "l2_caption"        # model-written description of media
ROLE_L2_TRANSCRIPT = "l2_transcript"  # speech recognized from audio (ASR)
ROLE_L3_WIKI = "l3_wiki"              # structured knowledge over a whole video
# Produced from another block; only multimodal sources take these.
MM_DERIVED_ROLES = frozenset(
    {ROLE_L1_SEGMENT, ROLE_L2_CAPTION, ROLE_L2_TRANSCRIPT, ROLE_L3_WIKI}
)
MM_ROLES = frozenset(
    {ROLE_IMAGE, ROLE_DOC_IMAGE, ROLE_SHORT_VIDEO, ROLE_LONG_VIDEO, ROLE_AUDIO}
) | MM_DERIVED_ROLES
# The block kind for each role.
ROLE_to_KIND = {
    ROLE_IMAGE: IMAGE,
    ROLE_DOC_IMAGE: IMAGE,
    ROLE_SHORT_VIDEO: VIDEO,
    ROLE_LONG_VIDEO: VIDEO,
    ROLE_L1_SEGMENT: VIDEO,
    ROLE_AUDIO: AUDIO,
    ROLE_L2_CAPTION: TEXT,
    ROLE_L2_TRANSCRIPT: TEXT,
    ROLE_L3_WIKI: TEXT,
}


def role_of(block: "ContentBlock") -> str:
    """A block's role, or `""` for one that has none (a document's prose)."""
    return str((block.metadata or {}).get("role") or "")


#: Whitelisted block metadata a node may carry; each key becomes a vector-store column.
BLOCK_METADATA_KEYS = (
    "role",
    "duration_s",
    "t_start_ms",
    "t_end_ms",
    "revision",
)

# Loader metadata that describes one page rather than the document it came from.
_PER_PAGE_KEYS = frozenset({"page_label", "page", "page_number"})


def _content_of(document) -> str:
    if hasattr(document, "get_content"):
        return document.get_content()
    return str(getattr(document, "text", ""))


def _page_of(metadata: Mapping[str, Any], fallback: int) -> int:
    for key in ("page_label", "page", "page_number"):
        value = metadata.get(key)
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return fallback


def _window(texts, budget: int, keep_tail: bool) -> str:
    """Up to `budget` characters from `texts`, cut at a word boundary; `keep_tail` keeps the end."""
    collected: List[str] = []
    remaining = budget
    for text in texts:
        if remaining <= 0:
            break
        text = text.strip()
        if not text:
            continue
        if len(text) > remaining:
            text = (
                text[-remaining:].split(" ", 1)[-1]
                if keep_tail
                else text[:remaining].rsplit(" ", 1)[0]
            )
        remaining -= len(text)
        collected.append(text)
    if keep_tail:
        collected.reverse()
    return "\n\n".join(collected).strip()


LAYOUT_METADATA_KEYS = (
    "block_id",
    "kind",
    "page",
    "bbox",
    "reading_order",
    "media_key",
    "caption_for",
    "asset_id",
    *BLOCK_METADATA_KEYS,
)


@dataclass
class ContentBlock:
    """One piece of an asset: text, a table, or media (image, audio, video)."""

    block_id: str
    # text | table | image | audio | video
    kind: str = TEXT
    # text | table, including derived text (captions, transcripts).
    text: str = ""
    # Binary kinds: a blob key, or a `file://` URI for a standalone media file.
    media_key: str = ""
    caption: str = ""
    # The block this one is the caption of, when a layout model reports them separately.
    caption_for: str = ""
    page: int = 0
    bbox: Tuple[float, ...] = ()
    reading_order: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def layout_metadata(self) -> Dict[str, Any]:
        """What a node derived from this block should carry for citation."""
        layout = {
            "block_id": self.block_id,
            "kind": self.kind,
            "page": self.page,
            "reading_order": self.reading_order,
        }
        if self.bbox:
            layout["bbox"] = list(self.bbox)
        if self.media_key:
            layout["media_key"] = self.media_key
        if self.caption_for:
            layout["caption_for"] = self.caption_for
        for key in BLOCK_METADATA_KEYS:
            value = self.metadata.get(key)
            if value not in (None, ""):
                layout[key] = value
        return layout

    def to_record(self) -> dict:
        return {
            "block_id": self.block_id,
            "kind": self.kind,
            "text": self.text,
            "media_key": self.media_key,
            "caption": self.caption,
            "caption_for": self.caption_for,
            "page": self.page,
            "bbox": list(self.bbox),
            "reading_order": self.reading_order,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "ContentBlock":
        return cls(
            block_id=str(record["block_id"]),
            kind=str(record.get("kind") or TEXT),
            text=str(record.get("text") or ""),
            media_key=str(record.get("media_key") or ""),
            caption=str(record.get("caption") or ""),
            caption_for=str(record.get("caption_for") or ""),
            page=int(record.get("page") or 0),
            bbox=tuple(record.get("bbox") or ()),
            reading_order=int(record.get("reading_order") or 0),
            metadata=dict(record.get("metadata") or {}),
        )


@dataclass
class ContentStream:
    """A document's blocks in reading order, plus document-level metadata (`file_path`, `file_name`, `asset_id`)."""

    asset_id: str
    blocks: List[ContentBlock] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def ordered(self) -> List[ContentBlock]:
        return sorted(self.blocks, key=lambda block: (block.reading_order, block.page))

    def blocks_of(self, *kinds: str) -> List[ContentBlock]:
        wanted = set(kinds)
        return [block for block in self.ordered() if block.kind in wanted]

    def text(self) -> str:
        """The textual blocks joined in reading order."""
        return "\n\n".join(
            block.text for block in self.blocks_of(TEXT, TABLE) if block.text
        )

    def media_keys(self) -> List[str]:
        return [
            block.media_key
            for block in self.ordered()
            if block.kind in BINARY_KINDS and block.media_key
        ]

    def surrounding_text(self, position: int, budget: int = 400) -> str:
        """The text either side of the block at `position`; `budget` is characters per side."""
        blocks = self.ordered()
        before = _window(
            (block.text for block in reversed(blocks[:position]) if block.text),
            budget,
            keep_tail=True,
        )
        after = _window(
            (block.text for block in blocks[position + 1:] if block.text),
            budget,
            keep_tail=False,
        )
        return "\n\n".join(part for part in (before, after) if part)

    @classmethod
    def from_documents(
        cls,
        documents: Sequence[Any],
        asset_id: str,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> "ContentStream":
        """One stream for one file: each loader document (page/section) becomes a text block."""
        blocks = []
        for order, document in enumerate(documents):
            document_metadata = dict(getattr(document, "metadata", None) or {})
            blocks.append(
                ContentBlock(
                    block_id=f"{asset_id}:{order}",
                    kind=TEXT,
                    text=_content_of(document),
                    page=_page_of(document_metadata, order),
                    reading_order=order,
                )
            )
        first = dict(getattr(documents[0], "metadata", None) or {}) if documents else {}
        # Document-level metadata, minus what belongs to one page of it.
        merged = {
            key: value for key, value in first.items() if key not in _PER_PAGE_KEYS
        }
        merged.update(metadata or {})
        merged["asset_id"] = asset_id
        return cls(asset_id=asset_id, blocks=blocks, metadata=merged)

    @classmethod
    def from_document(
        cls, document, asset_id: Optional[str] = None
    ) -> "ContentStream":
        """A stream for a single document, keyed by its own id unless told otherwise."""
        asset_id = str(
            asset_id
            or getattr(document, "doc_id", None)
            or getattr(document, "node_id", None)
            or id(document)
        )
        return cls.from_documents([document], asset_id)

    def to_record(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "metadata": dict(self.metadata),
            "blocks": [block.to_record() for block in self.blocks],
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "ContentStream":
        return cls(
            asset_id=str(record["asset_id"]),
            blocks=[
                ContentBlock.from_record(block)
                for block in record.get("blocks") or ()
            ],
            metadata=dict(record.get("metadata") or {}),
        )

    @classmethod
    def from_document_record(cls, record: Mapping[str, Any]) -> "ContentStream":
        """A stream out of a persisted llama-index document, for old workspaces."""
        metadata = dict(record.get("metadata") or {})
        asset_id = str(metadata.get("asset_id") or record.get("id_") or "")
        return cls(
            asset_id=asset_id,
            blocks=[
                ContentBlock(
                    block_id=f"{asset_id}:0",
                    kind=TEXT,
                    text=str(record.get("text") or ""),
                    reading_order=0,
                )
            ],
            metadata=metadata,
        )


def media_block(stream: ContentStream) -> Optional[ContentBlock]:
    """The block carrying the media itself, if this stream is a standalone media file."""
    for block in stream.ordered():
        if role_of(block) in (ROLE_IMAGE, ROLE_SHORT_VIDEO, ROLE_LONG_VIDEO, ROLE_AUDIO):
            return block
    return None
