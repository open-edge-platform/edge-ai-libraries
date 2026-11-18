# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Authorized local blob streaming and off-loop synchronous store access."""

import asyncio
import builtins
import io
import os
import threading
from dataclasses import replace
from types import SimpleNamespace

import anyio
import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import FileResponse

from api import retrieval
from assetlib.pool import SourceSyncStatus
from core.content import ContentBlock, file_uri, file_uri_path
from core.file_asset_library import FileAsset
from tests.test_mm_retrieval_integration import _client, _media_library


def _forbid_whole_blob_reads(monkeypatch, library):
    def forbidden(*args, **kwargs):
        pytest.fail("local responses must not load the entire blob through a byte reader")

    monkeypatch.setattr(FileAsset, "read_blob", forbidden)
    monkeypatch.setattr(library, "blob_reader", forbidden)


def _forbid_media_open(monkeypatch, *paths):
    blocked = {os.path.abspath(path) for path in paths}

    def guarded(original):
        def open_file(path, *args, **kwargs):
            if isinstance(path, (str, bytes, os.PathLike)):
                assert os.path.abspath(os.fsdecode(path)) not in blocked, (
                    "unauthorized media must be rejected before opening it"
                )
            return original(path, *args, **kwargs)

        return open_file

    monkeypatch.setattr(builtins, "open", guarded(builtins.open))
    monkeypatch.setattr(io, "open", guarded(io.open))

    def forbidden_response(*args, **kwargs):
        pytest.fail("an unauthorized URI must never become a file response")

    monkeypatch.setattr(retrieval, "FileResponse", forbidden_response)


@pytest.mark.parametrize(
    "reference", ["sibling", "origin-only", "text-block", "traversal", "symlink-alias", "removed"]
)
def test_unregistered_file_is_rejected_before_open(monkeypatch, tmp_path, reference):
    library, asset, registered_key, _ = _media_library(tmp_path)
    private = tmp_path / "private.jpg"
    private.write_bytes(b"private bytes")
    key = file_uri(str(private))
    if reference == "origin-only":
        asset.origin = key
    elif reference == "text-block":
        asset.content.blocks.append(ContentBlock("text", text="not binary", media_key=key))
    elif reference == "traversal":
        (tmp_path / "subdir").mkdir()
        key = f"file://{tmp_path}/subdir/../private.jpg"
    elif reference == "symlink-alias":
        alias = tmp_path / "alias.png"
        alias.symlink_to(file_uri_path(registered_key))
        key = file_uri(str(alias))
    elif reference == "removed":
        del library._assets[asset.asset_id]
        key = registered_key

    with _client(monkeypatch, library) as client:
        _forbid_media_open(
            monkeypatch, private, file_uri_path(registered_key), file_uri_path(key)
        )
        response = client.get("/v1/blob", params={"library": "library", "media_key": key})

    assert response.status_code == 404
    assert response.json() == {"detail": "blob not found"}


@pytest.mark.parametrize("source_id", ["other-content", "unattached", "missing", "filtered"])
def test_wrong_source_is_rejected_before_open(monkeypatch, tmp_path, source_id):
    library, _, key, _ = _media_library(tmp_path)
    library._sources["filtered"] = replace(
        library._sources["media"], source_id="filtered", configuration={"block_kinds": ["video"]}
    )
    library._asset_pools["pool"].source_statuses["filtered"] = SourceSyncStatus("filtered")

    with _client(monkeypatch, library) as client:
        _forbid_media_open(monkeypatch, file_uri_path(key))
        response = client.get("/v1/blob", params={
            "library": "library", "media_key": key, "source_id": source_id,
        })

    assert response.status_code == 404


@pytest.mark.parametrize("source_id", [None, "content", "media"])
def test_registered_file_streams_without_blob_reader(monkeypatch, tmp_path, source_id):
    library, _, key, data = _media_library(tmp_path)
    _forbid_whole_blob_reads(monkeypatch, library)
    params = {"library": "library", "media_key": key}
    if source_id is not None:
        params["source_id"] = source_id

    with _client(monkeypatch, library) as client:
        response = client.get("/v1/blob", params=params)

    assert response.status_code == 200
    assert response.content == data
    assert response.headers["content-type"] == "image/png"
    assert response.headers["content-length"] == str(len(data))
    assert response.headers["accept-ranges"] == "bytes"


@pytest.mark.parametrize("source_id", ["content", "media"])
@pytest.mark.parametrize("range_header, bounds", [
    ("bytes=0-7", (0, 8)),
    ("bytes=8-", (8, None)),
    ("bytes=-6", (-6, None)),
])
def test_registered_file_range(monkeypatch, tmp_path, source_id, range_header, bounds):
    library, _, key, data = _media_library(tmp_path)
    _forbid_whole_blob_reads(monkeypatch, library)

    with _client(monkeypatch, library) as client:
        response = client.get("/v1/blob", params={
            "library": "library", "media_key": key, "source_id": source_id,
        }, headers={"Range": range_header})

    start, stop, _ = slice(*bounds).indices(len(data))
    assert response.status_code == 206
    assert response.content == data[start:stop]
    assert response.headers["content-range"] == f"bytes {start}-{stop - 1}/{len(data)}"
    assert response.headers["content-length"] == str(stop - start)
    assert response.headers["content-type"] == "image/png"


def test_unsatisfiable_range(monkeypatch, tmp_path):
    library, _, key, data = _media_library(tmp_path)
    _forbid_whole_blob_reads(monkeypatch, library)

    with _client(monkeypatch, library) as client:
        response = client.get("/v1/blob", params={
            "library": "library", "media_key": key,
        }, headers={"Range": f"bytes={len(data)}-"})

    assert response.status_code == 416
    assert response.headers["content-range"] == f"bytes */{len(data)}"


def test_file_response_reads_bounded_chunks_and_keeps_jpeg_type(monkeypatch, tmp_path):
    library, asset, _, _ = _media_library(tmp_path)
    path = tmp_path / "large.jpg"
    data = b"\xff\xd8\xff" + b"x" * (FileResponse.chunk_size * 3 + 17)
    path.write_bytes(data)
    key = file_uri(str(path))
    asset.content.blocks[0].media_key = key
    _forbid_whole_blob_reads(monkeypatch, library)
    reads = []
    original_read = anyio.AsyncFile.read

    async def bounded_read(handle, size=-1):
        assert 0 < size <= FileResponse.chunk_size, "file reads must have a bounded size"
        reads.append(size)
        return await original_read(handle, size)

    monkeypatch.setattr(anyio.AsyncFile, "read", bounded_read)
    with _client(monkeypatch, library) as client:
        response = client.get("/v1/blob", params={"library": "library", "media_key": key})

    assert response.status_code == 200
    assert response.content == data
    assert response.headers["content-type"] == "image/jpeg"
    assert len(reads) >= 4, "the file must be streamed rather than preloaded"


@pytest.mark.parametrize("storage", ["file", "object-content", "object-projection"])
def test_concurrent_blob_io_keeps_event_loop_available(monkeypatch, tmp_path, storage):
    library, asset, file_key, file_data = _media_library(tmp_path)
    stream = asset.content
    app = FastAPI()
    app.include_router(retrieval.router)
    monkeypatch.setattr(retrieval, "registry", SimpleNamespace(require=lambda _: library))

    async def exercise():
        loop = asyncio.get_running_loop()
        loop_thread = threading.get_ident()
        started = asyncio.Queue()
        release = threading.Event()

        def blocking_io(result):
            assert threading.get_ident() != loop_thread, "synchronous blob I/O ran on the event loop"
            loop.call_soon_threadsafe(started.put_nowait, threading.get_ident())
            assert release.wait(5), "concurrent blob I/O was not released"
            return result

        if storage == "file":
            # Loading the record is part of reference/source authorization, not
            # file delivery; all concurrent lookups must run off the event loop.
            asset.cached = None
            asset.bind(lambda: blocking_io(stream))
            key, data, source_id = file_key, file_data, "media"
            _forbid_whole_blob_reads(monkeypatch, library)
        else:
            key, data = "blobs/image", b"GIF89aobject pixels"
            stream.blocks[0].media_key = key
            source_id = "content" if storage == "object-content" else "media"
            library.content_source = lambda source_id=None: library._sources[source_id or "content"]
            library._content_store = SimpleNamespace(
                get_blob=lambda source, media_key: blocking_io(data)
            )
            asset.bind_blobs(lambda media_key: blocking_io(data))

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            requests = [asyncio.create_task(client.get("/v1/blob", params={
                "library": "library", "media_key": key, "source_id": source_id,
            })) for _ in range(3)]
            try:
                # All three must reach blocking I/O before any may finish.
                workers = await asyncio.wait_for(
                    asyncio.gather(*(started.get() for _ in requests)), timeout=3
                )
                assert len(set(workers)) == len(requests)
                probe = await asyncio.wait_for(client.get("/v1/blob", params={
                    "library": "library", "media_key": "invalid/keyspace",
                }), timeout=2)
                assert probe.status_code == 400
                assert not any(request.done() for request in requests)
            finally:
                release.set()
                responses = await asyncio.gather(*requests)

        assert all(response.status_code == 200 for response in responses)
        assert all(response.content == data for response in responses)
        expected_type = "image/png" if storage == "file" else "image/gif"
        assert all(response.headers["content-type"] == expected_type for response in responses)

    asyncio.run(exercise())


@pytest.mark.parametrize("error", [KeyError, OSError, ValueError])
def test_offloaded_object_errors_still_return_not_found(monkeypatch, tmp_path, error):
    library, _, _, _ = _media_library(tmp_path)
    library.content_source = lambda source_id=None: library._sources["content"]

    def missing(source, key):
        raise error("missing")

    library._content_store = SimpleNamespace(get_blob=missing)
    with _client(monkeypatch, library) as client:
        response = client.get("/v1/blob", params={
            "library": "library", "media_key": "blobs/missing", "source_id": "content",
        })

    assert response.status_code == 404
    assert response.json() == {"detail": "blob not found"}