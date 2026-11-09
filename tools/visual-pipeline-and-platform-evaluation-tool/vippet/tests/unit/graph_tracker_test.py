# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import unittest

from graph import Graph


class TestDeepSortPropertySerialization(unittest.TestCase):
    def test_decoded_and_legacy_configs_export_with_one_layer_of_quotes(self):
        decoded = "max_age=60,object_class=person"
        for value in (decoded, f'"{decoded}"', f"'{decoded}'"):
            with self.subTest(value=value):
                graph = Graph.from_dict(
                    {
                        "nodes": [
                            {
                                "id": "0",
                                "type": "gvatrack",
                                "data": {
                                    "tracking-type": "deep-sort",
                                    "deepsort-trck-cfg": value,
                                },
                            }
                        ],
                        "edges": [],
                    }
                )

                exported = graph.to_pipeline_description()

                self.assertEqual(
                    exported,
                    "gvatrack tracking-type=deep-sort "
                    'deepsort-trck-cfg="max_age=60,object_class=person"',
                )
                imported = Graph.from_pipeline_description(exported)
                self.assertEqual(len(imported.nodes), 1)
                self.assertEqual(imported.nodes[0].type, "gvatrack")
                self.assertEqual(imported.nodes[0].data["deepsort-trck-cfg"], decoded)
                self.assertEqual(imported.to_pipeline_description(), exported)
                self.assertEqual(graph.nodes[0].data["deepsort-trck-cfg"], value)

    def test_other_properties_keep_literal_surrounding_quotes(self):
        graph = Graph.from_dict(
            {
                "nodes": [
                    {
                        "id": "0",
                        "type": "gvatrack",
                        "data": {"name": '"literal quotes"'},
                    },
                    {
                        "id": "1",
                        "type": "identity",
                        "data": {"deepsort-trck-cfg": '"literal quotes"'},
                    },
                ],
                "edges": [{"id": "0", "source": "0", "target": "1"}],
            }
        )

        self.assertEqual(
            Graph.from_pipeline_description(graph.to_pipeline_description()).to_dict(),
            graph.to_dict(),
        )
