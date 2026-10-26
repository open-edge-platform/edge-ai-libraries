# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for :class:`SharedMemoryPool` descriptor usage.

The ingestion pipeline builds two pools per run (video frames, plus a
detected-crop pool sized at twice the frame pool). Holding an open handle per
block costs two descriptors each, so at the default sizes the pools pinned
roughly 3000 descriptors and could not be allocated at all under a default
1024-descriptor limit.
"""

import os
from multiprocessing import shared_memory

import numpy as np
import pytest

from src.core.embedding.decoder import SharedMemoryPool

pytestmark = pytest.mark.skipif(
    not os.path.isdir("/proc/self/fd"), reason="requires /proc"
)


def _open_fd_count() -> int:
    return len(os.listdir(f"/proc/{os.getpid()}/fd"))


def test_pool_does_not_retain_a_descriptor_per_block():
    """Allocating many blocks must not scale open descriptors."""
    baseline = _open_fd_count()
    pool = SharedMemoryPool(max_blocks=256, block_size=4096)
    try:
        growth = _open_fd_count() - baseline
        assert growth < 16, (
            f"pool retained {growth} descriptors for 256 blocks; "
            "descriptors must be released after allocation"
        )
        assert pool.total_blocks() == 256
        assert pool.free_blocks() == 256
    finally:
        pool.shutdown()


def test_two_default_sized_pools_fit_within_a_1024_descriptor_budget():
    """Frame pool plus the twice-as-large crop pool must stay affordable."""
    baseline = _open_fd_count()
    frame_pool = SharedMemoryPool(max_blocks=512, block_size=4096)
    crop_pool = SharedMemoryPool(max_blocks=1024, block_size=2048)
    try:
        assert _open_fd_count() - baseline < 64
    finally:
        frame_pool.shutdown()
        crop_pool.shutdown()


def test_block_is_usable_after_pool_releases_descriptor():
    """Segments must stay attachable by name once the fd is closed."""
    pool = SharedMemoryPool(max_blocks=4, block_size=4096)
    try:
        name = pool.acquire()
        payload = np.arange(8, dtype=np.uint8)

        writer = shared_memory.SharedMemory(name=name)
        try:
            np.ndarray(payload.shape, dtype=payload.dtype, buffer=writer.buf)[:] = payload
        finally:
            writer.close()

        reader = shared_memory.SharedMemory(name=name)
        try:
            roundtrip = np.ndarray(
                payload.shape, dtype=payload.dtype, buffer=reader.buf
            ).copy()
        finally:
            reader.close()

        np.testing.assert_array_equal(roundtrip, payload)

        pool.release(name)
        assert pool.used_blocks() == 0
    finally:
        pool.shutdown()


def test_shutdown_unlinks_every_segment():
    """No segment may survive shutdown, otherwise /dev/shm leaks."""
    pool = SharedMemoryPool(max_blocks=8, block_size=4096)
    names = [pool.acquire() for _ in range(8)]
    for name in names:
        pool.release(name)
    pool.shutdown()

    for name in names:
        with pytest.raises(FileNotFoundError):
            shared_memory.SharedMemory(name=name)


def test_shutdown_is_idempotent():
    """Double shutdown must not raise, so cleanup paths can be defensive."""
    pool = SharedMemoryPool(max_blocks=4, block_size=4096)
    pool.shutdown()
    pool.shutdown()
