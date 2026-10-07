# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for pipeline-case pytest parameter wrapping."""

import unittest

from helpers.pipeline_case_helpers import PipelineCase, wrap_cases_for_pytest


class TestWrapCasesForPytest(unittest.TestCase):
    def setUp(self) -> None:
        self.case = PipelineCase(
            case_id="sample_cpu",
            pipeline_id="pipeline-1",
            variant_id="variant-1",
            device_family="CPU",
            pipeline_name="Sample",
        )
        self.missing_models = {"pipeline-1": {"Missing Model"}}

    def test_skip_missing_models_skips_case_with_reason(self) -> None:
        params, ids = wrap_cases_for_pytest(
            [self.case], self.missing_models, skip_missing_models=True
        )

        self.assertEqual(ids, ["sample_cpu"])
        self.assertEqual(params[0].values, (self.case,))
        self.assertTrue(any(mark.name == "skip" for mark in params[0].marks))
        self.assertIn("Missing Model", str(params[0].marks[0].kwargs["reason"]))

    def test_not_skipping_missing_models_schedules_case(self) -> None:
        params, ids = wrap_cases_for_pytest(
            [self.case], self.missing_models, skip_missing_models=False
        )

        self.assertEqual(ids, ["sample_cpu"])
        self.assertIs(params[0], self.case)