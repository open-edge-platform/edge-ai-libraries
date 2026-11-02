# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""The engine's file asset libraries and projection components.

`file_asset_library.py` holds `FileAssetLibrary`, the RAG specialization
of `assetlib.AssetLibrary`: it inherits generic asset/source/pool machinery and
adds the asset definition, projection choice, and file and chunk vocabulary.
`manager.py` keeps the set of libraries by name and id.

**An asset is a file** -- a report, a spreadsheet, a recording -- and one path
runs the length of all of them:

    extractor.py  a file        -> a ContentStream of typed blocks
    content.py    the blocks    -> the asset's durable, extractor-neutral form
    indexer.py    the blocks    -> nodes for a vector source
    knowledge.py  the blocks    -> vertices and edges for a graph source

Each stage reads the one before it and nothing else, so a new file format is a
new extractor and a new backend is a new projection; neither disturbs the other.

The components are ported from EdgeCraftRAG's edgecraftrag/components. Assetlib
owns library behaviour, core owns the RAG specialization and the projections,
and databasehub adapters are the whole boundary to each database backend.
Retrieval uses a custom BM25 retriever and pool-level QueryFusionRetriever:
available vector, graph, and BM25 arms share one chunk-id-based RRF implementation,
plus a pluggable embedding/reranker factory.

Model-specific runtimes, backend adapters, model discovery, and shared model
caches live in the sibling `inference` package.
"""
