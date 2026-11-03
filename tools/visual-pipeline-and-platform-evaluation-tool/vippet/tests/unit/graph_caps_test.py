# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import unittest

from graph import Graph


class TestCapsPropertyRoundTrip(unittest.TestCase):
    def test_caps_property_preserves_serialized_value(self):
        for caps in (
            '"video/x-raw, format=RGB"',
            "'video/x-raw, format=RGB'",
            '"video/x-raw,format=RGB,width=640,height=480"',
            '"video/x-raw(memory:VAMemory)"',
            r"\"video/x-raw(memory:VAMemory)\"",
            "video/x-raw",
        ):
            with self.subTest(caps=caps):
                pipeline = f"videotestsrc ! capsfilter caps={caps} ! fakesink"
                graph = Graph.from_pipeline_description(pipeline)

                self.assertEqual(
                    [node.type for node in graph.nodes],
                    ["videotestsrc", "capsfilter", "fakesink"],
                )
                self.assertEqual(graph.nodes[1].data, {"caps": caps})

                exported = graph.to_pipeline_description()
                self.assertEqual(exported, pipeline)
                self.assertEqual(
                    Graph.from_pipeline_description(exported).to_dict(),
                    graph.to_dict(),
                )

    def test_other_properties_are_still_unquoted(self):
        graph = Graph.from_pipeline_description(
            'identity name="filter name" ! fakesink'
        )

        self.assertEqual(graph.nodes[0].data["name"], "filter name")
        self.assertEqual(
            graph.to_pipeline_description(),
            'identity name="filter name" ! fakesink',
        )
