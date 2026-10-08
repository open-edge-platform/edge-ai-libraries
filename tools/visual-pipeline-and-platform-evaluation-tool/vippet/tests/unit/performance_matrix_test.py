# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the performance-benchmark matrix builder."""

import unittest
from typing import Any

from tests.performance.perf_helpers.matrix import (
    ALL_VARIANTS,
    ExclusionReason,
    MatrixFilters,
    build_matrix,
)

R = ExclusionReason

PIPELINES: list[dict[str, Any]] = [
    {
        "id": "object-detection",
        "name": "Object Detection",
        "variants": [
            {"id": "od-cpu", "name": "CPU"},
            {"id": "od-gpu", "name": "GPU"},
            {"id": "od-npu", "name": "NPU"},
            {"id": "od-gn", "name": "GPU_NPU"},
        ],
    },
    {
        "id": "smart-parking",
        "name": "Smart Parking",
        "variants": [{"id": "sp-cpu", "name": "CPU"}],
    },
    {
        "id": "lpr",
        "name": "License Plate",
        "variants": [
            {"id": "lpr-cpu", "name": "cpu"},
            {"id": "lpr-fpga", "name": "FPGA"},
        ],
    },
    {"id": "", "name": "broken", "variants": []},
]
DEVICES = [{"device_family": "CPU"}, {"device_family": "gpu"}, {"device_family": "X"}]


def _reasons(matrix: Any) -> dict[tuple[str, str], ExclusionReason]:
    return {(e.pipeline_id, e.variant): e.reason for e in matrix.excluded}


class TestBuildMatrix(unittest.TestCase):
    def test_default_filters(self) -> None:
        matrix = build_matrix(PIPELINES, DEVICES, {}, MatrixFilters())
        self.assertEqual(matrix.available_families, ["CPU", "GPU"])
        self.assertEqual(
            [(c.pipeline_id, c.device_family) for c in matrix.included],
            [
                ("object-detection", "CPU"),
                ("object-detection", "GPU"),
                ("smart-parking", "CPU"),
                ("lpr", "CPU"),
            ],
        )
        reasons = _reasons(matrix)
        self.assertEqual(reasons[("object-detection", "NPU")], R.UNSUPPORTED_FAMILY)
        self.assertEqual(reasons[("object-detection", "GPU_NPU")], R.UNSUPPORTED_FAMILY)
        self.assertEqual(reasons[("lpr", "FPGA")], R.UNSUPPORTED_FAMILY)
        self.assertEqual(reasons[("", ALL_VARIANTS)], R.MALFORMED)

    def test_case_ids_match_pipeline_case_helpers(self) -> None:
        matrix = build_matrix(PIPELINES, DEVICES, {}, MatrixFilters())
        self.assertEqual(matrix.included[0].case_id, "object_detection_cpu")
        self.assertEqual(matrix.included[-1].case_id, "license_plate_cpu")

    def test_pipeline_filter_and_skip_pipelines(self) -> None:
        filters = MatrixFilters(
            pipelines=["object-detection", "smart-parking"],
            skip_pipelines=["Smart-Parking"],
        )
        reasons = _reasons(build_matrix(PIPELINES, DEVICES, {}, filters))
        self.assertEqual(reasons[("lpr", ALL_VARIANTS)], R.PIPELINE_FILTER)
        self.assertEqual(reasons[("smart-parking", ALL_VARIANTS)], R.SKIP_PIPELINES)

    def test_known_pipeline_ids_unaffected_by_filters(self) -> None:
        """A pipeline removed via pipelines/skip_pipelines must still be
        reported as "known", so callers validating user-supplied filter
        ids (e.g. conftest._validate_filter_ids) don't mistake a
        deliberate skip for an unknown id."""
        filters = MatrixFilters(
            pipelines=["object-detection", "smart-parking"],
            skip_pipelines=["smart-parking"],
        )
        matrix = build_matrix(PIPELINES, DEVICES, {}, filters)
        self.assertEqual(
            matrix.known_pipeline_ids, ["object-detection", "smart-parking", "lpr"]
        )
        # Both are fully filtered out of included/excluded-as-runnable...
        self.assertEqual({c.pipeline_id for c in matrix.included}, {"object-detection"})
        # ...yet both remain valid, discoverable ids.
        self.assertIn("smart-parking", matrix.known_pipeline_ids)
        self.assertIn("lpr", matrix.known_pipeline_ids)
        # The malformed entry (empty id) must never be considered known.
        self.assertNotIn("", matrix.known_pipeline_ids)

    def test_skip_variants_and_variant_filter(self) -> None:
        devices = DEVICES + [{"device_family": "NPU"}]
        filters = MatrixFilters(variants=["cpu", "npu"], skip_variants=["npu"])
        matrix = build_matrix(PIPELINES, devices, {}, filters)
        reasons = _reasons(matrix)
        self.assertEqual(reasons[("object-detection", "NPU")], R.SKIP_VARIANTS)
        self.assertEqual(reasons[("object-detection", "GPU")], R.VARIANT_FILTER)
        # All-families-allowed semantics: GPU_NPU needs gpu too.
        self.assertEqual(reasons[("object-detection", "GPU_NPU")], R.VARIANT_FILTER)

    def test_combined_variant_needs_every_family(self) -> None:
        devices = DEVICES + [{"device_family": "NPU"}]
        filters = MatrixFilters(variants=["gpu", "npu"])
        matrix = build_matrix(PIPELINES, devices, {}, filters)
        self.assertIn(
            ("object-detection", "GPU_NPU"),
            [(c.pipeline_id, c.device_family) for c in matrix.included],
        )

    def test_missing_models_reported_only_for_included(self) -> None:
        missing = {"lpr": {"LPR Net", "A"}, "smart-parking": {"B"}}
        filters = MatrixFilters(skip_pipelines=["smart-parking"])
        matrix = build_matrix(PIPELINES, DEVICES, missing, filters)
        # Missing-model pipelines stay included; pytest wraps them with skip.
        self.assertIn("lpr", [c.pipeline_id for c in matrix.included])
        self.assertEqual(matrix.missing_models, {"lpr": ["A", "LPR Net"]})

    def test_rows_cross_product(self) -> None:
        filters = MatrixFilters(pipelines=["smart-parking"], stream_counts=[1, 5])
        matrix = build_matrix(PIPELINES, DEVICES, {}, filters)
        self.assertEqual(
            [(c.case_id, n) for c, n in matrix.rows()],
            [("smart_parking_cpu", 1), ("smart_parking_cpu", 5)],
        )

    def test_no_devices_excludes_everything(self) -> None:
        matrix = build_matrix(PIPELINES, [], {}, MatrixFilters())
        self.assertEqual(matrix.included, [])
        self.assertTrue(matrix.excluded)


if __name__ == "__main__":
    unittest.main()
