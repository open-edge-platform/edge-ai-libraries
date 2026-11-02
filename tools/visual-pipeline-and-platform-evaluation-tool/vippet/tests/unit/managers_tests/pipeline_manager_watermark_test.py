# SPDX-License-Identifier: Apache-2.0
"""Integration tests for automatic gvawatermark handling in PipelineManager.

These tests exercise the path inside
:meth:`PipelineManager.build_pipeline_command` that calls
:meth:`Graph.strip_watermark_if_all_sinks_are_fake` once per stream. They
verify that the produced pipeline command string contains (or does not
contain) ``gvawatermark`` depending on the requested output mode and on the
sink layout of the pipeline graph.
"""

import os
import unittest
from unittest.mock import MagicMock, patch

from graph import Graph
from internal_types import (
    InternalExecutionConfig,
    InternalMetadataMode,
    InternalOutputMode,
    InternalPipelinePerformanceSpec,
)
from managers.pipeline_manager import PipelineManager


# Re-use the same VideosManager stub strategy as pipeline_manager_test.py.
# build_pipeline_command goes through graph.to_pipeline_description, which
# instantiates VideosManager. The real singleton downloads default
# recordings and converts them to .ts on first use; both are unwanted in
# unit tests.
_videos_manager_patcher = None


def _mock_get_video_filename(path: str) -> str:
    return os.path.basename(path)


def _mock_get_video_path(filename: str) -> str:
    return os.path.join("/tmp", filename)


def setUpModule() -> None:
    """Install the VideosManager patch before any test runs."""
    global _videos_manager_patcher
    mock_instance = MagicMock()
    mock_instance.get_video_filename.side_effect = _mock_get_video_filename
    mock_instance.get_video_path.side_effect = _mock_get_video_path
    mock_instance.get_video.return_value = None
    mock_instance.get_ts_path.side_effect = lambda p: p
    mock_instance.ensure_ts_file.side_effect = lambda p: p

    _videos_manager_patcher = patch("graph.VideosManager", return_value=mock_instance)
    _videos_manager_patcher.start()


def tearDownModule() -> None:
    """Remove the VideosManager patch after the module's tests finish."""
    global _videos_manager_patcher
    if _videos_manager_patcher is not None:
        _videos_manager_patcher.stop()
        _videos_manager_patcher = None


def _watermark_graph_single_fakesink() -> Graph:
    """videotestsrc -> gvawatermark -> fakesink(default_output_sink)."""
    return Graph.from_dict(
        {
            "nodes": [
                {"id": "0", "type": "videotestsrc", "data": {}},
                {"id": "1", "type": "gvawatermark", "data": {}},
                {
                    "id": "2",
                    "type": "fakesink",
                    "data": {"name": "default_output_sink"},
                },
            ],
            "edges": [
                {"id": "0", "source": "0", "target": "1"},
                {"id": "1", "source": "1", "target": "2"},
            ],
        }
    )


def _watermark_graph_with_intermediate_filesink() -> Graph:
    """NVR-style graph: a tee with a non-fakesink intermediate recorder and
    a main fakesink, both fed through gvawatermark.

    videotestsrc -> tee -> queue -> gvawatermark -> filesink (intermediate)
                       \\-> queue -> gvawatermark -> fakesink(default_output_sink)
    """
    return Graph.from_dict(
        {
            "nodes": [
                {"id": "0", "type": "videotestsrc", "data": {}},
                {"id": "1", "type": "tee", "data": {}},
                {"id": "2", "type": "queue", "data": {}},
                {"id": "3", "type": "gvawatermark", "data": {}},
                {
                    "id": "4",
                    "type": "filesink",
                    "data": {"location": "/tmp/intermediate.mp4"},
                },
                {"id": "5", "type": "queue", "data": {}},
                {"id": "6", "type": "gvawatermark", "data": {}},
                {
                    "id": "7",
                    "type": "fakesink",
                    "data": {"name": "default_output_sink"},
                },
            ],
            "edges": [
                {"id": "0", "source": "0", "target": "1"},
                {"id": "1", "source": "1", "target": "2"},
                {"id": "2", "source": "2", "target": "3"},
                {"id": "3", "source": "3", "target": "4"},
                {"id": "4", "source": "1", "target": "5"},
                {"id": "5", "source": "5", "target": "6"},
                {"id": "6", "source": "6", "target": "7"},
            ],
        }
    )


def _execution_config(output_mode: InternalOutputMode) -> InternalExecutionConfig:
    return InternalExecutionConfig(
        output_mode=output_mode,
        max_runtime=0,
        metadata_mode=InternalMetadataMode.DISABLED,
    )


def _performance_spec(graph: Graph) -> list[InternalPipelinePerformanceSpec]:
    return [
        InternalPipelinePerformanceSpec(
            pipeline_id="/pipelines/wm-test/variants/cpu",
            pipeline_name="wm-test",
            pipeline_graph=graph,
            streams=1,
        )
    ]


class TestWatermarkHandlingInBuildPipelineCommand(unittest.TestCase):
    """Verify that gvawatermark stripping is wired correctly per output mode."""

    def setUp(self) -> None:
        PipelineManager._instance = None
        self.job_id = "wm-test-job"

    def test_output_disabled_strips_watermark_when_only_fakesink(self) -> None:
        """With output_mode=disabled and a fakesink-only graph the watermark
        must be removed from the generated pipeline command."""
        manager = PipelineManager()
        manager.pipelines = []

        pipeline_cmd = manager.build_pipeline_command(
            _performance_spec(_watermark_graph_single_fakesink()),
            _execution_config(InternalOutputMode.DISABLED),
            self.job_id,
        )

        self.assertNotIn("gvawatermark", pipeline_cmd.command)
        # The fakesink terminal is preserved because output_mode=disabled
        # does not install the encoder/file subpipeline.
        self.assertIn("fakesink", pipeline_cmd.command)

    def test_output_file_preserves_watermark(self) -> None:
        """With output_mode=file the main fakesink is converted to an
        OUTPUT_PLACEHOLDER and replaced by the encoder subpipeline, so the
        watermark must stay (the user will see it in the produced file)."""
        manager = PipelineManager()
        manager.pipelines = []

        pipeline_cmd = manager.build_pipeline_command(
            _performance_spec(_watermark_graph_single_fakesink()),
            _execution_config(InternalOutputMode.FILE),
            self.job_id,
        )

        self.assertIn("gvawatermark", pipeline_cmd.command)
        # The placeholder fakesink is replaced by a real filesink.
        self.assertIn("filesink", pipeline_cmd.command)

    def test_output_live_stream_preserves_watermark(self) -> None:
        """With output_mode=live_stream the watermark must stay so the live
        viewer sees the overlay."""
        manager = PipelineManager()
        manager.pipelines = []

        pipeline_cmd = manager.build_pipeline_command(
            _performance_spec(_watermark_graph_single_fakesink()),
            _execution_config(InternalOutputMode.LIVE_STREAM),
            self.job_id,
        )

        self.assertIn("gvawatermark", pipeline_cmd.command)
        # rtspclientsink is used for live streaming output.
        self.assertIn("rtspclientsink", pipeline_cmd.command)

    def test_output_disabled_preserves_watermark_when_intermediate_non_fakesink(
        self,
    ) -> None:
        """When the graph has at least one non-fakesink terminal (e.g. an
        intermediate filesink/splitmuxsink in NVR-style pipelines) the
        watermark must be kept even with output_mode=disabled, because the
        recorded file is itself a visible output for the user."""
        manager = PipelineManager()
        manager.pipelines = []

        pipeline_cmd = manager.build_pipeline_command(
            _performance_spec(_watermark_graph_with_intermediate_filesink()),
            _execution_config(InternalOutputMode.DISABLED),
            self.job_id,
        )

        self.assertIn("gvawatermark", pipeline_cmd.command)
        self.assertIn("filesink", pipeline_cmd.command)


if __name__ == "__main__":
    unittest.main()
