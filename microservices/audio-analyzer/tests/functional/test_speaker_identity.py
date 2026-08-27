"""
Tier 1 — SpeakerIdentityStore unit tests.

These tests exercise the speaker lock-on, cross-chunk identity persistence,
session isolation, TTL eviction, and reset logic.  Only numpy is required —
no torch, no pyannote, no ML model files.

Run:
    pytest tests/functional/test_speaker_identity.py -m tier1 -v
"""
import time
import unittest

import numpy as np
import pytest

from components.asr.diarization.speaker_identity import SpeakerIdentityStore


@pytest.mark.tier1
class SpeakerIdentityStoreTests(unittest.TestCase):
    def test_locks_onto_longest_speaking_label_in_first_chunk(self):
        store = SpeakerIdentityStore(similarity_threshold=0.75, lock_min_duration_sec=0.5)

        label_embeddings = {
            "SPEAKER_00": np.array([1.0, 0.0], dtype=np.float32),
            "SPEAKER_01": np.array([0.0, 1.0], dtype=np.float32),
        }
        turns = [
            {"start": 0.0, "end": 3.0, "speaker": "SPEAKER_00"},  # 3.0s — longest
            {"start": 3.0, "end": 3.6, "speaker": "SPEAKER_01"},  # 0.6s
        ]

        result = store.resolve("session-1", label_embeddings, turns)

        self.assertTrue(result["SPEAKER_00"])
        self.assertFalse(result["SPEAKER_01"])

    def test_no_lock_when_no_turn_meets_minimum_duration(self):
        store = SpeakerIdentityStore(similarity_threshold=0.75, lock_min_duration_sec=1.0)

        label_embeddings = {"SPEAKER_00": np.array([1.0, 0.0], dtype=np.float32)}
        turns = [{"start": 0.0, "end": 0.4, "speaker": "SPEAKER_00"}]

        result = store.resolve("session-2", label_embeddings, turns)

        self.assertFalse(result["SPEAKER_00"])

    def test_same_identity_recognized_across_chunks_despite_label_reset(self):
        store = SpeakerIdentityStore(similarity_threshold=0.75, lock_min_duration_sec=0.5)

        # Chunk 1: customer is SPEAKER_00.
        store.resolve(
            "session-3",
            {"SPEAKER_00": np.array([1.0, 0.0], dtype=np.float32)},
            [{"start": 0.0, "end": 2.0, "speaker": "SPEAKER_00"}],
        )

        # Chunk 2: pyannote resets labels — same voice is now SPEAKER_01,
        # with a slightly perturbed but highly similar embedding.
        result = store.resolve(
            "session-3",
            {
                "SPEAKER_01": np.array([0.98, 0.05], dtype=np.float32),
                "SPEAKER_00": np.array([0.0, 1.0], dtype=np.float32),
            },
            [
                {"start": 0.0, "end": 2.0, "speaker": "SPEAKER_01"},
                {"start": 2.0, "end": 3.0, "speaker": "SPEAKER_00"},
            ],
        )

        self.assertTrue(result["SPEAKER_01"])
        self.assertFalse(result["SPEAKER_00"])

    def test_dissimilar_embedding_is_not_primary(self):
        store = SpeakerIdentityStore(similarity_threshold=0.75, lock_min_duration_sec=0.5)

        store.resolve(
            "session-4",
            {"SPEAKER_00": np.array([1.0, 0.0], dtype=np.float32)},
            [{"start": 0.0, "end": 2.0, "speaker": "SPEAKER_00"}],
        )

        result = store.resolve(
            "session-4",
            {"SPEAKER_00": np.array([0.0, 1.0], dtype=np.float32)},
            [{"start": 0.0, "end": 2.0, "speaker": "SPEAKER_00"}],
        )

        self.assertFalse(result["SPEAKER_00"])

    def test_sessions_are_isolated(self):
        store = SpeakerIdentityStore(similarity_threshold=0.75, lock_min_duration_sec=0.5)

        store.resolve(
            "session-a",
            {"SPEAKER_00": np.array([1.0, 0.0], dtype=np.float32)},
            [{"start": 0.0, "end": 2.0, "speaker": "SPEAKER_00"}],
        )
        result_b = store.resolve(
            "session-b",
            {"SPEAKER_00": np.array([0.0, 1.0], dtype=np.float32)},
            [{"start": 0.0, "end": 2.0, "speaker": "SPEAKER_00"}],
        )
        result_a_again = store.resolve(
            "session-a",
            {"SPEAKER_00": np.array([1.0, 0.0], dtype=np.float32)},
            [{"start": 0.0, "end": 2.0, "speaker": "SPEAKER_00"}],
        )

        self.assertTrue(result_b["SPEAKER_00"])
        self.assertTrue(result_a_again["SPEAKER_00"])

    def test_idle_session_is_evicted_after_ttl(self):
        store = SpeakerIdentityStore(
            similarity_threshold=0.75, lock_min_duration_sec=0.5, session_ttl_seconds=0.05,
        )

        store.resolve(
            "session-ttl",
            {"SPEAKER_00": np.array([1.0, 0.0], dtype=np.float32)},
            [{"start": 0.0, "end": 2.0, "speaker": "SPEAKER_00"}],
        )
        self.assertIn("session-ttl", store._sessions)

        time.sleep(0.1)

        store.resolve(
            "session-other",
            {"SPEAKER_00": np.array([0.0, 1.0], dtype=np.float32)},
            [{"start": 0.0, "end": 2.0, "speaker": "SPEAKER_00"}],
        )

        self.assertNotIn("session-ttl", store._sessions)

    def test_reset_drops_session_state(self):
        store = SpeakerIdentityStore(similarity_threshold=0.75, lock_min_duration_sec=0.5)

        store.resolve(
            "session-reset",
            {"SPEAKER_00": np.array([1.0, 0.0], dtype=np.float32)},
            [{"start": 0.0, "end": 2.0, "speaker": "SPEAKER_00"}],
        )
        self.assertIn("session-reset", store._sessions)

        store.reset("session-reset")

        self.assertNotIn("session-reset", store._sessions)


if __name__ == "__main__":
    unittest.main()
