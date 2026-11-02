# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for :class:`SharedMemoryPool` descriptor usage.

A large ``VIDEO_FRAME_BATCH_SIZE`` (e.g. 256 with a blocks-multiplier of 2)
allocates 512 pool blocks. Holding an open handle per block costs two file
descriptors each and exhausts the default 1024 descriptor limit before a
single frame is decoded.
"""

import os
import sys
import unittest
from multiprocessing import shared_memory

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.utils.decoder import SharedMemoryPool  # noqa: E402


def _open_fd_count() -> int:
    return len(os.listdir(f"/proc/{os.getpid()}/fd"))


@unittest.skipUnless(os.path.isdir("/proc/self/fd"), "requires /proc")
class TestSharedMemoryPoolDescriptors(unittest.TestCase):
    def test_pool_does_not_retain_a_descriptor_per_block(self):
        """Allocating many blocks must not scale open descriptors."""
        baseline = _open_fd_count()
        pool = SharedMemoryPool(max_blocks=256, block_size=4096)
        try:
            growth = _open_fd_count() - baseline
            self.assertLess(
                growth,
                16,
                f"pool retained {growth} descriptors for 256 blocks; "
                "descriptors must be released after allocation",
            )
            self.assertEqual(pool.total_blocks(), 256)
            self.assertEqual(pool.free_blocks(), 256)
        finally:
            pool.shutdown()

    def test_block_is_usable_after_pool_releases_descriptor(self):
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
            self.assertEqual(pool.used_blocks(), 0)
        finally:
            pool.shutdown()

    def test_shutdown_unlinks_every_segment(self):
        """No segment may survive shutdown, otherwise /dev/shm leaks."""
        pool = SharedMemoryPool(max_blocks=8, block_size=4096)
        names = [pool.acquire() for _ in range(8)]
        for name in names:
            pool.release(name)
        pool.shutdown()

        for name in names:
            with self.assertRaises(FileNotFoundError):
                shared_memory.SharedMemory(name=name)

    def test_shutdown_is_idempotent(self):
        """Double shutdown must not raise, so cleanup paths can be defensive."""
        pool = SharedMemoryPool(max_blocks=4, block_size=4096)
        pool.shutdown()
        pool.shutdown()


if __name__ == "__main__":
    unittest.main()
