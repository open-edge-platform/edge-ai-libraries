# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""A document's content, normalized: an ordered stream of typed blocks.

This is the engine's own schema, not any extractor's. Docling, unstructured, and
pdfplumber each describe a page differently; an extractor adapter maps into
`ContentBlock` so that swapping extractors cannot silently change what is
already persisted.

The stream is the **asset's** durable content, written once at ingest. Chunking
it into nodes is the **projection's** job and happens at materialize time, since
how big a chunk should be depends on the embedding model, not on the document.
That split is why a library with two vector sources at different chunk sizes
runs layout extraction once rather than twice.

A figure carries its caption as a field, not as a block of its own: there is one
node per figure, and the caption stays available for display and citation. What
is *around* the figure is not stored at all -- `surrounding_text` derives it from
the neighbouring blocks on demand, because it is already in the stream and a
second copy could only drift from the first.

A standalone media file is a stream of one binary block with no text. There is
no separate class for it and no modality flag on the asset: an asset is a file,
and the difference between a report and a recording is which `kind` its blocks
have.
"""

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

#: A `media_key` that starts with this names a local file rather than a blob in
#: the content store. A standalone media file *is* the asset, so its block points
#: at the file it came from instead of at a second copy of its bytes.
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

#: Blocks whose payload is bytes in the object store rather than text in the
#: record. A standalone media file is a stream of exactly one of these.
BINARY_KINDS = frozenset({IMAGE, AUDIO, VIDEO})

# `metadata.role`: where a block sits in the media-understanding scheme, and so
# how it is processed. Set by the system, never by a user; `kind` stays the
# content type. L0, the original media, carries no level prefix; derived levels do.
ROLE_IMAGE = "image"                  # a standalone image file
ROLE_DOC_IMAGE = "doc_image"          # a figure extracted from a document (PDF page)
ROLE_SHORT_VIDEO = "short_video"      # a clip short enough to embed whole
ROLE_LONG_VIDEO = "long_video"        # a longer recording; needs L1 segments first
ROLE_AUDIO = "audio"                  # a standalone audio file
ROLE_L1_SEGMENT = "l1_segment"        # a time range cut from a long video
ROLE_L2_CAPTION = "l2_caption"        # model-written description of media
ROLE_L2_TRANSCRIPT = "l2_transcript"  # speech recognized from audio (ASR)
ROLE_L3_WIKI = "l3_wiki"              # structured knowledge over a whole video
# Produced from another block rather than read from the file: only multimodal
# sources take these.
MM_DERIVED_ROLES = frozenset(
    {ROLE_L1_SEGMENT, ROLE_L2_CAPTION, ROLE_L2_TRANSCRIPT, ROLE_L3_WIKI}
)
MM_ROLES = frozenset(
    {ROLE_IMAGE, ROLE_DOC_IMAGE, ROLE_SHORT_VIDEO, ROLE_LONG_VIDEO, ROLE_AUDIO}
) | MM_DERIVED_ROLES
# The kind each role's blocks have, so a model's roles say which kinds it takes.
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


#: Block metadata a node may carry. Metadata is otherwise free-form, and a
#: projection writes what it carries into the vector store, so an unbounded
#: passthrough would let any ingest path invent columns in a shared collection.
#: Adding a key here is the deliberate act of making it part of the contract.
BLOCK_METADATA_KEYS = (
    "role",
    "duration_s",
    "t_start_ms",
    "t_end_ms",
    "revision",
)

# Layout is for citing and for ordering, never for embedding. A node that let
# these into its embedded text would have its vector polluted with coordinates,
# so a projection excludes them (`excluded_embed_metadata_keys`).
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
    """Up to `budget` characters drawn from `texts`, cut at a word boundary.

    `keep_tail` takes the *end* of the text (what came just before a figure);
    otherwise the beginning (what comes just after it).
    """
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
    # text | table | image | audio | video. How it is processed is `metadata.role`.
    kind: str = TEXT
    # text | table, including derived text (captions, transcripts).
    text: str = ""
    # image | audio | video (`BINARY_KINDS`): where the bytes live -- a blob key
    # for an extracted figure, a `file://` URI for a standalone media file --
    # and a caption, kept for display and embedded by text sources.
    media_key: str = ""
    caption: str = ""
    # The block this one is the caption of, when a layout model reports them
    # separately. Intra-document relations need no graph.
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
        # A media block's own metadata is how a projection tells a clip from a
        # still and a processed block from a placeholder, and how a retrieved
        # node is located back in the source. Whitelisted, because everything
        # here becomes a column in whichever collection the node lands in.
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
    """A document's blocks in reading order, plus its document-level metadata.

    `metadata` is what the loader stamped on the document -- `file_path`,
    `file_name`, `asset_id`. It has to survive, because chunk deletion addresses
    records by `file_path` / `file_name` and sync addresses them by `asset_id`.
    """

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
        """The text either side of the block at `position` in reading order.

        A figure's neighbours are what a document says *about* it, and they are
        usually the only searchable signal it has -- a caption may be "Figure 3"
        or missing altogether. Derived from the stream rather than stored on the
        block, because it is already in the stream: writing it down as well
        would duplicate the text and let the copy drift from the original.

        `budget` is a character count per side, trimmed at a word boundary so a
        window never ends mid-word.
        """
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

    # --- construction ---------------------------------------------------------

    @classmethod
    def from_documents(
        cls,
        documents: Sequence[Any],
        asset_id: str,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> "ContentStream":
        """One stream for one file, however many pieces the loader split it into.

        A loader hands back a document per page or per section; those are parts
        of one asset, not assets of their own, so they become blocks in reading
        order. This is the seam a real layout extractor replaces -- it produces
        the same stream, with figures and bounding boxes instead of one block per
        piece.
        """
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

    # --- persistence ----------------------------------------------------------

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
    """The block that carries the media itself, if this stream is a media file.

    A document's figures have a role too, but they do not make it a media file.
    """
    for block in stream.ordered():
        if role_of(block) in (ROLE_IMAGE, ROLE_SHORT_VIDEO, ROLE_LONG_VIDEO, ROLE_AUDIO):
            return block
    return None
