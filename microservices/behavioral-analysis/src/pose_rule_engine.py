# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
Generic Declarative Pose Rule Engine

Evaluates pose patterns defined in YAML using a simple, intuitive DSL.
New patterns can be added without code changes.

Relations:
  above, below, left_of, right_of  — positional comparison
  near, far                        — distance (body-relative threshold)
  moving_fast, stationary          — velocity between frames
  bent, straight                   — joint angle at a vertex
  not_<relation>                   — negate any relation

Temporal:
  Ordered phases → sliding split (finds best partition)
  window_size    → sliding window (fixed-size evaluation)

Per-side:
  When per_side=true, short names (wrist, elbow, etc.) are tried
  as both left_ and right_ variants independently.
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)

# COCO 17-keypoint name-to-index mapping
KEYPOINT_INDEX: dict[str, int] = {
    "nose": 0,
    "left_eye": 1,
    "right_eye": 2,
    "left_ear": 3,
    "right_ear": 4,
    "left_shoulder": 5,
    "right_shoulder": 6,
    "left_elbow": 7,
    "right_elbow": 8,
    "left_wrist": 9,
    "right_wrist": 10,
    "left_hip": 11,
    "right_hip": 12,
    "left_knee": 13,
    "right_knee": 14,
    "left_ankle": 15,
    "right_ankle": 16,
}

# Short names that expand with per_side
EXPANDABLE_NAMES: set[str] = {
    "wrist", "elbow", "shoulder", "hip", "knee", "ankle", "eye", "ear",
}


def _midpoint(p1: tuple[float, float], p2: tuple[float, float]) -> tuple[float, float]:
    return ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)


def _euclidean(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def _angle_at_vertex(
    a: tuple[float, float], vertex: tuple[float, float], c: tuple[float, float]
) -> float:
    """Angle in degrees at vertex formed by points a-vertex-c."""
    va = (a[0] - vertex[0], a[1] - vertex[1])
    vc = (c[0] - vertex[0], c[1] - vertex[1])
    dot = va[0] * vc[0] + va[1] * vc[1]
    mag_a = math.hypot(va[0], va[1])
    mag_c = math.hypot(vc[0], vc[1])
    if mag_a < 1e-6 or mag_c < 1e-6:
        return 0.0
    cos_angle = max(-1.0, min(1.0, dot / (mag_a * mag_c)))
    return math.degrees(math.acos(cos_angle))


def _get_keypoint_xy(keypoints: np.ndarray, idx: int) -> tuple[float, float]:
    return (float(keypoints[idx][0]), float(keypoints[idx][1]))


# Virtual reference points — keyed by name.
# Each entry is (compute_fn, required_keypoint_indices).
# The engine checks confidence of required keypoints before computing.
VIRTUAL_POINTS: dict[str, tuple[Any, list[int]]] = {
    "waist_midpoint": (
        lambda kps: _midpoint(
            _get_keypoint_xy(kps, KEYPOINT_INDEX["left_hip"]),
            _get_keypoint_xy(kps, KEYPOINT_INDEX["right_hip"]),
        ),
        [KEYPOINT_INDEX["left_hip"], KEYPOINT_INDEX["right_hip"]],
    ),
    "chest_midpoint": (
        lambda kps: _midpoint(
            _get_keypoint_xy(kps, KEYPOINT_INDEX["left_shoulder"]),
            _get_keypoint_xy(kps, KEYPOINT_INDEX["right_shoulder"]),
        ),
        [KEYPOINT_INDEX["left_shoulder"], KEYPOINT_INDEX["right_shoulder"]],
    ),
    "torso_center": (
        lambda kps: _midpoint(
            _midpoint(
                _get_keypoint_xy(kps, KEYPOINT_INDEX["left_shoulder"]),
                _get_keypoint_xy(kps, KEYPOINT_INDEX["right_shoulder"]),
            ),
            _midpoint(
                _get_keypoint_xy(kps, KEYPOINT_INDEX["left_hip"]),
                _get_keypoint_xy(kps, KEYPOINT_INDEX["right_hip"]),
            ),
        ),
        [
            KEYPOINT_INDEX["left_shoulder"], KEYPOINT_INDEX["right_shoulder"],
            KEYPOINT_INDEX["left_hip"], KEYPOINT_INDEX["right_hip"],
        ],
    ),
    "head_center": (
        lambda kps: _midpoint(
            _get_keypoint_xy(kps, KEYPOINT_INDEX["left_ear"]),
            _get_keypoint_xy(kps, KEYPOINT_INDEX["right_ear"]),
        ),
        [KEYPOINT_INDEX["left_ear"], KEYPOINT_INDEX["right_ear"]],
    ),
}


def _torso_length(keypoints: np.ndarray, confidences: np.ndarray = None, min_conf: float = 0.0) -> float:
    """Distance from chest_midpoint to waist_midpoint.

    Returns 0.0 if any required keypoint has confidence below min_conf.
    """
    required = [
        KEYPOINT_INDEX["left_shoulder"], KEYPOINT_INDEX["right_shoulder"],
        KEYPOINT_INDEX["left_hip"], KEYPOINT_INDEX["right_hip"],
    ]
    if confidences is not None and min_conf > 0:
        for idx in required:
            if confidences[idx] < min_conf:
                return 0.0

    chest = _midpoint(
        _get_keypoint_xy(keypoints, KEYPOINT_INDEX["left_shoulder"]),
        _get_keypoint_xy(keypoints, KEYPOINT_INDEX["right_shoulder"]),
    )
    waist = _midpoint(
        _get_keypoint_xy(keypoints, KEYPOINT_INDEX["left_hip"]),
        _get_keypoint_xy(keypoints, KEYPOINT_INDEX["right_hip"]),
    )
    return _euclidean(chest, waist)


@dataclass
class PhaseMatch:
    """Result of evaluating a single phase."""

    name: str
    matched: bool
    match_count: int
    required: int


@dataclass
class EngineResult:
    """Result of the pose rule engine evaluation."""

    matched: bool
    confidence: float
    description: str
    phase_matches: list[PhaseMatch] = field(default_factory=list)
    key_frames: list[int] = field(default_factory=list)


class PoseRuleEngine:
    """
    Generic pose pattern evaluator driven by YAML configuration.

    Usage:
        engine = PoseRuleEngine(min_confidence=0.5)
        result = engine.evaluate(poses, pattern_config)
    """

    def __init__(self, min_confidence: float = 0.5):
        self.min_confidence = min_confidence

    def evaluate(
        self,
        poses: list,
        pattern_cfg: dict[str, Any],
        min_frames: int = 10,
    ) -> EngineResult:
        """
        Evaluate a pose sequence against a pattern configuration.

        Args:
            poses: List of Pose objects with .keypoints and .confidences
            pattern_cfg: The full pattern dict from patterns.yaml
            min_frames: Minimum frames required for evaluation
        """
        pose_cfg = pattern_cfg.get("pose", {})
        phases = pose_cfg.get("phases", [])

        if not phases:
            return EngineResult(matched=False, confidence=0.0, description="No phases defined")

        if len(poses) < min_frames:
            return EngineResult(
                matched=False, confidence=0.0,
                description=f"Not enough frames: {len(poses)}/{min_frames}",
            )

        per_side = pose_cfg.get("per_side", False)
        window_size = pose_cfg.get("window_size", None)

        if per_side:
            # Try left side, then right side — return first match
            for side in ("left", "right"):
                result = self._evaluate_with_side(poses, phases, window_size, side)
                if result.matched:
                    result.description = f"[{side}] {result.description}"
                    return result
            return EngineResult(
                matched=False, confidence=0.0,
                description="Pattern not detected (tried both sides)",
            )
        else:
            return self._evaluate_with_side(poses, phases, window_size, side=None)

    def _evaluate_with_side(
        self,
        poses: list,
        phases: list[dict[str, Any]],
        window_size: Optional[int],
        side: Optional[str],
    ) -> EngineResult:
        """Evaluate phases with a specific side expansion (or None for no expansion)."""
        if window_size is not None:
            return self._evaluate_window(poses, phases, window_size, side)
        else:
            return self._evaluate_sliding_split(poses, phases, side)

    def _evaluate_sliding_split(
        self,
        poses: list,
        phases: list[dict[str, Any]],
        side: Optional[str],
    ) -> EngineResult:
        """
        Sliding split: find the best partition point(s) for ordered phases.
        For N phases, tries all possible N-1 split points.
        """
        n = len(poses)
        num_phases = len(phases)

        # Pre-compute per-frame match for each phase
        frame_matches = []
        for phase in phases:
            matches = self._compute_phase_frame_matches(poses, phase, side)
            frame_matches.append(matches)

        # Get min_frames requirements
        min_frames_per_phase = [p.get("min_frames", 1) for p in phases]

        # For a single phase, evaluate across entire sequence
        if num_phases == 1:
            count = sum(frame_matches[0])
            required = min_frames_per_phase[0]
            if count >= required:
                conf = count / n
                matched_indices = [i for i, m in enumerate(frame_matches[0]) if m]
                return EngineResult(
                    matched=True,
                    confidence=min(1.0, conf),
                    description=f"Phase '{phases[0].get('name', '0')}': {count}/{n} frames matched",
                    phase_matches=[PhaseMatch(
                        name=phases[0].get("name", "0"),
                        matched=True, match_count=count, required=required,
                    )],
                    key_frames=matched_indices,
                )
            return EngineResult(
                matched=False, confidence=0.0,
                description=f"Phase '{phases[0].get('name', '0')}': {count}/{required} frames (need {required})",
            )

        # For 2 phases, optimized linear scan
        if num_phases == 2:
            return self._find_best_two_phase_split(
                n, frame_matches, min_frames_per_phase, phases
            )

        # For 3+ phases, recursive search
        return self._find_best_multi_split(
            n, num_phases, frame_matches, min_frames_per_phase, phases
        )

    def _find_best_two_phase_split(
        self,
        n: int,
        frame_matches: list[list[bool]],
        min_frames_per_phase: list[int],
        phases: list[dict[str, Any]],
    ) -> EngineResult:
        """Optimized split search for exactly 2 phases."""
        min_early = min_frames_per_phase[0]
        min_late = min_frames_per_phase[1]
        best_conf = 0.0
        best_split = -1
        best_counts = (0, 0)

        for split in range(min_early, n - min_late + 1):
            early_count = sum(frame_matches[0][:split])
            late_count = sum(frame_matches[1][split:])

            if early_count >= min_early and late_count >= min_late:
                conf = (early_count + late_count) / n
                if conf > best_conf:
                    best_conf = conf
                    best_split = split
                    best_counts = (early_count, late_count)

        if best_split < 0:
            return EngineResult(
                matched=False, confidence=0.0,
                description="Pattern not detected in any split",
            )

        # Collect frame indices that matched in each phase
        early_indices = [i for i in range(best_split) if frame_matches[0][i]]
        late_indices = [i for i in range(best_split, n) if frame_matches[1][i]]
        key_frames = early_indices + late_indices

        phase_matches = [
            PhaseMatch(
                name=phases[0].get("name", "0"),
                matched=True, match_count=best_counts[0], required=min_early,
            ),
            PhaseMatch(
                name=phases[1].get("name", "1"),
                matched=True, match_count=best_counts[1], required=min_late,
            ),
        ]
        desc = (
            f"'{phases[0].get('name', '0')}' {best_counts[0]} frames (0-{best_split - 1}), "
            f"'{phases[1].get('name', '1')}' {best_counts[1]} frames ({best_split}-{n - 1})"
        )
        return EngineResult(
            matched=True, confidence=min(1.0, best_conf),
            description=desc, phase_matches=phase_matches,
            key_frames=key_frames,
        )

    def _find_best_multi_split(
        self,
        n: int,
        num_phases: int,
        frame_matches: list[list[bool]],
        min_frames_per_phase: list[int],
        phases: list[dict[str, Any]],
    ) -> EngineResult:
        """Handle 3+ phases by trying all valid split configurations."""
        best_conf = 0.0
        best_counts: list[int] = []
        best_splits: list[int] = []

        def search(phase_idx: int, start: int, splits: list[int], counts: list[int]):
            nonlocal best_conf, best_counts, best_splits

            if phase_idx == num_phases - 1:
                count = sum(frame_matches[phase_idx][start:])
                if count >= min_frames_per_phase[phase_idx]:
                    total = sum(counts) + count
                    conf = total / n
                    if conf > best_conf:
                        best_conf = conf
                        best_counts = counts + [count]
                        best_splits = splits[:]
                return

            min_needed = min_frames_per_phase[phase_idx]
            remaining_min = sum(min_frames_per_phase[phase_idx + 1:])
            max_end = n - remaining_min

            for end in range(start + min_needed, max_end + 1):
                count = sum(frame_matches[phase_idx][start:end])
                if count >= min_needed:
                    search(phase_idx + 1, end, splits + [end], counts + [count])

        search(0, 0, [], [])

        if not best_counts:
            return EngineResult(
                matched=False, confidence=0.0,
                description="Pattern not detected across phases",
            )

        phase_matches = []
        desc_parts = []
        key_frames = []
        prev = 0
        for i, phase in enumerate(phases):
            end = best_splits[i] if i < len(best_splits) else n
            phase_matches.append(PhaseMatch(
                name=phase.get("name", str(i)),
                matched=True, match_count=best_counts[i],
                required=min_frames_per_phase[i],
            ))
            key_frames.extend(j for j in range(prev, end) if frame_matches[i][j])
            desc_parts.append(f"'{phase.get('name', str(i))}' {best_counts[i]} frames ({prev}-{end - 1})")
            prev = end

        return EngineResult(
            matched=True, confidence=min(1.0, best_conf),
            description=", ".join(desc_parts), phase_matches=phase_matches,
            key_frames=key_frames,
        )

    def _evaluate_window(
        self,
        poses: list,
        phases: list[dict[str, Any]],
        window_size: int,
        side: Optional[str],
    ) -> EngineResult:
        """Sliding window: all phases evaluated within a fixed-size window."""
        n = len(poses)
        if window_size > n:
            return EngineResult(
                matched=False, confidence=0.0,
                description=f"Window size {window_size} > sequence length {n}",
            )

        # Pre-compute frame matches for all phases
        frame_matches = []
        for phase in phases:
            matches = self._compute_phase_frame_matches(poses, phase, side)
            frame_matches.append(matches)

        best_count = 0
        best_start = -1

        for start in range(0, n - window_size + 1):
            end = start + window_size
            all_phases_ok = True
            window_total = 0

            for i, phase in enumerate(phases):
                required = phase.get("min_frames", 1)
                count = sum(frame_matches[i][start:end])
                if count < required:
                    all_phases_ok = False
                    break
                window_total += count

            if all_phases_ok and window_total > best_count:
                best_count = window_total
                best_start = start

        if best_start < 0:
            return EngineResult(
                matched=False, confidence=0.0,
                description="Pattern not detected in any window",
            )

        conf = best_count / window_size
        best_end = best_start + window_size
        key_frames = []
        for i in range(len(phases)):
            key_frames.extend(
                j for j in range(best_start, best_end) if frame_matches[i][j]
            )
        key_frames = sorted(set(key_frames))
        return EngineResult(
            matched=True, confidence=min(1.0, conf),
            description=f"Matched in window [{best_start}:{best_end}]",
            key_frames=key_frames,
        )

    def _compute_phase_frame_matches(
        self,
        poses: list,
        phase: dict[str, Any],
        side: Optional[str],
    ) -> list[bool]:
        """Compute per-frame match for a phase's conditions."""
        conditions = phase.get("conditions", [])
        match_mode = phase.get("match", "all")
        results = []

        for i, pose in enumerate(poses):
            prev_pose = poses[i - 1] if i > 0 else None
            frame_ok = self._evaluate_frame(pose, prev_pose, conditions, match_mode, side)
            results.append(frame_ok)

        return results

    def _evaluate_frame(
        self,
        pose,
        prev_pose,
        conditions: list[dict[str, Any]],
        match_mode: str,
        side: Optional[str],
    ) -> bool:
        """Evaluate all conditions for a single frame."""
        if not conditions:
            return True

        results = []
        for cond in conditions:
            result = self._evaluate_condition(pose, prev_pose, cond, side)
            results.append(result)

        if match_mode == "any":
            return any(results)
        return all(results)

    def _evaluate_condition(
        self,
        pose,
        prev_pose,
        cond: dict[str, Any],
        side: Optional[str],
    ) -> bool:
        """Evaluate a single condition."""
        relation = cond.get("relation", "")

        # Handle not_ prefix
        negated = False
        if relation.startswith("not_"):
            negated = True
            relation = relation[4:]

        result = self._evaluate_relation(pose, prev_pose, cond, relation, side)

        return (not result) if negated else result

    def _evaluate_relation(
        self,
        pose,
        prev_pose,
        cond: dict[str, Any],
        relation: str,
        side: Optional[str],
    ) -> bool:
        """Dispatch to the appropriate relation evaluator."""
        subject_name = cond.get("subject", "")
        reference_name = cond.get("reference", "")

        # Expand short names with side prefix
        subject_name = self._expand_name(subject_name, side)

        if relation in ("above", "below", "left_of", "right_of"):
            return self._rel_position(pose, subject_name, reference_name, relation, side)
        elif relation in ("near", "far"):
            threshold = cond.get("threshold", 0.6)
            return self._rel_distance(pose, subject_name, reference_name, relation, threshold, side)
        elif relation in ("moving_fast", "stationary"):
            threshold = cond.get("threshold", 0.1)
            return self._rel_velocity(pose, prev_pose, subject_name, relation, threshold)
        elif relation in ("bent", "straight"):
            min_angle = cond.get("min_angle", 0)
            max_angle = cond.get("max_angle", 360)
            if relation == "straight":
                min_angle = cond.get("min_angle", 150)
                max_angle = cond.get("max_angle", 180)
            return self._rel_angle(pose, subject_name, reference_name, min_angle, max_angle, side)
        else:
            logger.warning(f"Unknown relation: {relation}")
            return False

    def _rel_position(
        self,
        pose,
        subject_name: str,
        reference_name: str,
        relation: str,
        side: Optional[str],
    ) -> bool:
        """Evaluate positional relations: above, below, left_of, right_of."""
        subject = self._resolve_point(pose, subject_name)
        ref = self._resolve_point(pose, self._expand_name(reference_name, side))
        if subject is None or ref is None:
            return False

        if relation == "above":
            return subject[1] < ref[1]
        elif relation == "below":
            return subject[1] > ref[1]
        elif relation == "left_of":
            return subject[0] < ref[0]
        elif relation == "right_of":
            return subject[0] > ref[0]
        return False

    def _rel_distance(
        self,
        pose,
        subject_name: str,
        reference_name: str,
        relation: str,
        threshold: float,
        side: Optional[str],
    ) -> bool:
        """Evaluate distance relations: near, far (body-relative)."""
        subject = self._resolve_point(pose, subject_name)
        ref = self._resolve_point(pose, self._expand_name(reference_name, side))
        if subject is None or ref is None:
            return False

        torso = _torso_length(pose.keypoints, pose.confidences, self.min_confidence)
        if torso < 1e-4:
            return False

        dist = _euclidean(subject, ref)
        normalized = dist / torso

        if relation == "near":
            return normalized < threshold
        elif relation == "far":
            return normalized >= threshold
        return False

    def _rel_velocity(
        self,
        pose,
        prev_pose,
        subject_name: str,
        relation: str,
        threshold: float,
    ) -> bool:
        """Evaluate velocity relations: moving_fast, stationary."""
        if prev_pose is None:
            return relation == "stationary"

        curr = self._resolve_point(pose, subject_name)
        prev = self._resolve_point(prev_pose, subject_name)
        if curr is None or prev is None:
            return False

        torso = _torso_length(pose.keypoints, pose.confidences, self.min_confidence)
        if torso < 1e-4:
            return False

        velocity = _euclidean(curr, prev) / torso

        if relation == "moving_fast":
            return velocity > threshold
        elif relation == "stationary":
            return velocity < threshold
        return False

    def _rel_angle(
        self,
        pose,
        subject_name: str,
        reference_spec: Any,
        min_angle: float,
        max_angle: float,
        side: Optional[str],
    ) -> bool:
        """
        Evaluate angle relations: bent, straight.

        subject is the vertex point.
        reference is [point_a, point_c] — the two endpoints forming the angle.
        """
        vertex = self._resolve_point(pose, subject_name)
        if vertex is None:
            return False

        if not isinstance(reference_spec, list) or len(reference_spec) != 2:
            logger.warning(f"Angle relation requires reference as [point_a, point_c], got: {reference_spec}")
            return False

        point_a_name = self._expand_name(reference_spec[0], side)
        point_c_name = self._expand_name(reference_spec[1], side)

        point_a = self._resolve_point(pose, point_a_name)
        point_c = self._resolve_point(pose, point_c_name)
        if point_a is None or point_c is None:
            return False

        angle = _angle_at_vertex(point_a, vertex, point_c)
        return min_angle <= angle <= max_angle

    def _resolve_point(
        self, pose, name: str
    ) -> Optional[tuple[float, float]]:
        """Resolve a point name to (x, y) coordinates."""
        if not name:
            return None

        # Virtual points — check confidence of constituent keypoints
        if name in VIRTUAL_POINTS:
            compute_fn, required_indices = VIRTUAL_POINTS[name]
            for idx in required_indices:
                if pose.confidences[idx] < self.min_confidence:
                    return None
            return compute_fn(pose.keypoints)

        # Regular keypoint
        idx = KEYPOINT_INDEX.get(name)
        if idx is None:
            logger.warning(f"Unknown keypoint: {name}")
            return None

        if pose.confidences[idx] < self.min_confidence:
            return None

        return _get_keypoint_xy(pose.keypoints, idx)

    def _expand_name(self, name: str, side: Optional[str]) -> str:
        """Expand a short name (e.g. 'wrist') to full name (e.g. 'left_wrist') when side is set."""
        if side and isinstance(name, str) and name in EXPANDABLE_NAMES:
            return f"{side}_{name}"
        return name
