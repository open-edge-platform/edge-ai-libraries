# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Build the launch strings of an exported app from a variant graph.

The exported app mounts its bundled assets at the same container paths ViPPET
uses (``/models`` and ``/videos``), so the launch strings ViPPET resolves run
unchanged there. Outputs go to ``/output``, a directory of the app.

Each app offers three ways to run the pipeline, selected when an instance is
started:

* ``fakesink`` - no video output, the input loops until the instance is stopped.
* ``file`` - the annotated video is written to ``/output/{name}.mp4``; the
  input is played once.
* ``rtsp`` - the annotated video is published to the app's media server at
  ``rtsp://mediamtx:8554/{name}``; the input loops.

``{name}`` is the instance name, filled in by the app's ``run.sh``. Every
``gvametapublish`` element writes JSON Lines to ``/output/{name}.jsonl``.
"""

import copy
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from graph import CAMERA_SOURCE_TYPES, OUTPUT_PLACEHOLDER, Graph
from models import SupportedModelsManager
from video_encoder import (
    ENCODER_CONFIG,
    ENCODER_DEVICE_CPU,
    ENCODER_DEVICE_GPU,
    STREAMING_ENCODER_CONFIG,
)
from video_decoder import split_device_target

logger = logging.getLogger("app_export.pipelines")

SINK_FAKESINK = "fakesink"
SINK_FILE = "file"
SINK_RTSP = "rtsp"
SINKS: tuple[str, ...] = (SINK_FAKESINK, SINK_FILE, SINK_RTSP)

# Filled in by the app's run.sh with the instance name.
NAME_PLACEHOLDER = "{name}"

MODELS_ROOT = "/models"
VIDEOS_ROOT = "/videos"
OUTPUT_ROOT = "/output"

# Host name of the media server service in the app's compose file.
RTSP_SERVER = "rtsp://mediamtx:8554"

# Catalog names of the models an app may use. Pallet Defect Detection is the
# only pipeline verified to run as an app so far (ITEP-97461).
SUPPORTED_MODELS: frozenset[str] = frozenset({"pallet_defect_detection"})

# Encoders that every Intel GPU with VA-API provides and that ship in the
# DL Streamer image, so the app does not depend on the encoders available
# where ViPPET runs (e.g. the low-power vah264lpenc).
_PORTABLE_ENCODERS: dict[str, str] = {
    ENCODER_DEVICE_GPU: "vah264enc",
    ENCODER_DEVICE_CPU: "openh264enc",
}

_INFERENCE_TYPES = frozenset({"gvadetect", "gvaclassify", "gvainference"})
_EXPORTABLE_DEVICES = frozenset({"CPU", "GPU", "NPU"})

# gvametapublish properties that only apply to a message broker. The app has no
# broker, so they are dropped when a publisher is pointed at a file.
_BROKER_PROPERTIES = frozenset(
    {
        "address",
        "topic",
        "mqtt-client-id",
        "mqtt-config",
        "max-connect-attempts",
        "max-reconnect-interval",
    }
)
_UNSUPPORTED_TYPES = frozenset({"gvagenai", "gvapython", "gvaaudiodetect"})

# key=/absolute/path in a launch string.
_PATH_PROPERTY = re.compile(r"(?<![\w-])([\w-]+)=(/[^\s!]+)")


@dataclass(frozen=True)
class AppPipelines:
    """
    Launch strings of an exported app and the files they read.

    Attributes:
        launch_strings: Launch string per sink (see ``SINKS``), with
            ``NAME_PLACEHOLDER`` where the instance name goes.
        devices: Inference devices the pipeline uses ("CPU", "GPU", "NPU"),
            without device indexes.
        model_files: Absolute container paths under ``MODELS_ROOT`` referenced
            by ``model`` properties.
        other_model_files: Absolute container paths under ``MODELS_ROOT``
            referenced by any other property (``model-proc``, labels).
        video_files: Absolute container paths under ``VIDEOS_ROOT`` read by the
            pipeline (the input video and its looping TS companion).
    """

    launch_strings: dict[str, str]
    devices: list[str]
    model_files: list[str] = field(default_factory=list)
    other_model_files: list[str] = field(default_factory=list)
    video_files: list[str] = field(default_factory=list)


def check_exportable(graph: Graph) -> None:
    """
    Check that a variant graph can run as an exported app.

    An app runs one input video file through stock DL Streamer elements with
    models from ``SUPPORTED_MODELS``, and has no outputs other than the main
    ``fakesink`` (which the app replaces) and ``gvametapublish``.

    Args:
        graph: Advanced graph of the variant, as stored by ViPPET (model display
            names, video file names).

    Raises:
        ValueError: With a user-facing reason when the variant cannot be
            exported.
    """
    sources = [node for node in graph.nodes if node.type.endswith("src")]
    if len(sources) != 1 or sources[0].type != "filesrc":
        found = ", ".join(sorted({node.type for node in sources})) or "none"
        if any(node.type in CAMERA_SOURCE_TYPES for node in sources):
            found += " (camera)"
        raise ValueError(
            "Export as app needs exactly one video file source (filesrc); "
            f"this variant has: {found}."
        )

    unsupported = sorted(
        {
            node.type
            for node in graph.nodes
            if node.type in _UNSUPPORTED_TYPES or node.type.endswith("_py")
        }
    )
    if unsupported:
        raise ValueError(
            "Export as app does not support these elements yet: "
            f"{', '.join(unsupported)}."
        )

    sinks = sorted(
        {
            node.type
            for node in graph.nodes
            if node.type.endswith("sink") and node.type != "fakesink"
        }
    )
    if sinks:
        raise ValueError(
            "Export as app writes its own outputs and does not support pipelines "
            f"with these sinks: {', '.join(sinks)}."
        )

    model_names: list[str] = []
    for node in graph.nodes:
        if node.type not in _INFERENCE_TYPES:
            continue
        device = (node.data.get("device") or "").strip()
        family, gpu_index = split_device_target(device)
        # Composite devices (AUTO, HETERO, MULTI) are not mapped to the app's
        # device mounts, and the launch strings of other GPUs name
        # host-specific render nodes.
        if device and (
            family not in _EXPORTABLE_DEVICES
            or (family == ENCODER_DEVICE_GPU and gpu_index != 0)
        ):
            raise ValueError(
                "Export as app supports the devices CPU, GPU (the first GPU only) "
                f"and NPU; this variant uses {device}. Change the device, save, "
                "then export again."
            )
        display_name = (node.data.get("model") or "").strip()
        if not display_name:
            continue
        model = SupportedModelsManager().find_installed_model_by_display_name(
            display_name
        )
        if model is None:
            raise ValueError(
                f"Model '{display_name}' is not installed. Install it on the Models "
                "page, then export again."
            )
        model_names.append(model.name)

    if not model_names or not set(model_names) <= SUPPORTED_MODELS:
        raise ValueError(
            "Export as app currently supports Pallet Defect Detection pipelines "
            "only (model 'Pallet Defect Detection')."
        )


def build_app_pipelines(graph: Graph) -> AppPipelines:
    """
    Build the launch strings of an exported app from a variant graph.

    Applies the same graph changes as a ViPPET performance test (model instance
    ids, decoder selection, looping, main output), then substitutes the app's
    output locations and a portable encoder.

    Args:
        graph: Advanced graph of the variant, as stored by ViPPET.

    Returns:
        AppPipelines: Launch strings per sink and the files they read.

    Raises:
        ValueError: If the variant cannot be exported (see
            ``check_exportable``), or a launch string references a file outside
            the bundled models and videos.
    """
    check_exportable(graph)

    base = graph.unify_model_instance_ids()
    base.validate_inference_devices_share_va_display()

    if base.has_decodebin3():
        base = base.apply_decodebin3_replacement(
            base.determine_input_codec(), base.get_target_device()
        )

    encoder_device = base.get_recommended_encoder_device()

    launch_strings: dict[str, str] = {}
    for sink in SINKS:
        if sink == SINK_FILE:
            variant_graph = copy.deepcopy(base)
        else:
            variant_graph = base.apply_looping_modifications()

        if sink != SINK_FAKESINK:
            variant_graph = variant_graph.prepare_main_output_placeholder()

        _set_metadata_outputs(variant_graph)
        variant_graph = variant_graph.strip_watermark_if_all_sinks_are_fake()

        launch_string = variant_graph.to_pipeline_description()
        if sink != SINK_FAKESINK:
            if OUTPUT_PLACEHOLDER not in launch_string:
                raise ValueError(
                    "Export as app needs the pipeline to end in "
                    "'fakesink name=default_output_sink'."
                )
            launch_string = launch_string.replace(
                OUTPUT_PLACEHOLDER, _output_subpipeline(sink, encoder_device)
            )
        launch_strings[sink] = launch_string

    model_files, other_model_files, video_files = _referenced_files(
        launch_strings.values()
    )

    return AppPipelines(
        launch_strings=launch_strings,
        devices=_devices(base),
        model_files=model_files,
        other_model_files=other_model_files,
        video_files=video_files,
    )


def _set_metadata_outputs(graph: Graph) -> None:
    """
    Point every gvametapublish element of the graph at a JSON Lines file under /output.

    Publishers configured for a message broker are switched to the file as well,
    because the app does not run a broker.
    """
    publishers = [node for node in graph.nodes if node.type == "gvametapublish"]
    for node in publishers:
        suffix = "" if len(publishers) == 1 else f"-{node.id}"
        for prop in _BROKER_PROPERTIES:
            node.data.pop(prop, None)
        node.data["method"] = "file"
        node.data["file-format"] = "json-lines"
        node.data["file-path"] = f"{OUTPUT_ROOT}/{NAME_PLACEHOLDER}{suffix}.jsonl"


def _output_subpipeline(sink: str, encoder_device: str) -> str:
    """Return the encoder and writer chain that replaces the main fakesink."""
    if sink == SINK_FILE:
        encoder = _encoder(ENCODER_CONFIG, encoder_device)
        return (
            f"{encoder} ! h264parse ! mp4mux ! "
            f"filesink location={OUTPUT_ROOT}/{NAME_PLACEHOLDER}.mp4"
        )
    encoder = _encoder(STREAMING_ENCODER_CONFIG, encoder_device)
    return (
        f"{encoder} ! h264parse ! rtspclientsink protocols=tcp "
        f"location={RTSP_SERVER}/{NAME_PLACEHOLDER}"
    )


def _encoder(config: dict[str, list[tuple[str, str]]], encoder_device: str) -> str:
    """Return ViPPET's encoder settings for the portable encoder of a device."""
    element = _PORTABLE_ENCODERS[encoder_device]
    for search, encoder in config[encoder_device]:
        if search == element:
            return encoder
    raise ValueError(f"No {element} settings for encoder device {encoder_device}.")


def _devices(graph: Graph) -> list[str]:
    """Return the inference devices of the graph without indexes, e.g. ["GPU", "NPU"]."""
    devices = {
        node.data["device"].split(".")[0].upper()
        for node in graph.nodes
        if node.type.startswith("gva") and node.data.get("device")
    }
    return sorted(devices or {"CPU"})


def _referenced_files(
    launch_strings: Iterable[str],
) -> tuple[list[str], list[str], list[str]]:
    """
    Sort the absolute paths of the launch strings into model and video files.

    Raises:
        ValueError: If a path is neither an app output nor under the models or
            videos root.
    """
    model_files: set[str] = set()
    other_model_files: set[str] = set()
    video_files: set[str] = set()
    for launch_string in launch_strings:
        for key, path in _PATH_PROPERTY.findall(launch_string):
            if path.startswith(f"{OUTPUT_ROOT}/"):
                continue
            if ".." in path.split("/"):
                raise ValueError(f"Export as app does not accept '{key}={path}'.")
            if path.startswith(f"{MODELS_ROOT}/"):
                (model_files if key == "model" else other_model_files).add(path)
            elif path.startswith(f"{VIDEOS_ROOT}/") and key == "location":
                video_files.add(path)
            else:
                raise ValueError(
                    "Export as app can only bundle models and input videos; the "
                    f"pipeline also reads '{key}={path}'."
                )
    return sorted(model_files), sorted(other_model_files), sorted(video_files)
