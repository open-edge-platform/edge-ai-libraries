# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Comprehensive unit tests for pose_analyzer module."""

from pathlib import Path
from types import SimpleNamespace
import sys

import numpy as np
import pytest

# Ensure direct module imports (pose_analyzer, pose_rule_engine, etc.) resolve in tests.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pose_analyzer import Keypoints, PatternResult, Pose, PoseAnalyzer


@pytest.fixture
def sample_pose() -> Pose:
    keypoints = np.array(
        [[float(i), float(i + 100)] for i in range(17)],
        dtype=float,
    )
    confidences = np.array([0.1 + (i * 0.01) for i in range(17)], dtype=float)
    return Pose(keypoints=keypoints, confidences=confidences, timestamp=123)


@pytest.fixture
def pose_sequence(sample_pose: Pose) -> list[Pose]:
    return [sample_pose, sample_pose]


@pytest.fixture
def analyzer() -> PoseAnalyzer:
    return PoseAnalyzer(min_frames=5, confidence_threshold=0.6)


def test_pose_get_keypoint_and_properties(sample_pose: Pose) -> None:
    left_wrist = sample_pose.left_wrist
    right_wrist = sample_pose.right_wrist
    left_hip = sample_pose.left_hip
    right_hip = sample_pose.right_hip
    left_shoulder = sample_pose.left_shoulder
    right_shoulder = sample_pose.right_shoulder

    assert left_wrist == (
        sample_pose.keypoints[Keypoints.LEFT_WRIST][0],
        sample_pose.keypoints[Keypoints.LEFT_WRIST][1],
        sample_pose.confidences[Keypoints.LEFT_WRIST],
    )
    assert right_wrist == (
        sample_pose.keypoints[Keypoints.RIGHT_WRIST][0],
        sample_pose.keypoints[Keypoints.RIGHT_WRIST][1],
        sample_pose.confidences[Keypoints.RIGHT_WRIST],
    )
    assert left_hip == (
        sample_pose.keypoints[Keypoints.LEFT_HIP][0],
        sample_pose.keypoints[Keypoints.LEFT_HIP][1],
        sample_pose.confidences[Keypoints.LEFT_HIP],
    )
    assert right_hip == (
        sample_pose.keypoints[Keypoints.RIGHT_HIP][0],
        sample_pose.keypoints[Keypoints.RIGHT_HIP][1],
        sample_pose.confidences[Keypoints.RIGHT_HIP],
    )
    assert left_shoulder == (
        sample_pose.keypoints[Keypoints.LEFT_SHOULDER][0],
        sample_pose.keypoints[Keypoints.LEFT_SHOULDER][1],
        sample_pose.confidences[Keypoints.LEFT_SHOULDER],
    )
    assert right_shoulder == (
        sample_pose.keypoints[Keypoints.RIGHT_SHOULDER][0],
        sample_pose.keypoints[Keypoints.RIGHT_SHOULDER][1],
        sample_pose.confidences[Keypoints.RIGHT_SHOULDER],
    )


def test_pose_midpoints(sample_pose: Pose) -> None:
    expected_waist_x = (
        sample_pose.keypoints[Keypoints.LEFT_HIP][0]
        + sample_pose.keypoints[Keypoints.RIGHT_HIP][0]
    ) / 2
    expected_waist_y = (
        sample_pose.keypoints[Keypoints.LEFT_HIP][1]
        + sample_pose.keypoints[Keypoints.RIGHT_HIP][1]
    ) / 2

    expected_chest_x = (
        sample_pose.keypoints[Keypoints.LEFT_SHOULDER][0]
        + sample_pose.keypoints[Keypoints.RIGHT_SHOULDER][0]
    ) / 2
    expected_chest_y = (
        sample_pose.keypoints[Keypoints.LEFT_SHOULDER][1]
        + sample_pose.keypoints[Keypoints.RIGHT_SHOULDER][1]
    ) / 2

    assert sample_pose.waist_midpoint == (expected_waist_x, expected_waist_y)
    assert sample_pose.chest_midpoint == (expected_chest_x, expected_chest_y)


def test_pose_get_keypoint_out_of_range_raises(sample_pose: Pose) -> None:
    with pytest.raises(IndexError):
        sample_pose.get_keypoint(999)


def test_pattern_result_default_list_isolated_between_instances() -> None:
    result_a = PatternResult(
        matched=True,
        confidence=0.9,
        pattern_id="a",
        description="desc",
    )
    result_b = PatternResult(
        matched=False,
        confidence=0.1,
        pattern_id="b",
        description="desc",
    )

    result_a.key_frames.append(1)

    assert result_a.key_frames == [1]
    assert result_b.key_frames == []


def test_pose_analyzer_init_and_is_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, float] = {}

    class FakeRuleEngine:
        def __init__(self, min_confidence: float):
            captured["min_confidence"] = min_confidence

    import pose_analyzer as module_under_test

    monkeypatch.setattr(module_under_test, "PoseRuleEngine", FakeRuleEngine)

    pa = module_under_test.PoseAnalyzer(min_frames=7, confidence_threshold=0.77)

    assert pa.min_frames == 7
    assert pa.confidence_threshold == 0.77
    assert pa.pattern_config == {}
    assert captured["min_confidence"] == 0.77
    assert pa.is_loaded() is True


def test_detect_pattern_returns_disabled_when_pattern_disabled(
    analyzer: PoseAnalyzer,
    pose_sequence: list[Pose],
) -> None:
    analyzer.pattern_config = {
        "shelf_to_waist": {
            "enabled": False,
        }
    }

    result = analyzer.detect_pattern(pose_sequence, pattern_id="shelf_to_waist")

    assert result.matched is False
    assert result.confidence == 0.0
    assert result.pattern_id == "shelf_to_waist"
    assert "disabled" in result.description


def test_detect_pattern_uses_rule_engine_for_phases(
    analyzer: PoseAnalyzer,
    pose_sequence: list[Pose],
) -> None:
    engine_result = SimpleNamespace(
        matched=True,
        confidence=0.88,
        description="phase match",
        key_frames=[1, 3, 5],
    )

    calls: list[dict[str, object]] = []

    class FakeEngine:
        def evaluate(
            self,
            seq: list[Pose],
            config: dict[str, object],
            min_frames: int,
        ) -> SimpleNamespace:
            calls.append({"seq": seq, "config": config, "min_frames": min_frames})
            return engine_result

    analyzer.rule_engine = FakeEngine()  # type: ignore[assignment]
    analyzer.pattern_config = {
        "shelf_to_waist": {
            "enabled": True,
            "pose": {
                "phases": [
                    {"name": "phase-a"},
                ]
            },
        }
    }

    result = analyzer.detect_pattern(pose_sequence, pattern_id="shelf_to_waist")

    assert result == PatternResult(
        matched=True,
        confidence=0.88,
        pattern_id="shelf_to_waist",
        description="phase match",
        key_frames=[1, 3, 5],
    )
    assert len(calls) == 1
    assert calls[0]["seq"] == pose_sequence
    assert calls[0]["min_frames"] == analyzer.min_frames


def test_detect_pattern_without_phases_returns_not_matched(
    analyzer: PoseAnalyzer,
    pose_sequence: list[Pose],
) -> None:
    analyzer.pattern_config = {
        "pattern_without_phases": {
            "enabled": True,
            "pose": {},
        }
    }

    result = analyzer.detect_pattern(pose_sequence, pattern_id="pattern_without_phases")

    assert result.matched is False
    assert result.confidence == 0.0
    assert result.pattern_id == "pattern_without_phases"
    assert "no phases defined" in result.description


def test_detect_pattern_rule_engine_exception_propagates(
    analyzer: PoseAnalyzer,
    pose_sequence: list[Pose],
) -> None:
    class BoomEngine:
        def evaluate(
            self,
            seq: list[Pose],
            config: dict[str, object],
            min_frames: int,
        ) -> SimpleNamespace:
            raise RuntimeError("rule evaluation failed")

    analyzer.rule_engine = BoomEngine()  # type: ignore[assignment]
    analyzer.pattern_config = {
        "shelf_to_waist": {
            "enabled": True,
            "pose": {
                "phases": [
                    {"name": "phase-a"},
                ]
            },
        }
    }

    with pytest.raises(RuntimeError, match="rule evaluation failed"):
        analyzer.detect_pattern(pose_sequence, pattern_id="shelf_to_waist")


def test_detect_all_patterns_default_pattern_when_no_config(
    monkeypatch: pytest.MonkeyPatch,
    analyzer: PoseAnalyzer,
    pose_sequence: list[Pose],
) -> None:
    calls: list[str] = []

    def fake_detect_pattern(
        seq: list[Pose],
        pattern_id: str,
    ) -> PatternResult:
        calls.append(pattern_id)
        return PatternResult(
            matched=False,
            confidence=0.0,
            pattern_id=pattern_id,
            description="default",
        )

    analyzer.pattern_config = {}
    monkeypatch.setattr(analyzer, "detect_pattern", fake_detect_pattern)

    results = analyzer.detect_all_patterns(pose_sequence)

    assert calls == ["shelf_to_waist"]
    assert [r.pattern_id for r in results] == ["shelf_to_waist"]


def test_detect_all_patterns_skips_disabled_patterns(
    monkeypatch: pytest.MonkeyPatch,
    analyzer: PoseAnalyzer,
    pose_sequence: list[Pose],
) -> None:
    calls: list[str] = []

    def fake_detect_pattern(
        seq: list[Pose],
        pattern_id: str,
    ) -> PatternResult:
        calls.append(pattern_id)
        return PatternResult(
            matched=True,
            confidence=0.9,
            pattern_id=pattern_id,
            description="matched",
        )

    analyzer.pattern_config = {
        "enabled_pattern": {"enabled": True},
        "disabled_pattern": {"enabled": False},
        "implicit_enabled": {},
    }
    monkeypatch.setattr(analyzer, "detect_pattern", fake_detect_pattern)

    results = analyzer.detect_all_patterns(pose_sequence)

    assert calls == ["enabled_pattern", "implicit_enabled"]
    assert [r.pattern_id for r in results] == ["enabled_pattern", "implicit_enabled"]


def test_sample_frames_returns_all_when_shorter_or_equal() -> None:
    frames = [(np.zeros((2, 2, 3), dtype=np.uint8), i) for i in range(3)]
    sampled = PoseAnalyzer._sample_frames(frames, 3)
    assert sampled == frames


def test_sample_frames_evenly_when_longer() -> None:
    frames = [(np.zeros((1, 1, 3), dtype=np.uint8), i) for i in range(10)]
    sampled = PoseAnalyzer._sample_frames(frames, 4)
    sampled_ts = [ts for _, ts in sampled]

    assert sampled_ts == [0, 3, 6, 9]


@pytest.mark.asyncio
async def test_analyze_with_vlm_returns_unchanged_when_no_vlm_client() -> None:
    analyzer = PoseAnalyzer(vlm_client=None, pattern_config={"p": {"vlm": {"enabled": True}}})
    original = PatternResult(
        matched=True,
        confidence=0.7,
        pattern_id="p",
        description="pose matched",
    )
    frames = [(np.zeros((1, 1, 3), dtype=np.uint8), 1)]

    result = await analyzer.analyze_with_vlm(frames, original)

    assert result is original
    assert result.vlm_result is None
    assert result.vlm_confirmed is None


@pytest.mark.asyncio
async def test_analyze_with_vlm_skips_when_pattern_vlm_disabled() -> None:
    class DummyClient:
        async def analyze(self, frame_images: list[np.ndarray], prompt: str):
            raise AssertionError("analyze should not be called when VLM is disabled")

    analyzer = PoseAnalyzer(
        vlm_client=DummyClient(),
        pattern_config={"p": {"vlm": {"enabled": False, "prompt": "x"}}},
    )
    original = PatternResult(
        matched=True,
        confidence=0.7,
        pattern_id="p",
        description="pose matched",
    )
    frames = [(np.zeros((1, 1, 3), dtype=np.uint8), 1)]

    result = await analyzer.analyze_with_vlm(frames, original)

    assert result is original


@pytest.mark.asyncio
async def test_analyze_with_vlm_skips_when_prompt_missing() -> None:
    class DummyClient:
        async def analyze(self, frame_images: list[np.ndarray], prompt: str):
            raise AssertionError("analyze should not be called when prompt is missing")

    analyzer = PoseAnalyzer(
        vlm_client=DummyClient(),
        pattern_config={"p": {"vlm": {"enabled": True, "prompt": ""}}},
    )
    original = PatternResult(
        matched=True,
        confidence=0.7,
        pattern_id="p",
        description="pose matched",
    )
    frames = [(np.zeros((1, 1, 3), dtype=np.uint8), 1)]

    result = await analyzer.analyze_with_vlm(frames, original)

    assert result is original


@pytest.mark.asyncio
async def test_analyze_with_vlm_failure_falls_back_to_pose_only() -> None:
    class DummyClient:
        async def analyze(self, frame_images: list[np.ndarray], prompt: str):
            return SimpleNamespace(success=False, error="service unavailable")

    analyzer = PoseAnalyzer(
        vlm_client=DummyClient(),
        pattern_config={"p": {"vlm": {"enabled": True, "prompt": "check"}}},
    )
    original = PatternResult(
        matched=True,
        confidence=0.66,
        pattern_id="p",
        description="pose matched",
    )
    frames = [(np.zeros((1, 1, 3), dtype=np.uint8), 1)]

    result = await analyzer.analyze_with_vlm(frames, original)

    assert result is original
    assert result.vlm_confirmed is None
    assert result.confidence == 0.66
    assert result.vlm_result is None


@pytest.mark.asyncio
async def test_analyze_with_vlm_success_suspicious_true_uses_key_frames_and_prefix() -> None:
    captured: dict[str, object] = {}

    class DummyClient:
        async def analyze(self, frame_images: list[np.ndarray], prompt: str):
            captured["frame_count"] = len(frame_images)
            captured["prompt"] = prompt
            return SimpleNamespace(
                success=True,
                parsed={
                    "suspicious": True,
                    "confidence": 0.8,
                    "reasoning": "object moved to waist",
                },
                metrics={"latency_ms": 123},
            )

    analyzer = PoseAnalyzer(
        vlm_client=DummyClient(),
        pattern_config={
            "p": {
                "vlm": {
                    "enabled": True,
                    "prompt": "confirm behavior",
                    "num_frames": 2,
                }
            }
        },
    )
    original = PatternResult(
        matched=True,
        confidence=0.6,
        pattern_id="p",
        description="pose matched",
        key_frames=[1, 100, 3],
    )

    frames = [
        (np.zeros((2, 2, 3), dtype=np.uint8), 10),
        (np.ones((2, 2, 3), dtype=np.uint8), 20),
        (np.full((2, 2, 3), 2, dtype=np.uint8), 30),
        (np.full((2, 2, 3), 3, dtype=np.uint8), 40),
    ]

    result = await analyzer.analyze_with_vlm(frames, original, frame_key_prefix="cam/")

    assert result.vlm_confirmed is True
    assert result.vlm_result == {
        "suspicious": True,
        "confidence": 0.8,
        "reasoning": "object moved to waist",
    }
    assert result.vlm_metrics == {"latency_ms": 123}
    assert result.confidence == pytest.approx((0.6 + 0.8) / 2)
    assert "VLM confirms" in result.description
    assert captured["frame_count"] == 2
    assert captured["prompt"] == "confirm behavior"


@pytest.mark.asyncio
async def test_analyze_with_vlm_success_suspicious_false_reduces_confidence() -> None:
    class DummyClient:
        async def analyze(self, frame_images: list[np.ndarray], prompt: str):
            return SimpleNamespace(
                success=True,
                parsed={
                    "suspicious": False,
                    "confidence": 0.2,
                    "reasoning": "no concealment seen",
                },
                metrics={"tokens": 50},
            )

    analyzer = PoseAnalyzer(
        vlm_client=DummyClient(),
        pattern_config={
            "p": {
                "vlm": {
                    "enabled": True,
                    "prompt": "confirm behavior",
                    "num_frames": 3,
                }
            }
        },
    )
    original = PatternResult(
        matched=True,
        confidence=0.8,
        pattern_id="p",
        description="pose matched",
        key_frames=[],
    )
    frames = [
        (np.zeros((1, 1, 3), dtype=np.uint8), 1),
        (np.zeros((1, 1, 3), dtype=np.uint8), 2),
        (np.zeros((1, 1, 3), dtype=np.uint8), 3),
        (np.zeros((1, 1, 3), dtype=np.uint8), 4),
    ]

    result = await analyzer.analyze_with_vlm(frames, original)

    assert result.vlm_confirmed is False
    assert result.confidence == pytest.approx(0.4)
    assert "VLM disagrees" in result.description
    assert result.vlm_metrics == {"tokens": 50}


@pytest.mark.asyncio
async def test_analyze_with_vlm_success_with_none_parsed_defaults_to_not_suspicious() -> None:
    class DummyClient:
        async def analyze(self, frame_images: list[np.ndarray], prompt: str):
            return SimpleNamespace(success=True, parsed=None, metrics={"ok": 1})

    analyzer = PoseAnalyzer(
        vlm_client=DummyClient(),
        pattern_config={"p": {"vlm": {"enabled": True, "prompt": "check"}}},
    )
    original = PatternResult(
        matched=True,
        confidence=1.0,
        pattern_id="p",
        description="pose matched",
    )
    frames = [(np.zeros((1, 1, 3), dtype=np.uint8), 1)]

    result = await analyzer.analyze_with_vlm(frames, original)

    assert result.vlm_confirmed is False
    assert result.confidence == pytest.approx(0.5)
    assert result.vlm_result is None


@pytest.mark.asyncio
async def test_analyze_with_vlm_client_exception_propagates() -> None:
    class DummyClient:
        async def analyze(self, frame_images: list[np.ndarray], prompt: str):
            raise RuntimeError("network timeout")

    analyzer = PoseAnalyzer(
        vlm_client=DummyClient(),
        pattern_config={"p": {"vlm": {"enabled": True, "prompt": "check"}}},
    )
    original = PatternResult(
        matched=True,
        confidence=0.9,
        pattern_id="p",
        description="pose matched",
    )
    frames = [(np.zeros((1, 1, 3), dtype=np.uint8), 1)]

    with pytest.raises(RuntimeError, match="network timeout"):
        await analyzer.analyze_with_vlm(frames, original)