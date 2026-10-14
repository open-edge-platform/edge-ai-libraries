# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Frame transport: POSIX shared memory vs heap.

``MM_DATAPREP_VIDEO_FRAME_TRANSPORT`` selects how a decoded frame travels from
the decoder to the embed/detect workers. ``shm`` uses the fixed-capacity POSIX
shared-memory pool; ``heap`` carries the ndarray by reference through the
in-process queues (no pool, nothing in ``/dev/shm``, one fewer copy per frame).
Both must produce an identical downstream metadata/image contract so the rest of
the pipeline is transport-agnostic. These tests pin that contract down.
"""

from __future__ import annotations

import numpy as np

from src.core.embedding.decoder import FrameMetadata, convert_and_store_frame


class _FakeAvFrame:
    """Minimal stand-in for ``av.video.frame.VideoFrame``."""

    def __init__(self, arr: np.ndarray):
        self._arr = arr

    def to_ndarray(self, format: str = "rgb24") -> np.ndarray:  # noqa: A002 - mirror PyAV
        assert format == "rgb24"
        return self._arr


class _RecordingShmPool:
    """Records whether a block was ever acquired."""

    block_size = 1920 * 1080 * 3
    max_blocks = 4

    def __init__(self):
        self.acquired = 0
        import multiprocessing.shared_memory as _shm

        self._shm_mod = _shm
        self._blocks = []

    def acquire(self):
        self.acquired += 1
        blk = self._shm_mod.SharedMemory(create=True, size=self.block_size)
        self._blocks.append(blk)
        return blk.name

    def cleanup(self):
        for blk in self._blocks:
            blk.close()
            blk.unlink()


def _make_frame(h=4, w=6):
    # Distinct, reproducible pixel values so a copy-vs-reference check is exact.
    arr = np.arange(h * w * 3, dtype=np.uint8).reshape(h, w, 3)
    return arr, _FakeAvFrame(arr)


class TestConvertAndStoreFrameHeap:
    def test_heap_transport_carries_array_and_skips_pool(self):
        arr, frame = _make_frame()

        meta = convert_and_store_frame(0, 7, frame, shm_pool=None, ingest_epoch=123.0)

        assert isinstance(meta, FrameMetadata)
        assert meta.shm == ""
        assert meta.array is arr  # by reference, not copied
        assert meta.shape == str(arr.shape)
        assert meta.dtype == "uint8"
        assert meta.ingest_epoch == 123.0

    def test_heap_to_dict_keeps_array_reference(self):
        arr, frame = _make_frame()

        d = convert_and_store_frame(0, 1, frame, shm_pool=None).to_dict()

        # to_dict must NOT deep-copy the frame (that would defeat heap transport).
        assert d["array"] is arr
        assert d["shm"] == ""


class TestConvertAndStoreFrameShm:
    def test_shm_transport_acquires_a_block_and_has_no_array(self):
        arr, frame = _make_frame()
        pool = _RecordingShmPool()
        try:
            meta = convert_and_store_frame(0, 3, frame, shm_pool=pool)

            assert pool.acquired == 1
            assert meta.shm != ""
            assert meta.array is None

            # The block must hold an exact copy of the decoded frame.
            import multiprocessing.shared_memory as shm_mod

            shm = shm_mod.SharedMemory(name=meta.shm)
            try:
                stored = np.ndarray(arr.shape, dtype=arr.dtype, buffer=shm.buf)
                assert np.array_equal(stored, arr)
            finally:
                shm.close()
        finally:
            pool.cleanup()


class TestMapSharedFrameHeapIsNonDestructive:
    def test_heap_frame_can_be_mapped_twice(self):
        # With object detection enabled a full frame is mapped twice: once by the
        # detector (to_pil=False) and once by the embed worker (to_pil=True). The
        # heap array must survive the first map.
        from src.core.embedding.embedding_helper import _map_shared_frame

        arr, _ = _make_frame()
        d = {"array": arr, "shm": "", "shape": str(arr.shape), "dtype": "uint8"}

        shm1, got_arr, d_after = _map_shared_frame(d, to_pil=False)
        assert shm1 is None
        assert got_arr is arr
        assert d_after.get("array") is arr  # not popped

        shm2, pil, _ = _map_shared_frame(d, to_pil=True)
        assert shm2 is None
        assert np.array_equal(np.asarray(pil), arr)
