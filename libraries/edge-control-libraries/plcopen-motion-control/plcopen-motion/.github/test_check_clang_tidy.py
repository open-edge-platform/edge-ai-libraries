# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation

import pathlib
import subprocess
import sys
import tempfile
import unittest


CHECKER = pathlib.Path(__file__).with_name("check-clang-tidy.py").resolve()


class CheckClangTidyTest(unittest.TestCase):
    def run_checker(self, report):
        with tempfile.TemporaryDirectory() as directory:
            if report is not None:
                pathlib.Path(directory, "output.yaml").write_text(report)
            return subprocess.run(
                [sys.executable, str(CHECKER)],
                cwd=directory,
                capture_output=True,
                text=True,
                check=False,
            )

    def test_empty_report_passes(self):
        result = self.run_checker("")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Fix count: 0", result.stdout)

    def test_empty_diagnostics_pass(self):
        result = self.run_checker("Diagnostics: []\n")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_ruckig_diagnostics_remain_filtered(self):
        result = self.run_checker(
            "Diagnostics:\n"
            "  - DiagnosticMessage:\n"
            "      FilePath: /usr/local/include/ruckig/ruckig.hpp\n"
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_repository_diagnostics_fail(self):
        result = self.run_checker(
            "Diagnostics:\n"
            "  - DiagnosticMessage:\n"
            "      FilePath: /usr/local/include/ruckig/ruckig.hpp\n"
            "  - DiagnosticMessage:\n"
            "      FilePath: library/fb/common/src/axis.cpp\n"
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("Fix count: 1", result.stdout)

    def test_missing_report_fails(self):
        self.assertNotEqual(self.run_checker(None).returncode, 0)

    def test_malformed_report_fails(self):
        for report in ("Diagnostics: [", "Unexpected: []\n", "Diagnostics: 1\n"):
            with self.subTest(report=report):
                self.assertNotEqual(self.run_checker(report).returncode, 0)


if __name__ == "__main__":
    unittest.main()
