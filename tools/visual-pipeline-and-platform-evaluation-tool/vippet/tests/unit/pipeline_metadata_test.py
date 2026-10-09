# SPDX-License-Identifier: Apache-2.0

"""Unit tests for metadata publication coverage in built-in pipelines."""

import unittest
from pathlib import Path

import yaml


PIPELINES_DIR = Path(__file__).parents[2] / "pipelines"
CONVERTED_INFERENCE_ELEMENTS = ("gvadetect", "gvaclassify", "gvainference")
INFERENCE_ELEMENTS = (*CONVERTED_INFERENCE_ELEMENTS, "gvagenai")


class TestPipelineMetadataCoverage(unittest.TestCase):
    """Ensure inference variants expose metadata for functional validation."""

    def test_inference_variants_can_publish_metadata(self):
        """Require converters and publishers appropriate to each inference type.

        Functional inference validation reads what ``gvametapublish`` writes, so a
        new inference pipeline without a correctly ordered metadata tail would be
        silently unverifiable.
        """
        failures = []

        for pipeline_path in sorted(PIPELINES_DIR.rglob("*.yaml")):
            with pipeline_path.open(encoding="utf-8") as pipeline_file:
                pipeline = yaml.safe_load(pipeline_file)

            for variant in pipeline.get("variants", []):
                description = variant.get("pipeline_description", "")
                elements = [
                    element.split(maxsplit=1)[0]
                    for element in description.split("!")
                    if element.strip()
                ]
                element_types = set(elements)
                if not element_types.intersection(INFERENCE_ELEMENTS):
                    continue

                problems = []
                needs_converter = bool(
                    element_types.intersection(CONVERTED_INFERENCE_ELEMENTS)
                )
                if needs_converter and "gvametaconvert" not in element_types:
                    problems.append("missing gvametaconvert")
                if "gvametapublish" not in element_types:
                    problems.append("missing gvametapublish")
                if not problems:
                    publish_at = elements.index("gvametapublish")
                    last_inference_at = max(
                        index
                        for index, element in enumerate(elements)
                        if element in INFERENCE_ELEMENTS
                    )
                    if publish_at < last_inference_at:
                        problems.append("gvametapublish precedes an inference element")
                    if (
                        needs_converter
                        and elements.index("gvametaconvert") > publish_at
                    ):
                        problems.append("gvametaconvert follows gvametapublish")

                if problems:
                    relative_path = pipeline_path.relative_to(PIPELINES_DIR)
                    failures.append(
                        f"{relative_path}:{variant['name']} {', '.join(problems)}"
                    )

        self.assertEqual([], failures, "\n" + "\n".join(failures))


if __name__ == "__main__":
    unittest.main()
