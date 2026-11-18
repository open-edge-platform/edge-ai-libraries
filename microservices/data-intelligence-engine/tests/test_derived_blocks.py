# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""What a derived block -- a caption, a transcript -- changes after it lands.

Two promises. Only the sources that take the new block re-materialize the
asset: a caption arriving must not re-encode the clip for an identical vector.
And a clip found by search is shown by its description once there is one,
without anything being re-embedded.
"""

from llama_index.core.schema import NodeWithScore, TextNode

from core.content import (
    ROLE_L2_CAPTION,
    ROLE_SHORT_VIDEO,
    TEXT,
    VIDEO,
    ContentBlock,
    ContentStream,
)
from core.file_asset_library import FileAsset

from tests.test_sources.fakes import FakeProjection, Library, add_source, ingest


def _synced_pool(*source_ids):
    library = Library()
    for source_id in source_ids:
        add_source(library, source_id)
    library.create_asset_pool(
        asset_pool_id="pool",
        name="pool",
        source_configurations=[{"source_id": source_id} for source_id in source_ids],
    )
    [asset_id] = ingest(library, "pool", "clip")
    library.sync_asset_pool("pool")
    return library, asset_id


def _adds(library, source_id):
    return library.asset_pools["pool"].projections[
        [p.source.source_id for p in library.asset_pools["pool"].projections].index(source_id)
    ].adds


def test_only_the_named_sources_re_materialize_the_asset():
    library, asset_id = _synced_pool("xclip", "gme")

    library.note_assets_changed([asset_id], {"gme"})
    library.sync_asset_pool("pool")

    assert _adds(library, "xclip") == [[asset_id]], "the clip is not re-encoded"
    assert _adds(library, "gme") == [[asset_id], [asset_id]]
    statuses = library.asset_pools["pool"].source_statuses
    assert all(status.status == "ready" for status in statuses.values())
    assert statuses["xclip"].indexed_revision == statuses["gme"].indexed_revision


def test_no_named_source_in_a_pool_leaves_it_alone():
    library, asset_id = _synced_pool("xclip")
    revision = library.asset_pools["pool"].revision

    library.note_assets_changed([asset_id], {"gme"})

    assert library.asset_pools["pool"].revision == revision


def test_without_source_ids_every_source_re_materializes_as_before():
    library, asset_id = _synced_pool("xclip", "gme")

    library.note_assets_changed([asset_id])
    library.sync_asset_pool("pool")

    assert _adds(library, "xclip") == [[asset_id], [asset_id]]


# --- shown by its description ---------------------------------------------------


class _Hits(FakeProjection):
    """Returns one node per held asset, written as a clip node is."""

    def retrieve(self, query):
        return [
            NodeWithScore(
                node=TextNode(
                    id_=f"{asset_id}:0",
                    text="holiday clip",
                    metadata={"asset_id": asset_id, "block_id": f"{asset_id}:0", "kind": VIDEO},
                ),
                score=0.3,
            )
            for asset_id in sorted(self.held)
        ]


class _HitsLibrary(Library):
    def build_projection(self, projection_id, name, source):
        return _Hits(source, self.store)


def _clip(asset_id, caption=None):
    blocks = [
        ContentBlock(
            f"{asset_id}:0", kind=VIDEO, media_key="file:///x.mp4",
            caption="holiday clip", metadata={"role": ROLE_SHORT_VIDEO},
        )
    ]
    if caption is not None:
        blocks.append(
            ContentBlock(
                f"{asset_id}:caption", kind=TEXT, text=caption,
                metadata={"role": ROLE_L2_CAPTION, "source_block_id": f"{asset_id}:0"},
            )
        )
    stream = ContentStream(asset_id=asset_id, blocks=blocks)
    return FileAsset(asset_id=asset_id, origin=f"file:///{asset_id}.mp4", cached=stream)


def _search(*assets):
    library = _HitsLibrary()
    add_source(library, "xclip")
    library.create_asset_pool(
        asset_pool_id="pool", name="pool", source_configurations=[{"source_id": "xclip"}]
    )
    library.register_assets(list(assets))
    library.add_assets_to_pool("pool", [asset.asset_id for asset in assets])
    library.sync_asset_pool("pool")
    return {
        scored.node.metadata["asset_id"]: scored.node.get_content()
        for scored in library.retrieve({"pool": object()})["pool"]
    }


def test_a_clip_with_a_description_is_shown_by_it():
    texts = _search(_clip("a", "A family walks along a beach."), _clip("b"))

    assert texts["a"] == "A family walks along a beach."
    assert texts["b"] == "holiday clip", "no description yet: the file name stays"
