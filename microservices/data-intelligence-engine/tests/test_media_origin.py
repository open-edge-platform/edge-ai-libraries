# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""A standalone media file is the asset, so its block points at the file itself.

Nothing is copied into the content store, so reading a clip back is opening its
path -- and deleting the asset takes the file with it, but only when the file is
one the engine holds.
"""

import os

import pytest

import config
from core import extractor
from core.file_asset_library import FileAsset, asset_id_for, file_origin

from .test_asset_identity import _library_with_pool


def _file(directory, name, data=b"\x89PNG\r\n"):
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(str(directory), name)
    with open(path, "wb") as handle:
        handle.write(data)
    return path


def _asset(path):
    origin = file_origin(path)
    stream = extractor.extract(path, asset_id_for(origin))
    asset = FileAsset(asset_id=stream.asset_id, origin=origin, cached=stream)

    def no_blobs(_key):
        raise AssertionError("a media file must not be read through the blob store")

    asset.bind_blobs(no_blobs)
    return asset, stream.blocks[0].media_key


# --- reading ------------------------------------------------------------------


def test_the_path_is_handed_straight_over_without_any_copy(tmp_path):
    path = _file(tmp_path, "clip.png")
    asset, key = _asset(path)

    with asset.media_path(key) as opened:
        assert opened == path


def test_bytes_come_from_the_file_when_the_key_is_a_file(tmp_path):
    path = _file(tmp_path, "clip.png", b"pixels")
    asset, key = _asset(path)

    assert asset.read_blob(key) == b"pixels"


def test_a_moved_origin_is_a_clear_error_not_a_stack_trace(tmp_path):
    path = _file(tmp_path, "clip.png")
    asset, key = _asset(path)
    os.unlink(path)

    with pytest.raises(ValueError, match="origin file is gone"):
        with asset.media_path(key):
            pass
    with pytest.raises(ValueError, match="origin file is gone"):
        asset.read_blob(key)


def test_a_blob_is_put_on_disk_for_the_decoder_and_removed_afterwards():
    asset = FileAsset(asset_id="a1")
    asset.bind_blobs(lambda key: b"figure-bytes" if key == "blobs/abc" else b"")

    with asset.media_path("blobs/abc", ".png") as opened:
        assert opened.endswith(".png")
        with open(opened, "rb") as handle:
            assert handle.read() == b"figure-bytes"

    assert not os.path.exists(opened)


def test_the_temporary_file_is_removed_even_when_the_decoder_fails():
    asset = FileAsset(asset_id="a1")
    asset.bind_blobs(lambda _key: b"x")
    seen = []

    with pytest.raises(RuntimeError):
        with asset.media_path("blobs/abc") as opened:
            seen.append(opened)
            raise RuntimeError("could not decode")

    assert not os.path.exists(seen[0])


# --- deleting -----------------------------------------------------------------


def _ingested(library, path):
    origin = file_origin(path)
    asset = library.create_asset(
        origin=origin, stream=extractor.extract(path, asset_id_for(origin))
    )
    library.register_assets([asset])
    return asset


def test_deleting_an_asset_removes_its_file_when_the_engine_holds_it(
    tmp_path, monkeypatch
):
    uploads = tmp_path / "uploads"
    monkeypatch.setattr(config, "UPLOAD_DIR", str(uploads))
    library, _, _ = _library_with_pool()
    path = _file(uploads, "clip.png")
    asset = _ingested(library, path)

    result = library.delete_assets([asset.asset_id])

    assert result["files_removed"] == [os.path.realpath(path)]
    assert result["files_kept"] == []
    assert not os.path.exists(path)


def test_a_file_outside_the_upload_directory_is_left_alone_and_reported(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(config, "UPLOAD_DIR", str(tmp_path / "uploads"))
    library, _, _ = _library_with_pool()
    path = _file(tmp_path / "my-own-data", "clip.png")
    asset = _ingested(library, path)

    result = library.delete_assets([asset.asset_id])

    assert result["removed"] == [asset.asset_id]
    assert result["files_removed"] == []
    assert result["files_kept"] == [os.path.realpath(path)]
    assert os.path.exists(path), "the caller's own file is not the engine's to delete"


def test_a_link_in_the_upload_directory_cannot_make_other_files_look_owned(
    tmp_path, monkeypatch
):
    uploads = tmp_path / "uploads"
    monkeypatch.setattr(config, "UPLOAD_DIR", str(uploads))
    library, _, _ = _library_with_pool()
    real = _file(tmp_path / "my-own-data", "clip.png")
    link = os.path.join(str(uploads), "clip.png")
    os.makedirs(str(uploads), exist_ok=True)
    os.symlink(real, link)
    asset = _ingested(library, link)

    result = library.delete_assets([asset.asset_id])

    assert result["files_removed"] == []
    assert result["files_kept"] == [os.path.realpath(real)]
    assert os.path.exists(real)


def test_deleting_an_asset_whose_file_is_already_gone_is_not_an_error(
    tmp_path, monkeypatch
):
    uploads = tmp_path / "uploads"
    monkeypatch.setattr(config, "UPLOAD_DIR", str(uploads))
    library, _, _ = _library_with_pool()
    path = _file(uploads, "clip.png")
    asset = _ingested(library, path)
    os.unlink(path)

    result = library.delete_assets([asset.asset_id])

    assert result["removed"] == [asset.asset_id]
    assert result["files_removed"] == []
