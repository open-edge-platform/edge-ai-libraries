import copy
import logging
import os
import re
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from models import SupportedModelsManager
from resources import (
    get_labels_manager,
    get_public_model_proc_manager,
    get_scripts_manager,
)
from utils import slugify_text
from video_decoder import VideoDecoder
from videos import VideosManager
from images import ImagesManager

# Internal constant used as a placeholder type for the main output sink in the graph.
OUTPUT_PLACEHOLDER: str = "{OUTPUT_PLACEHOLDER}"
RTSP_URL_PREFIX = "rtsp://"
USB_DEVICE_PREFIX = "/dev/video"

# Element types whose presence marks a pipeline as metadata-only (no video output).
# Such pipelines are allowed to keep an unnamed fakesink as-is (used for metadata
# delivery) instead of having it converted to OUTPUT_PLACEHOLDER.
METADATA_ONLY_NODE_TYPES: frozenset[str] = frozenset({"gvagenai"})


def graph_is_metadata_only(nodes: list["Node"]) -> bool:
    """Return True if the pipeline produces only metadata (no video output)."""
    return any(node.type in METADATA_ONLY_NODE_TYPES for node in nodes)


logger = logging.getLogger(__name__)
labels_manager = get_labels_manager()
scripts_manager = get_scripts_manager()
model_proc_manager = get_public_model_proc_manager()

# Configuration for Simple View: comma-separated regex patterns for visible elements.
# All elements matching these patterns will be shown in Simple View.
# All other elements (including caps nodes) will be hidden and their edges reconnected.
SIMPLE_VIEW_VISIBLE_ELEMENTS = os.environ.get(
    "SIMPLE_VIEW_VISIBLE_ELEMENTS", "*src,urisourcebin,gva*,*sink,source"
)

# Configuration for Simple View: comma-separated regex patterns for invisible elements.
# Elements matching these patterns will be excluded from Simple View even if they
# match SIMPLE_VIEW_VISIBLE_ELEMENTS. This allows fine-grained control over which
# elements are shown. Evaluation order: VISIBLE first, then INVISIBLE exclusions.
SIMPLE_VIEW_INVISIBLE_ELEMENTS = os.environ.get(
    "SIMPLE_VIEW_INVISIBLE_ELEMENTS",
    "gvafpscounter,gvametapublish,gvametaconvert,gvawatermark",
)

# Default latency (in ms) applied to rtspsrc elements that do not specify it explicitly.
RTSPSRC_DEFAULT_LATENCY_MS: int = int(
    os.environ.get("RTSPSRC_DEFAULT_LATENCY_MS", "100")
)


def _compile_visibility_patterns(pattern_string: str) -> list[re.Pattern]:
    """
    Parse comma-separated wildcard patterns and compile them into regex patterns.

    Args:
        pattern_string: Comma-separated string of wildcard patterns (e.g., "*src,gva*")

    Returns:
        list[re.Pattern]: List of compiled regex patterns

    Examples:
        "*src" becomes regex "^.*src$"
        "gva*" becomes regex "^gva.*$"
    """
    if not pattern_string or not pattern_string.strip():
        return []

    patterns = [
        pattern.strip() for pattern in pattern_string.split(",") if pattern.strip()
    ]
    compiled_patterns = []

    for pattern in patterns:
        # Convert wildcard pattern to regex: * matches any sequence of characters
        regex_pattern = "^" + pattern.replace("*", ".*") + "$"
        compiled_patterns.append(re.compile(regex_pattern))

    return compiled_patterns


# Compile visibility patterns once at module initialization
_COMPILED_VISIBLE_PATTERNS = _compile_visibility_patterns(SIMPLE_VIEW_VISIBLE_ELEMENTS)
_COMPILED_INVISIBLE_PATTERNS = _compile_visibility_patterns(
    SIMPLE_VIEW_INVISIBLE_ELEMENTS
)

# Internal reserved key used to mark special node kinds inside Node.data.
# We cannot extend the public Node schema with a new top-level field, so we
# store this discriminator as a synthetic property that the frontend can treat
# in a special way.
NODE_KIND_KEY = "__node_kind"
NODE_KIND_CAPS = "caps"


# Per-node-type overrides for elements whose model property does not follow
# the default ``model=...`` convention.
#
# Convention: ``node.data`` always stores the model under the key
# ``"model"``, no matter how the GStreamer element spells it on the wire
# (e.g. ``gvagenai`` uses ``model-path=...``). Each spec carries:
#   - ``model_key``: the wire key used when parsing from / emitting to a
#     pipeline string.
#   - ``uses_model_proc``: whether ``model-proc=...`` should be injected
#     after ``model`` when rebuilding the runnable pipeline.
@dataclass(frozen=True)
class NodeModelSpec:
    model_key: str = "model"
    uses_model_proc: bool = True


NODE_MODEL_SPECS: dict[str, NodeModelSpec] = {
    "gvagenai": NodeModelSpec(model_key="model-path", uses_model_proc=False),
}

_DEFAULT_NODE_MODEL_SPEC = NodeModelSpec()


def _model_spec(node_type: str) -> NodeModelSpec:
    """Return the model spec for ``node_type`` (default spec if not listed)."""
    return NODE_MODEL_SPECS.get(node_type, _DEFAULT_NODE_MODEL_SPEC)


class InputKind(str, Enum):
    """Enum for input source types."""

    VIDEO = "video"
    CAMERA = "camera"
    IMAGE_SET = "image_set"


# Default frame rate (numerator/denominator) used in the caps that follow
# the ``multifilesrc`` element when the source is an image set. Image
# sets do not carry a native frame rate, so a fixed cadence is required
# to drive the downstream pipeline. Kept conservative; can be overridden
# in the future by extending the source-node ``data`` payload.
IMAGE_SET_DEFAULT_FRAMERATE = "30/1"

# Internal flag stored in ``Node.data`` to mark a ``multifilesrc`` node
# that originated from an image-set source. Used by the looping
# transformation and codec detection to handle these nodes specially
# without having to reparse the location pattern.
_IMAGE_SET_NODE_FLAG = "__image_set"


def _image_set_decoder_for_extension(extension: str) -> str:
    """
    Return the GStreamer decoder element name that pairs with the given
    canonical image extension. Every extension accepted by the upload
    validator is guaranteed to have a software decoder available in the
    runtime environment.
    """
    table = {
        "jpg": "jpegdec",
        "jpeg": "jpegdec",
        "png": "pngdec",
        "bmp": "avdec_bmp",
        "tif": "avdec_tiff",
        "tiff": "avdec_tiff",
    }
    decoder = table.get(extension.lower())
    if decoder is None:
        # Should never happen - the upload validator already enforces
        # the allow-list. Falling back to ``decodebin3`` keeps the
        # pipeline runnable in case a directory was created out of
        # band.
        return "decodebin3"
    return decoder


# Preferred VA-accelerated decoder for each image extension, in order of
# preference. The first element that is actually available in the
# current GStreamer installation is selected at runtime via
# ``GstInspector``. Image formats without a VA decoder rely on a
# ``vapostproc`` stage to lift the software-decoded frames into VA
# memory; that is handled separately by
# ``Graph._upgrade_image_set_for_va_memory``.
_IMAGE_SET_VA_DECODERS: dict[str, list[str]] = {
    "jpg": ["vajpegdec", "vaapijpegdec", "qsvjpegdec"],
    "jpeg": ["vajpegdec", "vaapijpegdec", "qsvjpegdec"],
    # No VA decoder ships for PNG / BMP / TIFF in stock GStreamer; the
    # ``vapostproc`` fallback path handles these.
    "png": [],
    "bmp": [],
    "tif": [],
    "tiff": [],
}


def _image_set_caps_for_extension(extension: str) -> str:
    """
    Return the caps string that pairs with the chosen image decoder.
    The caps mime type matches the extension (jpg/jpeg -> ``image/jpeg``)
    and pins a fixed frame rate so the downstream chain can negotiate.
    """
    mime_table = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "bmp": "image/bmp",
        "tif": "image/tiff",
        "tiff": "image/tiff",
    }
    mime = mime_table.get(extension.lower(), "image/jpeg")
    return f"{mime},framerate={IMAGE_SET_DEFAULT_FRAMERATE}"


@dataclass
class _Token:
    """
    Internal token representation used when parsing non-caps segments.

    kind:
        TYPE      – Element type token (for example "filesrc", "gvadetect").
        PROPERTY  – Element property in 'key=value' form.
        TEE_END   – Tee branch endpoint in the form 't.' where 't' is tee name.
        SKIP      – Whitespace (filtered out before emitting tokens).
        MISMATCH  – Any unrecognized character sequence (treated as an error).
    """

    kind: str | None
    value: str


@dataclass
class Node:
    """
    Single node in an in-memory pipeline graph.

    Attributes:
        id: Node identifier, unique within a single graph.
        type: Element type, usually a framework-specific element name
            (for example a GStreamer element name or a caps string).
        data: Key/value properties for the element (for example element
            arguments or configuration).

            Reserved keys:
              * "__node_kind" – internal discriminator used to mark special
                node types. When present and equal to "caps", the node
                represents a GStreamer caps string (for example
                "video/x-raw,width=320,height=240") instead of a regular
                element.

            The discriminator is stored inside data instead of being a
            top-level attribute to avoid changing the public API schema.
    """

    id: str
    type: str
    data: dict[str, str]


@dataclass
class Edge:
    id: str
    source: str
    target: str


@dataclass
class Graph:
    nodes: list[Node]
    edges: list[Edge]

    @staticmethod
    def from_dict(data: dict) -> "Graph":
        """
        Create Graph from a plain dictionary (for example deserialized JSON).

        Args:
            data: Dictionary with 'nodes' and 'edges' keys following the Graph schema

        Returns:
            Graph: New Graph instance created from the dictionary

        The dictionary is expected to follow the same structure as produced
        by Graph.to_dict() and exposed via the public API.

        The "__node_kind" discriminator, when present inside node.data, is
        preserved as-is. It is used internally to distinguish caps nodes
        from regular element nodes during round-trip conversions.
        """
        nodes = [
            Node(
                id=node["id"],
                type=node["type"],
                data=node["data"],
            )
            for node in data["nodes"]
        ]
        edges = [
            Edge(id=edge["id"], source=edge["source"], target=edge["target"])
            for edge in data["edges"]
        ]

        return Graph(nodes=nodes, edges=edges)

    def to_dict(self) -> dict[str, list[dict[str, str | dict[str, str]]]]:
        """
        Convert Graph into a plain dictionary (for example for JSON serialization).

        Returns:
            dict: Dictionary representation of the graph with 'nodes' and 'edges' keys

        The resulting structure is compatible with the public API schema.
        Using asdict() here ensures all dataclass fields are serialized consistently.
        """
        return asdict(self)

    @staticmethod
    def from_pipeline_description(pipeline_description: str) -> "Graph":
        """
        Parse a GStreamer-like pipeline description string into a Graph.

        Args:
            pipeline_description: GStreamer pipeline string with elements separated by '!'

        Returns:
            Graph: New Graph instance representing the parsed pipeline

        High-level algorithm:
          1. Split the description by '!' into segments (elements or caps).
          2. For each segment:
             a) First, try to parse it as a caps segment
                (base, key=value, key2=value2, ...).
                - If successful, create a Node with __node_kind="caps" in data.
             b) If not caps, tokenize the segment into TYPE/PROPERTY/TEE_END
                tokens and build regular element nodes.
          3. After parsing all segments, post-process models and video paths.

        Important invariants:
          * Node IDs are assigned sequentially starting from 0 as segments are processed.
          * Edge IDs are sequential and unique across the graph and are stored
            as strings. Their numeric value is derived from the insertion
            order of edges, not from node indices.
          * Caps nodes are created only when the segment uses comma-separated
            properties (at least one comma and all trailing parts are key=value
            with non-empty values).
          * Segments without commas are never treated as caps; they are
            regular elements, regardless of "/" or parentheses in the name.

        Examples treated as caps:
          - "video/x-raw(memory:VAMemory),width=320,height=240"
          - "video/x-raw,width=320,height=240"
          - "video/x-raw(memory:NVMM),format=UYVY,width=2592,height=1944,framerate=28/1"
          - "video/x-raw,format=(string)UYVY,width=(int)2592,height=(int)1944,framerate=(fraction)28/1"

        Examples treated as regular elements:
          - "video/x-raw(memory:NVMM)"
          - "video/x-raw"
          - "weird/no_comma"
        """
        logger.debug(f"Parsing pipeline description: {pipeline_description}")

        nodes: list[Node] = []
        edges: list[Edge] = []

        tee_stack: list[str] = []
        prev_token_kind: str | None = None

        # Split the pipeline into segments by '!' which separates elements/caps
        raw_elements = pipeline_description.split("!")

        # node_id is derived from the position of segments/elements
        node_id = 0
        # edge_id is a monotonically increasing counter across the whole graph
        # and is always serialized as a string.
        edge_id = 0

        for raw_element in raw_elements:
            element = raw_element.strip()
            if not element:
                # Skip empty segments produced by trailing or duplicate '!'
                continue

            # 1) Try to parse the whole segment as a caps string.
            #    If this succeeds, we create a single caps node for this segment.
            caps_parsed = _parse_caps_segment(element)
            if caps_parsed is not None:
                caps_base, caps_props = caps_parsed
                edge_id = _add_caps_node(
                    nodes=nodes,
                    edges=edges,
                    node_id=node_id,
                    caps_base=caps_base,
                    caps_props=caps_props,
                    tee_stack=tee_stack,
                    prev_token_kind=prev_token_kind,
                    edge_id=edge_id,
                )
                prev_token_kind = "CAPS"
                node_id += 1
                continue

            # 2) If caps parsing failed, treat the segment as a regular element
            #    and tokenize it into TYPE/PROPERTY/TEE_END tokens.
            for token in _tokenize(element):
                match token.kind:
                    case "TYPE":
                        edge_id = _add_node(
                            nodes=nodes,
                            edges=edges,
                            node_id=node_id,
                            token=token,
                            prev_token_kind=prev_token_kind,
                            tee_stack=tee_stack,
                            edge_id=edge_id,
                        )
                    case "PROPERTY":
                        _add_property_to_last_node(nodes, token)
                    case "TEE_END":
                        # TEE_END only affects edge source selection in _add_node,
                        # no direct action needed here.
                        pass
                    case "MISMATCH":
                        # We treat any unrecognized token as a hard error to avoid
                        # silently producing incorrect graphs.
                        raise ValueError(
                            f"Unrecognized token in pipeline description: "
                            f"'{token.value}' (element: '{element}')"
                        )
                    # SKIP is filtered in _tokenize and never reaches here.

                prev_token_kind = token.kind

            node_id += 1

        # Post-process models, video paths labels and module paths so stored
        # graphs reference display names / filenames instead of absolute paths.
        _model_path_to_display_name(nodes)
        _input_video_path_to_display_name(nodes)
        _labels_path_to_display_name(nodes)
        _module_path_to_display_name(nodes)

        logger.debug(f"Nodes:\n{nodes}")
        logger.debug(f"Edges:\n{edges}")

        return Graph(nodes, edges)

    def to_pipeline_description(self) -> str:
        """
        Convert the in-memory Graph back into a GStreamer-like pipeline string.

        Returns:
            str: GStreamer pipeline description string

        Raises:
            ValueError: If graph is empty, circular, or contains unsupported model/device combinations

        High-level algorithm:
          1. Validate that the graph is non-empty and acyclic and that all
             models are supported on their target devices.
          2. Map model display names and video filenames back to full paths.
          3. Build an adjacency map (edges_from) and find start nodes.
          4. Starting from each start node, recursively build linear chains
             of elements:
               - For regular elements:
                   "type key1=value1 key2=value2 ..."
               - For caps nodes (__node_kind="caps"):
                   "type,key1=value1,key2=value2,..."
             Chains are joined with " ! " and tee branches rendered using
             the well-known "t." notation.
        """
        if not self.nodes:
            raise ValueError("Empty graph, cannot convert to pipeline description")

        logger.debug("Converting graph to pipeline description")
        logger.debug(f"Nodes:\n{self.nodes}")
        logger.debug(f"Edges:\n{self.edges}")

        # Work on a deep copy of nodes to avoid mutating the original graph.
        nodes = copy.deepcopy(self.nodes)
        _validate_models_supported_on_devices(nodes)
        _model_display_name_to_path(nodes)
        _input_video_name_to_path(nodes)
        _labels_name_to_path(nodes)
        _module_name_to_path(nodes)

        nodes_by_id = {node.id: node for node in nodes}

        # Build adjacency list: from-node-id -> list of target-node-ids
        edges_from: dict[str, list[str]] = defaultdict(list)
        for edge in self.edges:
            edges_from[edge.source].append(edge.target)

        # Collect tee node names for later when writing tee branches.
        tee_names = {
            node.id: node.data["name"]
            for node in nodes
            if node.type == "tee" and "name" in node.data
        }

        target_node_ids = set(edge.target for edge in self.edges)
        start_nodes = set(nodes_by_id.keys()) - target_node_ids

        if not start_nodes:
            raise ValueError(
                "Cannot convert graph to pipeline description: "
                "circular graph detected or no start nodes found"
            )

        result_parts: list[str] = []
        visited: set[str] = set()

        # Process each independent chain in ascending node-id order
        for start_id in sorted(start_nodes):
            if start_id not in visited:
                _build_chain(
                    start_id, nodes_by_id, edges_from, tee_names, visited, result_parts
                )

        pipeline_description = " ".join(result_parts)
        logger.debug(f"Generated pipeline description: {pipeline_description}")

        return pipeline_description

    def apply_looping_modifications(self) -> "Graph":
        """
        Apply modifications to make pipeline suitable for looping playback.

        Changes applied:
        - Replace filesrc with multifilesrc loop=true
        - Change input file extension to .ts in location (ensures TS file exists)
        - Replace demuxers (qtdemux, matroskademux, avidemux, flvdemux) with tsdemux
        - Set default max-size-time and max-files on splitmuxsink if not already configured

        Returns:
            Modified Graph object with looping support

        Raises:
            ValueError: If live sources (v4l2src, rtspsrc) are detected in the pipeline
            ValueError: If TS file cannot be created for any video source

        Note:
            This creates a deep copy of the graph to avoid modifying the original.
            If TS file does not exist, it will be created automatically.
        """
        videos_manager = VideosManager()
        modified_graph = copy.deepcopy(self)

        for node in modified_graph.nodes:
            if node.type in {"v4l2src", "rtspsrc"}:
                raise ValueError(
                    f"Looping playback is not supported for live sources like {node.type}. "
                    f"Please disable looping, remove, or replace the {node.type} element in your pipeline."
                )

            # Image-set sources are already represented as
            # ``multifilesrc`` and do not need a TS companion. Just
            # toggle ``loop`` so the runner can rely on a wallclock
            # timer to terminate the pipeline.
            if node.type == "multifilesrc" and _IMAGE_SET_NODE_FLAG in node.data:
                node.data["loop"] = "true"
                logger.debug(
                    "Enabled looping on image-set multifilesrc (node %s)", node.id
                )
                continue

            # Replace filesrc with multifilesrc loop=true
            if node.type == "filesrc":
                node.type = "multifilesrc"
                node.data["loop"] = "true"

                if "location" in node.data:
                    location = node.data["location"]

                    # Ensure TS file exists before using it
                    ts_path = videos_manager.get_ts_path(location)
                    if ts_path is None:
                        raise ValueError(
                            f"Cannot get TS path for video '{location}'. "
                            f"Ensure the video file exists and has a supported format."
                        )

                    # Verify TS file actually exists on disk
                    if not os.path.isfile(ts_path):
                        # Try to create TS file
                        source_filename = os.path.basename(location)
                        source_path = videos_manager.get_video_path(source_filename)

                        if source_path is None:
                            raise ValueError(
                                f"Cannot find source video '{source_filename}' for TS conversion."
                            )

                        ts_path = videos_manager.ensure_ts_file(source_path)
                        if ts_path is None:
                            raise ValueError(
                                f"Failed to create TS file for video '{source_filename}'."
                            )

                    # Store only the filename, not the full path
                    # _input_video_name_to_path will convert it back to full path later
                    ts_filename = os.path.basename(ts_path)
                    node.data["location"] = ts_filename
                    logger.debug(
                        f"Modified filesrc to multifilesrc with location: {ts_filename}"
                    )

            # Replace demuxers with tsdemux for looping support
            elif node.type in {
                "qtdemux",
                "matroskademux",
                "avidemux",
                "flvdemux",
            }:
                node.type = "tsdemux"
                logger.debug("Replaced demuxer with tsdemux for looping support")

            # Set default max-size-time and max-files on splitmuxsink if not already configured
            elif node.type == "splitmuxsink":
                if not node.data.get("max-size-time"):
                    node.data["max-size-time"] = "10000000000"
                if not node.data.get("max-files"):
                    node.data["max-files"] = "100"

        return modified_graph

    def apply_rtsp_connection_settings(self) -> "Graph":
        """
        Apply connection settings to all rtspsrc nodes in the pipeline.

        Settings applied to each rtspsrc node:
        - user-id / user-pw: credentials looked up from CameraManager by RTSP URL.
        - latency: set to RTSPSRC_DEFAULT_LATENCY_MS if not already explicitly configured.

        If no rtspsrc node is found, the graph is returned unchanged.

        Returns:
            Modified Graph object with connection settings applied to rtspsrc nodes.

        Note:
            This creates a deep copy of the graph to avoid modifying the original.
        """
        from managers.camera_manager import CameraManager
        # TODO: temporary, to avoid circular import. In the near future, this file will be refactored to not depend on managers at all.

        modified_graph = copy.deepcopy(self)

        for node in modified_graph.nodes:
            if node.type != "rtspsrc":
                continue

            location = node.data.get("location")
            if not location:
                continue

            details = CameraManager().get_network_camera_details_by_rtsp_url(location)
            if details is not None:
                if details.username is not None:
                    node.data["user-id"] = details.username
                if details.password is not None:
                    node.data["user-pw"] = details.password

            node.data.setdefault("latency", str(RTSPSRC_DEFAULT_LATENCY_MS))
            logger.debug(f"Applied RTSP connection settings to rtspsrc node {node.id}")

        return modified_graph

    def prepare_main_output_placeholder(self) -> "Graph":
        """
        Convert default fakesink node to a main output placeholder.

        Finds fakesink nodes with name="default_output_sink" and converts them to
        "{OUTPUT_PLACEHOLDER}" type. If no named fakesink is found but there is
        exactly one fakesink in the graph, that fakesink will be used automatically.
        This placeholder will be later replaced with the actual main output
        subpipeline (file output or live stream).

        Returns:
            Graph: New Graph instance with fakesink converted to placeholder

        Raises:
            ValueError: If no fakesink is found in the graph
            ValueError: If multiple fakesinks exist without explicit naming
            ValueError: If multiple fakesinks are named "default_output_sink"

        Note:
            This is used to mark the location where main output (for user viewing)
            should be inserted, distinct from intermediate output sinks that are part
            of the pipeline definition.
        """
        modified_graph = copy.deepcopy(self)
        placeholder_created = False

        # Find all fakesinks with explicit name="default_output_sink"
        named_default_sinks = [
            node
            for node in modified_graph.nodes
            if node.type == "fakesink"
            and node.data.get("name") == "default_output_sink"
        ]

        if len(named_default_sinks) > 1:
            raise ValueError(
                f"Found {len(named_default_sinks)} fakesink nodes with name='default_output_sink'. "
                "Only one fakesink should be named 'default_output_sink'."
            )

        # If exactly one named default sink exists, use it
        if len(named_default_sinks) == 1:
            node = named_default_sinks[0]
            node.data.clear()
            node.type = OUTPUT_PLACEHOLDER
            placeholder_created = True
            logger.debug(f"Converted node {node.id} to OUTPUT_PLACEHOLDER")

        # If no named default sink, check if there's exactly one fakesink in the graph.
        # Skip auto-selection for metadata-only pipelines (no video output needed).
        if not placeholder_created:
            is_metadata_only = graph_is_metadata_only(modified_graph.nodes)

            fakesink_nodes = [
                node for node in modified_graph.nodes if node.type == "fakesink"
            ]

            if len(fakesink_nodes) == 0:
                raise ValueError(
                    "No fakesink found in the graph. "
                    "Please add 'fakesink' or 'fakesink name=default_output_sink' "
                    "at the end of your pipeline to specify where the output should be placed."
                )
            elif is_metadata_only:
                # Keep unnamed fakesink as-is (used for metadata delivery). This condition must
                # precede the single-fakesink condition, to avoid converting to OUTPUT_PLACEHOLDER.
                logger.debug(
                    "Metadata-only pipeline detected. Keeping unnamed fakesink as-is."
                )
            elif len(fakesink_nodes) == 1:
                # Exactly one fakesink in a video pipeline - convert it to OUTPUT_PLACEHOLDER.
                node = fakesink_nodes[0]
                node.data.clear()
                node.type = OUTPUT_PLACEHOLDER
                placeholder_created = True
                logger.debug(f"Converted node {node.id} to OUTPUT_PLACEHOLDER")
            else:
                # Multiple fakesinks - need explicit naming
                raise ValueError(
                    f"Found {len(fakesink_nodes)} fakesink nodes in the graph. "
                    "Please specify which one should be the main output by adding "
                    "'name=default_output_sink' to the desired fakesink element."
                )

        return modified_graph

    def prepare_intermediate_output_sinks(
        self, output_dir: str, stream_index: int
    ) -> "Graph":
        """
        Prepare intermediate output sink nodes with filenames in the given output directory.

        This method handles intermediate output sinks (e.g., video recorder simulation)
        that are part of the pipeline definition. These are distinct from main output sinks
        which replace fakesink elements for user viewing (live stream or file output).

        Filename format: intermediate_stream{streamidx}_{file_name}{_splitmuxsink_pattern}{ext}
        - streamidx: three-digit zero-padded stream index
        - file_name: slugified stem from the original location property
        - _splitmuxsink_pattern: "_%03d" appended only for splitmuxsink nodes with max-files > 0
        - ext: slugified original extension (defaults to ".mp4" when missing)

        Args:
            output_dir: Directory path where intermediate output files will be placed.
            stream_index: Stream index used in filename generation.

        Returns:
            Graph object with updated sink node locations.
        """
        stream_idx_str = f"{stream_index:03d}"

        for node in self.nodes:
            # Check if node is a sink type
            if not node.type.endswith("sink"):
                continue

            # Check if location key exists
            location = node.data.get("location")
            if not location:
                continue

            path = Path(location)
            file_name = slugify_text(Path(path.name).stem)
            ext = path.suffix if path.suffix else ".mp4"
            ext = slugify_text(ext)

            # Add splitmuxsink pattern only for splitmuxsink with max-files > 0
            splitmux_pattern = ""
            if node.type == "splitmuxsink":
                max_files = node.data.get("max-files")
                if max_files is not None:
                    try:
                        if int(max_files) > 0:
                            splitmux_pattern = "_%03d"
                    except (ValueError, TypeError):
                        pass

            filename = f"intermediate_stream{stream_idx_str}_{file_name}{splitmux_pattern}{ext}"
            new_path = str(Path(output_dir) / filename)

            # Update node's location
            node.data["location"] = new_path

            logger.debug(f"Updated sink node {node.id}: {location} -> {new_path}")

        return self

    def unify_all_element_names(
        self, pipeline_index: int, stream_index: int
    ) -> "Graph":
        """
        Unify all element names in the graph to ensure uniqueness across multiple pipelines.

        Args:
            pipeline_index: Index of the pipeline (used in new element name)
            stream_index: Index of the stream (used in new element name)
        """
        modified_graph = copy.deepcopy(self)

        for node in modified_graph.nodes:
            if "name" in node.data:
                old_name = node.data["name"]
                node.data["name"] = f"{old_name}_{pipeline_index}_{stream_index}"
                logger.debug(
                    f"Unified element name in node {node.id}: {old_name} -> {node.data['name']}"
                )

        return modified_graph

    def apply_stream_identifiers(
        self, pipeline_index: int, stream_index: int
    ) -> tuple["Graph", str, str, str]:
        """
        Assign explicit GStreamer element names to the main-branch source and sink.

        The goal is to make every stream individually identifiable in external
        tracers (for example the DLStreamer `latency_tracer`), which reports
        measurements keyed by `source_name` and `sink_name`. Without explicit
        names, GStreamer auto-generates non-deterministic names like
        "filesrc0", "fakesink0", ..., which are impossible to map back to a
        specific stream when several streams run in parallel.

        What this method does:
          1. Finds the main-branch source: the start node (no incoming edges).
             When multiple start nodes exist, the one with the smallest id
             is selected, consistent with `to_pipeline_description` ordering.
          2. Finds the "main sink" — i.e. the terminal element that actually
             represents the user-facing video output for this stream. The
             selection rule, in priority order, mirrors
             `prepare_main_output_placeholder` so that every stream (stream
             0 where the placeholder has already been inserted, AND
             stream_index > 0 where the placeholder step is skipped) picks
             the same semantic element:

               a) The single OUTPUT_PLACEHOLDER node, if present.
               b) The fakesink with `name == "default_output_sink"`, if
                  present (the canonical user-facing output marker).
               c) The single unnamed fakesink in the graph, if that is the
                  only fakesink.
               d) Best-effort fallback: the terminal reached by walking
                  `targets[0]` from the source (first-branch-inline).

             Intermediate recorder sinks on the tee's inline branch (e.g.
             a splitmuxsink used to simulate a DVR) are therefore never
             mistaken for the main sink when the graph carries the
             `default_output_sink` marker on another tee branch.
          3. Sets `name=<source_name>` on the source node and
             `name=<sink_name>` on the resolved main-sink node. Both names
             include `pipeline_index` and `stream_index` so they remain
             unique across all streams of a single run.
          4. Returns the computed `stream_id` (concatenation of source and
             sink names) so the caller can log / track it.

        Special case — OUTPUT_PLACEHOLDER main sink:
            When the main sink is an OUTPUT_PLACEHOLDER, no `name` property
            is written into the graph, because the placeholder is about to
            be replaced by a full output subpipeline (e.g. encoder +
            filesink). The caller is responsible for injecting
            `name=<sink_name>` into the expanded output subpipeline string
            so the sink name still ends up in the final pipeline. The
            computed sink name is returned regardless.

        Args:
            pipeline_index: Index of the pipeline in the current run.
            stream_index: Index of the stream within this pipeline.

        Returns:
            tuple:
                - Graph: New Graph instance with source/sink names applied.
                - str: Assigned source element name.
                - str: Assigned sink element name (to be used either from the
                  graph itself or injected into the output subpipeline).
                - str: `stream_id` (source_name + "__" + sink_name), unique
                  within a single run.

        Raises:
            ValueError: If no source (start) node can be found.
            ValueError: If no main sink can be found.
            ValueError: If more than one OUTPUT_PLACEHOLDER node exists
                (only one user-facing output is supported per stream).
            ValueError: If more than one fakesink is named
                `default_output_sink` (same invariant as
                `prepare_main_output_placeholder`).
        """
        modified_graph = copy.deepcopy(self)

        # Build an adjacency map: node_id -> list of downstream node ids.
        # This mirrors the structure used by `to_pipeline_description`.
        edges_from: dict[str, list[str]] = defaultdict(list)
        for edge in modified_graph.edges:
            edges_from[edge.source].append(edge.target)

        nodes_by_id = {node.id: node for node in modified_graph.nodes}

        # --- Source selection ---

        # Start nodes = nodes with no incoming edges.
        target_node_ids = {edge.target for edge in modified_graph.edges}
        start_node_ids = [
            node.id for node in modified_graph.nodes if node.id not in target_node_ids
        ]

        if not start_node_ids:
            raise ValueError(
                "Cannot apply stream identifiers: no source node found in graph."
            )

        # Pick the first start node in sorted order so the choice is
        # deterministic and consistent with `to_pipeline_description`, which
        # also iterates `sorted(start_nodes)`.
        source_id = sorted(start_node_ids)[0]
        source_node = nodes_by_id[source_id]

        # --- Main sink selection ---
        #
        # The main sink is the user-facing output terminal. We want its
        # GStreamer `name` to match the stream_id so that external tracers
        # (latency_tracer) can correlate their per-frame rows back to a
        # specific stream. Selection priority — intentionally aligned with
        # `prepare_main_output_placeholder`, so every stream (stream 0 with
        # the placeholder already inserted, AND streams 1+ where the
        # placeholder step is skipped) picks the same semantic element:
        #
        #   (a) If the graph contains an OUTPUT_PLACEHOLDER node, that is
        #       the main sink. This is the stream-0 case after
        #       `prepare_main_output_placeholder` has already run.
        #       Intermediate recorder sinks (e.g. a splitmuxsink sitting on
        #       the tee's inline branch) are therefore never selected.
        #
        #   (b) If a fakesink with `name == "default_output_sink"` exists,
        #       that is the main sink. This matches the marker used by
        #       `prepare_main_output_placeholder` and covers streams where
        #       the placeholder step has NOT run (stream_index > 0, or
        #       output_mode=disabled). It also correctly handles graphs
        #       where the user-facing output sits on a non-first tee branch
        #       while an intermediate recorder sink sits on the inline
        #       branch.
        #
        #   (c) If there is exactly one fakesink in the graph, and it has
        #       no explicit name, that fakesink is the main sink (mirrors
        #       the auto-pick rule of `prepare_main_output_placeholder`).
        #
        #   (d) Otherwise, walk the main chain by always following
        #       `targets[0]` from the source (mirroring `_build_chain`'s
        #       first-branch-inline logic) and use the terminal node. This
        #       is the best-effort fallback for pipelines that don't
        #       follow the fakesink convention.
        #
        # In all cases, tee-branch sinks reached via `targets[1:]` are NOT
        # renamed unless they are the selected main sink.
        placeholder_nodes = [
            node for node in modified_graph.nodes if node.type == OUTPUT_PLACEHOLDER
        ]
        if len(placeholder_nodes) > 1:
            raise ValueError(
                f"Cannot apply stream identifiers: found {len(placeholder_nodes)} "
                "OUTPUT_PLACEHOLDER nodes, expected at most one."
            )

        sink_node: Optional[Node] = None

        # (a) OUTPUT_PLACEHOLDER has the highest priority.
        if len(placeholder_nodes) == 1:
            sink_node = placeholder_nodes[0]

        # (b) fakesink named "default_output_sink".
        if sink_node is None:
            named_default_sinks = [
                node
                for node in modified_graph.nodes
                if node.type == "fakesink"
                and node.data.get("name") == "default_output_sink"
            ]
            if len(named_default_sinks) > 1:
                # Same invariant as `prepare_main_output_placeholder`.
                raise ValueError(
                    f"Cannot apply stream identifiers: found "
                    f"{len(named_default_sinks)} fakesink nodes with "
                    f"name='default_output_sink', expected at most one."
                )
            if len(named_default_sinks) == 1:
                sink_node = named_default_sinks[0]

        # (c) Single unnamed fakesink in the graph.
        if sink_node is None:
            fakesink_nodes = [
                node for node in modified_graph.nodes if node.type == "fakesink"
            ]
            if len(fakesink_nodes) == 1:
                sink_node = fakesink_nodes[0]

        # (d) Fallback: walk targets[0] from the source.
        if sink_node is None:
            current_id: str = source_id
            visited: set[str] = set()
            while True:
                if current_id in visited:
                    # Defensive: the graph should be acyclic (validated
                    # elsewhere), but break here to avoid any theoretical
                    # infinite loop.
                    break
                visited.add(current_id)
                targets = edges_from.get(current_id, [])
                if not targets:
                    break
                current_id = targets[0]

            sink_node = nodes_by_id.get(current_id)

        if sink_node is None:
            raise ValueError("Cannot apply stream identifiers: no main sink found.")

        # Deterministic, run-unique names. Prefix disambiguates source vs sink
        # in log output; indices guarantee uniqueness across streams.
        source_name = f"src_p{pipeline_index}_s{stream_index}"
        sink_name = f"sink_p{pipeline_index}_s{stream_index}"

        # Assign the source name. Overwrites any pre-existing `name` so the
        # stream is guaranteed to be identifiable by the tracer.
        source_node.data["name"] = source_name
        logger.debug(
            f"Set source name on node {source_node.id} "
            f"(type={source_node.type}): {source_name}"
        )

        # Assign the sink name only if the terminal is a real element. For
        # OUTPUT_PLACEHOLDER the caller injects the name into the expanded
        # output subpipeline instead.
        if sink_node.type == OUTPUT_PLACEHOLDER:
            logger.debug(
                f"Main sink node {sink_node.id} is OUTPUT_PLACEHOLDER; "
                f"skipping in-graph rename. Sink name '{sink_name}' will be "
                f"injected into the output subpipeline by the caller."
            )
        else:
            sink_node.data["name"] = sink_name
            logger.debug(
                f"Set sink name on node {sink_node.id} "
                f"(type={sink_node.type}): {sink_name}"
            )

        stream_id = f"{source_name}__{sink_name}"
        return modified_graph, source_name, sink_name, stream_id

    def strip_watermark_if_all_sinks_are_fake(self) -> "Graph":
        """
        Remove all gvawatermark nodes if every sink in the graph is a fakesink.

        If the graph contains at least one OUTPUT_PLACEHOLDER node, it means
        non-fakesink outputs will be added later, so the graph is returned
        unchanged.

        When all sink nodes (nodes whose type ends with "sink") are fakesink,
        gvawatermark elements serve no purpose because there is no real video
        output to render overlays on. Removing them avoids unnecessary
        processing overhead.

        For each removed gvawatermark node, incoming and outgoing edges are
        reconnected so that the predecessor connects directly to the successor.

        Returns:
            Graph: New Graph instance with gvawatermark nodes removed, or self
                if conditions are not met.

        Note:
            This creates a deep copy of the graph to avoid modifying the original.
        """
        # Early exit: if any OUTPUT_PLACEHOLDER exists, real sinks will be
        # added later, so keep gvawatermark nodes intact.
        for node in self.nodes:
            if node.type == OUTPUT_PLACEHOLDER:
                logger.debug(
                    "Graph contains OUTPUT_PLACEHOLDER, skipping gvawatermark removal"
                )
                return self

        # Collect all sink nodes (type ends with "sink")
        sink_nodes = [node for node in self.nodes if node.type.endswith("sink")]

        # If there are no sinks at all, nothing to decide — return unchanged.
        if not sink_nodes:
            return self

        # Check if ALL sinks are fakesink
        all_fakesink = all(node.type == "fakesink" for node in sink_nodes)
        if not all_fakesink:
            logger.debug("Not all sinks are fakesink, skipping gvawatermark removal")
            return self

        # Check if there are any gvawatermark nodes to remove.
        watermark_ids = [node.id for node in self.nodes if node.type == "gvawatermark"]
        if not watermark_ids:
            return self

        logger.debug(
            f"All sinks are fakesink, removing {len(watermark_ids)} gvawatermark node(s)"
        )

        modified_graph = copy.deepcopy(self)

        for wm_id in watermark_ids:
            # Find incoming edges (edges targeting this watermark node)
            incoming_edges = [e for e in modified_graph.edges if e.target == wm_id]
            # Find outgoing edges (edges sourced from this watermark node)
            outgoing_edges = [e for e in modified_graph.edges if e.source == wm_id]

            # Collect source node IDs from incoming edges
            source_ids = [e.source for e in incoming_edges]
            # Collect target node IDs from outgoing edges
            target_ids = [e.target for e in outgoing_edges]

            # Remove all edges connected to the watermark node
            modified_graph.edges = [
                e
                for e in modified_graph.edges
                if e.source != wm_id and e.target != wm_id
            ]

            # Reconnect: create edges from each source to each target
            # Find max edge ID for generating new unique IDs
            max_edge_id = 0
            for e in modified_graph.edges:
                try:
                    max_edge_id = max(max_edge_id, int(e.id))
                except ValueError:
                    pass

            next_edge_id = max_edge_id + 1

            for src in source_ids:
                for tgt in target_ids:
                    modified_graph.edges.append(
                        Edge(id=str(next_edge_id), source=src, target=tgt)
                    )
                    logger.debug(
                        f"Reconnected edge: {src} -> {tgt} (id={next_edge_id}) "
                        f"after removing gvawatermark node {wm_id}"
                    )
                    next_edge_id += 1

            # Remove the watermark node
            modified_graph.nodes = [n for n in modified_graph.nodes if n.id != wm_id]

        return modified_graph

    def inject_metadata_file_paths(self, metadata_dir: str) -> list[str]:
        """
        Assign output file paths to all gvametapublish nodes and configure them for file output.

        Sets method=file, file-format=json-lines, and file-path on every gvametapublish
        node found in the graph, overwriting any existing values.

        Args:
            metadata_dir: Directory where metadata files will be written.

        Returns:
            list[str]: Paths of the metadata files that were injected (one per gvametapublish node).
        """
        metadata_file_paths: list[str] = []
        for node in self.nodes:
            if node.type == "gvametapublish":
                meta_path = os.path.join(
                    metadata_dir,
                    f"metadata_{node.id}.jsonl",
                )
                node.data["method"] = "file"
                node.data["file-format"] = "json-lines"
                node.data["file-path"] = meta_path
                metadata_file_paths.append(meta_path)
        return metadata_file_paths

    def unify_model_instance_ids(self) -> "Graph":
        """
        Unify model-instance-id for nodes with the same device and model.

        Finds gvadetect and gvaclassify nodes and assigns the same model-instance-id
        to nodes that share identical device and model properties.
        This ensures model instances are properly reused when their configuration matches
        across multiple pipelines.

        Returns:
            Graph: New Graph instance with unified model-instance-ids

        Note:
            Model-instance-id is created by combining device and model values,
            with all characters lowercased and invalid characters replaced by underscores.
            This ensures consistent IDs across different pipelines with matching configurations.
        """
        modified_graph = copy.deepcopy(self)

        for node in modified_graph.nodes:
            if node.type not in {"gvadetect", "gvaclassify"}:
                continue

            device = node.data.get("device", "")
            model = node.data.get("model", "")

            # Sanitize each component: lowercase and replace invalid characters with underscores
            # Valid characters are: alphanumeric, hyphen, underscore
            sanitized_device = re.sub(r"[^a-z0-9_-]", "_", device.lower())
            sanitized_model = re.sub(r"[^a-z0-9_-]", "_", model.lower())

            model_instance_id = f"{sanitized_device}_{sanitized_model}"

            node.data["model-instance-id"] = model_instance_id
            logger.debug(
                f"Assigned model-instance-id={model_instance_id} to node {node.id} "
                f"(device={device}, model={model})"
            )

        return modified_graph

    def get_recommended_encoder_device(self) -> str:
        """
        Iterate backwards through nodes to find the last video/x-raw node
        and return the recommended encoder device based on memory type.

        Note: NPU variants are not considered because NPUs do not provide dedicated
        memory accessible for GStreamer pipeline buffering; they operate exclusively
        on system or shared memory.

        Returns:
            str: ENCODER_DEVICE_GPU if video/x-raw(memory:VAMemory) is detected,
                 ENCODER_DEVICE_CPU for standard video/x-raw or when no video/x-raw
                 node exists in the pipeline.
        """
        from video_encoder import ENCODER_DEVICE_CPU, ENCODER_DEVICE_GPU
        # TODO: temporary, to avoid circular import. In the near future, this file will be refactored to not depend on managers at all.

        for node in reversed(self.nodes):
            if not node.type.startswith("video/x-raw"):
                continue
            if "memory:VAMemory" in node.type:
                return ENCODER_DEVICE_GPU
            return ENCODER_DEVICE_CPU

        return ENCODER_DEVICE_CPU

    def to_simple_view(self) -> "Graph":
        """
        Generate a simplified view of the pipeline graph by filtering out technical elements.

        Returns:
            Graph: A new simplified graph with only visible elements

        This function creates a new graph that shows only "meaningful" elements (sources,
        inference, outputs) while hiding technical plumbing elements (queues, converters, etc.).
        Additionally, specific source elements (filesrc, v4l2src, rtspsrc) are converted to
        a generic "source" type for better UI presentation.

        Algorithm:
          1. Identify which nodes should be visible based on SIMPLE_VIEW_VISIBLE_ELEMENTS patterns
          2. Build a mapping of edges to traverse through hidden nodes
          3. Create new graph with only visible nodes (deep copied)
          4. Convert source elements (*src) to generic "source" nodes with kind/source attributes
          5. Reconnect edges: if A→hidden→hidden→B, create direct edge A→B
          6. Handle tee branches: preserve branching structure even when tee itself is hidden

        Important invariants:
          * Visible node IDs are preserved from the original graph
          * Edge IDs are regenerated sequentially in the new graph
          * Caps nodes (marked with __node_kind="caps") are always hidden
          * Source elements are converted to generic "source" type with standardized attributes
          * If all nodes in a path are hidden, the edge is dropped
          * Tee branch structure is maintained when tee has visible downstream nodes
        """
        logger.debug("Generating simple view from advanced graph")
        logger.debug(f"Visible element patterns: {SIMPLE_VIEW_VISIBLE_ELEMENTS}")

        # Use precompiled patterns for visibility check
        visible_node_ids = set()
        for node in self.nodes:
            if _is_node_visible(node, _COMPILED_VISIBLE_PATTERNS):
                visible_node_ids.add(node.id)
                logger.debug(f"Node {node.id} ({node.type}) is visible in simple view")
            else:
                logger.debug(f"Node {node.id} ({node.type}) is hidden in simple view")

        # Build adjacency map for traversing the graph
        edges_from: dict[str, list[str]] = defaultdict(list)
        for edge in self.edges:
            edges_from[edge.source].append(edge.target)

        # Create new graph with only visible nodes (preserving their IDs)
        # Sort nodes by their numeric IDs to ensure consistent ordering
        simple_nodes = [
            copy.deepcopy(node) for node in self.nodes if node.id in visible_node_ids
        ]
        simple_nodes.sort(key=lambda node: int(node.id))

        # Convert specific source elements (*src) to generic "source" type
        # This simplifies the UI by showing a unified source node
        _prepare_generic_input(simple_nodes)

        # Generate new edges by traversing through hidden nodes
        # Process visible nodes in sorted order by their numeric IDs to ensure consistent edge ordering
        simple_edges: list[Edge] = []
        edge_id = 0

        # Sort visible node IDs numerically to process them in order
        sorted_visible_node_ids = sorted(visible_node_ids, key=lambda x: int(x))

        for visible_node_id in sorted_visible_node_ids:
            # Find all visible downstream nodes by traversing through hidden nodes
            visible_targets = _find_visible_targets(
                visible_node_id, edges_from, visible_node_ids
            )

            # Sort target IDs to ensure consistent edge ordering
            sorted_visible_targets = sorted(visible_targets, key=lambda x: int(x))

            # Create direct edges from this visible node to all visible targets
            for target_id in sorted_visible_targets:
                simple_edges.append(
                    Edge(id=str(edge_id), source=visible_node_id, target=target_id)
                )
                logger.debug(
                    f"Created simple view edge: {visible_node_id} -> {target_id} (id={edge_id})"
                )
                edge_id += 1

        logger.debug(
            f"Simple view graph created with {len(simple_nodes)} nodes and {len(simple_edges)} edges"
        )
        return Graph(nodes=simple_nodes, edges=simple_edges)

    @staticmethod
    def apply_simple_view_changes(
        modified_simple: "Graph", original_simple: "Graph", original_advanced: "Graph"
    ) -> "Graph":
        """
        Merge changes from modified simple view back into the advanced view.

        Args:
            modified_simple: Simple view graph after user modifications
            original_simple: Original simple view graph before modifications
            original_advanced: Original advanced view graph to apply changes to

        Returns:
            Graph: New advanced view graph with changes applied

        Raises:
            ValueError: If any edges were added, removed, or modified
            ValueError: If any nodes were added or removed
            ValueError: If any unsupported changes were detected

        Algorithm:
          1. Detect changes in nodes (added/removed/modified)
          2. If nodes were added or removed, raise ValueError (not supported)
          3. Detect changes in edges between original_simple and modified_simple
          4. If any edge changes detected, raise ValueError (edge changes not supported)
          5. For modified node properties, update corresponding nodes in original_advanced
          6. Handle generic "source" nodes by converting them to specific GStreamer elements
          7. Return new advanced graph with updated properties

        Note: Property modifications of existing visible nodes are supported.

        All structural changes (adding/removing nodes or edges) are rejected.
        We check node structure first because removing nodes also removes their edges,
        and we want to report the root cause (node removal) rather than the symptom (edge removal).
        """
        logger.debug("Applying simple view changes to advanced view")

        # Step 1: Detect node changes
        # Build sets of node IDs for comparison
        original_node_ids = {node.id for node in original_simple.nodes}
        modified_node_ids = {node.id for node in modified_simple.nodes}

        # Check for added nodes
        added_node_ids = modified_node_ids - original_node_ids
        if added_node_ids:
            added_nodes_str = ", ".join(sorted(added_node_ids))
            raise ValueError(
                f"Node additions are not supported in simple view. "
                f"Added nodes: {added_nodes_str}. "
                f"Please use advanced view to add new nodes."
            )

        # Check for removed nodes
        removed_node_ids = original_node_ids - modified_node_ids
        if removed_node_ids:
            removed_nodes_str = ", ".join(sorted(removed_node_ids))
            raise ValueError(
                f"Node removals are not supported in simple view. "
                f"Removed nodes: {removed_nodes_str}. "
                f"Please use advanced view to remove nodes."
            )

        logger.debug("No node additions or removals detected - validation passed")

        # Step 2: Detect edge changes
        # Build dictionaries for efficient edge lookup by ID
        original_edges_by_id = {edge.id: edge for edge in original_simple.edges}
        modified_edges_by_id = {edge.id: edge for edge in modified_simple.edges}

        # Get sets of edge IDs for comparison
        original_edge_ids = set(original_edges_by_id.keys())
        modified_edge_ids = set(modified_edges_by_id.keys())

        # Check for added edges (new edge IDs that didn't exist before)
        added_edge_ids = modified_edge_ids - original_edge_ids
        if added_edge_ids:
            added_edges_details = [
                f"id={edge_id} ({modified_edges_by_id[edge_id].source} -> {modified_edges_by_id[edge_id].target})"
                for edge_id in sorted(added_edge_ids)
            ]
            added_edges_str = ", ".join(added_edges_details)
            raise ValueError(
                f"Edge additions are not supported in simple view. "
                f"Added edges: {added_edges_str}. "
                f"Please use advanced view to modify graph structure."
            )

        # Check for removed edges (edge IDs that existed before but are now gone)
        removed_edge_ids = original_edge_ids - modified_edge_ids
        if removed_edge_ids:
            removed_edges_details = [
                f"id={edge_id} ({original_edges_by_id[edge_id].source} -> {original_edges_by_id[edge_id].target})"
                for edge_id in sorted(removed_edge_ids)
            ]
            removed_edges_str = ", ".join(removed_edges_details)
            raise ValueError(
                f"Edge removals are not supported in simple view. "
                f"Removed edges: {removed_edges_str}. "
                f"Please use advanced view to modify graph structure."
            )

        # Check for modified edges (same edge ID but changed source or target)
        modified_edges_details = []
        for edge_id in original_edge_ids:
            original_edge = original_edges_by_id[edge_id]
            modified_edge = modified_edges_by_id[edge_id]

            # Check if source or target changed for this edge ID
            if (
                original_edge.source != modified_edge.source
                or original_edge.target != modified_edge.target
            ):
                modified_edges_details.append(
                    f"id={edge_id} changed from ({original_edge.source} -> {original_edge.target}) "
                    f"to ({modified_edge.source} -> {modified_edge.target})"
                )

        if modified_edges_details:
            modified_edges_str = ", ".join(modified_edges_details)
            raise ValueError(
                f"Edge modifications are not supported in simple view. "
                f"Modified edges: {modified_edges_str}. "
                f"Please use advanced view to modify graph structure."
            )

        logger.debug("No edge changes detected - validation passed")

        # Step 3: Detect modified node properties
        # Build dictionaries for efficient lookup
        original_nodes_by_id = {node.id: node for node in original_simple.nodes}
        modified_nodes_by_id = {node.id: node for node in modified_simple.nodes}

        # Track which nodes have property changes
        modified_node_ids_with_changes = set()

        for node_id in modified_node_ids:
            original_node = original_nodes_by_id[node_id]
            modified_node = modified_nodes_by_id[node_id]

            # Check if type changed (should not happen in simple view)
            if original_node.type != modified_node.type:
                raise ValueError(
                    f"Node type changes are not supported in simple view. "
                    f"Node {node_id} type changed from '{original_node.type}' to '{modified_node.type}'. "
                    f"Please use advanced view to modify node types."
                )

            # Check if data/properties changed
            if original_node.data != modified_node.data:
                modified_node_ids_with_changes.add(node_id)
                logger.debug(
                    f"Node {node_id} has property changes: "
                    f"original={original_node.data}, modified={modified_node.data}"
                )

        # Step 4: Apply property changes to advanced view
        # Create a deep copy of the advanced graph to avoid modifying the original
        result_advanced = copy.deepcopy(original_advanced)

        # Build a lookup dictionary for advanced nodes
        advanced_nodes_by_id = {node.id: node for node in result_advanced.nodes}

        # Apply changes to corresponding nodes in advanced view
        for node_id in modified_node_ids_with_changes:
            if node_id not in advanced_nodes_by_id:
                # This should never happen if simple view was correctly generated from advanced view
                # If it does happen, it indicates a bug in the simple view generation logic
                raise ValueError(
                    f"Internal error: Node {node_id} from simple view not found in advanced view. "
                    f"This indicates a mismatch between the simple and advanced graph representations."
                )

            # Get the modified properties from simple view
            modified_node = modified_nodes_by_id[node_id]

            # Update the properties in the advanced view node
            advanced_node = advanced_nodes_by_id[node_id]
            advanced_node.data.clear()
            advanced_node.data.update(modified_node.data)

            logger.debug(
                f"Applied property changes to advanced node {node_id}: {advanced_node.data}"
            )

        # Step 5: Handle generic "source" node mapping to GStreamer elements
        for node_id in modified_node_ids:
            modified_node = modified_nodes_by_id[node_id]

            if modified_node.type == "source":
                # Generic source node detected - map to appropriate GStreamer element
                kind = modified_node.data.get("kind", "")
                source = modified_node.data.get("source", "")

                if not kind or not source:
                    raise ValueError(
                        f"Node {node_id} of type 'source' must have both 'kind' and 'source' attributes. "
                        f"Found: kind='{kind}', source='{source}'"
                    )

                # Determine the target GStreamer element type and properties
                if kind == InputKind.VIDEO:
                    target_type = "filesrc"
                    target_properties = {"location": source}
                    logger.debug(
                        f"Mapping source node {node_id} to filesrc with location={source}"
                    )

                elif kind == InputKind.CAMERA:
                    if source.startswith(RTSP_URL_PREFIX):
                        target_type = "rtspsrc"
                        target_properties = {"location": source}
                        logger.debug(
                            f"Mapping source node {node_id} to rtspsrc with location={source}"
                        )
                    elif source.startswith(USB_DEVICE_PREFIX):
                        target_type = "v4l2src"
                        target_properties = {"device": source}
                        logger.debug(
                            f"Mapping source node {node_id} to v4l2src with device={source}"
                        )
                    else:
                        raise ValueError(
                            f"Unsupported camera source '{source}' for node {node_id}. "
                            f"Camera sources must start with '{RTSP_URL_PREFIX}' for network cameras or '{USB_DEVICE_PREFIX}' for USB cameras."
                        )

                elif kind == InputKind.IMAGE_SET:
                    # Image-set source: resolve the set name to a
                    # ``multifilesrc`` location pattern and inject a
                    # decoder + caps node right after it. The looping
                    # transformation flips ``loop`` to ``true`` later
                    # if the run requires it; here we always emit a
                    # single-pass configuration with ``stop-index`` so
                    # the pipeline terminates cleanly when the set is
                    # exhausted.
                    image_set = ImagesManager().get_image_set(source)
                    if image_set is None:
                        raise ValueError(
                            f"Unknown image set '{source}' for node {node_id}."
                        )
                    location_pattern = ImagesManager().get_location_pattern(source)
                    if location_pattern is None:
                        raise ValueError(
                            f"Failed to resolve location pattern for image set '{source}'."
                        )

                    if node_id not in advanced_nodes_by_id:
                        # Should not happen - the simple-to-advanced
                        # mapping is bijective for source nodes - but
                        # guard against drift instead of crashing in
                        # the rewiring loop below.
                        raise ValueError(
                            f"Internal error: image-set source node {node_id} missing in advanced view."
                        )

                    advanced_node = advanced_nodes_by_id[node_id]
                    advanced_node.type = "multifilesrc"
                    advanced_node.data.clear()
                    advanced_node.data.update(
                        {
                            "location": location_pattern,
                            "index": "1",
                            "stop-index": str(image_set.image_count),
                            "loop": "false",
                            "caps": _image_set_caps_for_extension(image_set.extension),
                            # Internal marker used by looping and codec
                            # detection to recognize this node as part
                            # of an image-set pipeline.
                            _IMAGE_SET_NODE_FLAG: image_set.extension,
                        }
                    )

                    # Allocate fresh IDs for the decoder and caps nodes.
                    existing_ids = [
                        int(n.id) for n in result_advanced.nodes if n.id.isdigit()
                    ] + [int(e.id) for e in result_advanced.edges if e.id.isdigit()]
                    next_id = (max(existing_ids) + 1) if existing_ids else 0

                    decoder_id = str(next_id)
                    next_id += 1
                    decoder_node = Node(
                        id=decoder_id,
                        type=_image_set_decoder_for_extension(image_set.extension),
                        data={},
                    )

                    edge_src_to_decoder = Edge(
                        id=str(next_id),
                        source=node_id,
                        target=decoder_id,
                    )
                    next_id += 1

                    # Insert the decoder right after the multifilesrc
                    # node in the nodes list to preserve the visual
                    # order in any debug dump.
                    for i, n in enumerate(result_advanced.nodes):
                        if n.id == node_id:
                            result_advanced.nodes.insert(i + 1, decoder_node)
                            break

                    # Rewire: every edge that previously left the
                    # source node now leaves the decoder, and we add
                    # one fresh edge ``source -> decoder``.
                    for edge in result_advanced.edges:
                        if edge.source == node_id:
                            edge.source = decoder_id
                    result_advanced.edges.append(edge_src_to_decoder)

                    logger.debug(
                        f"Transformed source node {node_id} into multifilesrc + "
                        f"{decoder_node.type} for image set '{source}' "
                        f"({image_set.image_count} images, {image_set.extension})"
                    )
                    # The standard "set type/data" code path below is
                    # bypassed for image sets because we already mutated
                    # the advanced node above. ``continue`` to the next
                    # source node.
                    continue
                else:
                    raise ValueError(
                        f"Unsupported source kind '{kind}' for node {node_id}. "
                        f"Supported kinds: '{InputKind.VIDEO.value}', "
                        f"'{InputKind.CAMERA.value}', '{InputKind.IMAGE_SET.value}'"
                    )

                # Update the node in advanced view (overwriting any properties copied earlier)
                if node_id in advanced_nodes_by_id:
                    advanced_node = advanced_nodes_by_id[node_id]
                    advanced_node.type = target_type
                    advanced_node.data.clear()
                    advanced_node.data.update(target_properties)
                    logger.debug(
                        f"Transformed source node {node_id} to {target_type} with properties {target_properties}"
                    )

        logger.debug(
            f"Successfully applied changes from simple view to advanced view. "
            f"Modified {len(modified_node_ids_with_changes)} nodes."
        )

        return result_advanced

    def get_target_device(self) -> str:
        """Determine the target inference device from the nearest gva* node after decodebin3.

        Searches forward from each decodebin3 node along edges to find the
        closest gva* element (gvadetect, gvaclassify, gvainference, etc.)
        that has a device attribute.

        If no decodebin3 node exists, falls back to scanning all gva* nodes
        in order.

        Returns:
            Device name ("CPU", "GPU", "NPU"), or "CPU" as default
            if no gva* node with device attribute is found.
        """
        # Build adjacency map for forward traversal
        edges_from: dict[str, list[str]] = {}
        for edge in self.edges:
            edges_from.setdefault(edge.source, []).append(edge.target)

        nodes_by_id = {node.id: node for node in self.nodes}

        # Find all decodebin3 nodes
        decodebin3_ids = [node.id for node in self.nodes if node.type == "decodebin3"]

        if decodebin3_ids:
            # BFS forward from each decodebin3 to find nearest gva* with device
            for db_id in decodebin3_ids:
                visited: set[str] = set()
                queue: list[str] = list(edges_from.get(db_id, []))

                while queue:
                    current_id = queue.pop(0)
                    if current_id in visited:
                        continue
                    visited.add(current_id)

                    current_node = nodes_by_id.get(current_id)
                    if current_node is None:
                        continue

                    if (
                        current_node.type.startswith("gva")
                        and "device" in current_node.data
                    ):
                        return current_node.data["device"].upper()

                    queue.extend(edges_from.get(current_id, []))

        # Fallback: scan all nodes in order for any gva* with device
        for node in self.nodes:
            if node.type.startswith("gva") and "device" in node.data:
                return node.data["device"].upper()

        return "CPU"

    def has_gvametapublish(self) -> bool:
        """Check whether the graph contains any gvametapublish element.

        Returns:
            True if at least one gvametapublish node is present, False otherwise.
        """
        return any(node.type == "gvametapublish" for node in self.nodes)

    def has_decodebin3(self) -> bool:
        """Check whether the graph contains a decodebin3 element."""
        return any(node.type == "decodebin3" for node in self.nodes)

    def has_image_set_source(self) -> bool:
        """Check whether the graph contains an image-set ``multifilesrc`` source.

        Image-set sources require the same post-processing pass as graphs
        with ``decodebin3`` (see ``apply_decodebin3_replacement``): the
        downstream chain may contain video-centric elements
        (``parsebin``, ``avdec_h264``, container muxers, ...) that need
        to be adapted to a raw-video stream produced by the dedicated
        image decoder.
        """
        return any(
            node.type == "multifilesrc" and _IMAGE_SET_NODE_FLAG in node.data
            for node in self.nodes
        )

    def determine_input_codec(self) -> Optional[str]:
        """Determine the input codec for this pipeline graph.

        Inspects the first source node in the graph to determine what kind
        of input is used, then retrieves the codec accordingly:
        - filesrc: reads Video.codec from VideosManager based on the location property.
        - v4l2src: reads best_capture.fourcc from CameraManager for the device path.
        - rtspsrc: reads best_profile.encoding from CameraManager for the RTSP URL.

        Returns:
            Codec string (e.g., "h264", "MJPG"), or None if codec cannot be determined.
        """
        from managers.camera_manager import CameraManager
        # TODO: temporary, to avoid circular import. In the near future, this file will be refactored to not depend on managers at all.

        for node in self.nodes:
            # Image-set sources carry their canonical extension on the
            # multifilesrc node. Returning that string here lets logging
            # and downstream device-selection code treat it like any
            # other codec value.
            if node.type == "multifilesrc" and _IMAGE_SET_NODE_FLAG in node.data:
                ext = str(node.data.get(_IMAGE_SET_NODE_FLAG, "")).lower()
                if ext:
                    logger.debug(
                        f"Determined codec '{ext}' from image-set multifilesrc"
                    )
                    return ext
                return None

            if node.type == "filesrc":
                location = node.data.get("location")
                if not location:
                    continue

                filename = os.path.basename(location)
                video = VideosManager().get_video(filename)
                if video is not None and video.codec:
                    logger.debug(
                        f"Determined codec '{video.codec}' from filesrc location '{location}'"
                    )
                    return video.codec
                return None

            elif node.type == "v4l2src":
                device_path = node.data.get("device")
                if not device_path:
                    continue
                details = CameraManager().get_usb_camera_details_by_device_path(
                    device_path
                )
                if details is None:
                    logger.debug(f"No camera found for device path '{device_path}'")
                    return None
                best_capture = details.best_capture
                if best_capture is not None and best_capture.fourcc:
                    logger.debug(
                        f"Determined codec '{best_capture.fourcc}' from v4l2src device '{device_path}'"
                    )
                    return best_capture.fourcc
                return None

            elif node.type == "rtspsrc":
                location = node.data.get("location")
                if not location:
                    continue
                details = CameraManager().get_network_camera_details_by_rtsp_url(
                    location
                )
                if details is None:
                    # Fall back to encoding lookup
                    encoding = CameraManager().get_encoding_for_rtsp_url(location)
                    if encoding:
                        logger.debug(
                            f"Determined codec '{encoding}' from rtspsrc URL '{location}' (encoding lookup)"
                        )
                        return encoding
                    logger.debug(f"No camera found for RTSP URL '{location}'")
                    return None
                best_profile = details.best_profile
                if best_profile is not None and best_profile.encoding:
                    logger.debug(
                        f"Determined codec '{best_profile.encoding}' from rtspsrc URL '{location}'"
                    )
                    return best_profile.encoding
                # Fall back to encoding from any matching profile
                encoding = CameraManager().get_encoding_for_rtsp_url(location)
                if encoding:
                    return encoding
                return None

        logger.debug("No source node found in graph, cannot determine codec")
        return None

    def apply_decodebin3_replacement(
        self,
        codec: Optional[str],
        target_device: str,
    ) -> "Graph":
        """Replace all decodebin3 nodes with parsebin + specific decoder + output caps.

        This ensures decoding happens on the device we want (matching the
        inference device), instead of letting decodebin3 choose arbitrarily.

        The replacement pattern for compressed codecs is:
            decodebin3 → parsebin ! <decoder> ! <output_caps>
        where output_caps is:
            - video/x-raw                    for CPU decoders
            - video/x-raw(memory:VAMemory)   for GPU/NPU (VA-API) decoders

        For raw formats: decodebin3 → videoconvert

        The method works in two phases:
        1. Determine replacements: for each decodebin3, build the list of
           replacement nodes (parsebin + decoder + caps, videoconvert, or keep).
           Also determine if a v4l2src capsfilter is needed.
        2. Apply replacements: mutate a deep copy of the graph with the
           determined replacements, updating nodes and edges.

        Args:
            codec: Input stream codec (e.g., "h264", "h265", "MJPG", "YUYV"),
                or None if codec cannot be determined (keeps decodebin3 as fallback).
            target_device: Target device from gvadetect ("CPU", "GPU", "NPU").

        Returns:
            Modified Graph with decodebin3 replaced.
            If no suitable decoder is found, decodebin3 is kept as-is (fallback).

        Note:
            This creates a deep copy of the graph to avoid modifying the original.
        """
        video_decoder = VideoDecoder()
        modified_graph = copy.deepcopy(self)

        # Image-set sources already carry their own dedicated image
        # decoder (jpegdec / pngdec / avdec_bmp / avdec_tiff) injected by
        # ``apply_simple_view_changes`` right after ``multifilesrc``. The
        # ``codec`` reported by ``determine_input_codec`` for these
        # graphs is the image extension (e.g. ``"jpg"``), which is not a
        # video codec and is intentionally absent from
        # ``FOURCC_TO_CODEC``. The generic decodebin3-replacement pass
        # does not apply; instead we run an image-set-specific upgrade
        # that handles VA-memory hand-off for GPU/NPU targets and prunes
        # any leftover ``decodebin3`` node that the simple-view
        # transformation may have carried over.
        if any(
            node.type == "multifilesrc" and _IMAGE_SET_NODE_FLAG in node.data
            for node in modified_graph.nodes
        ):
            logger.debug(
                "Image-set source detected; adapting video-centric pipeline "
                "elements and running decoder upgrade (target device: %s)",
                target_device,
            )
            # Step 1: rewrite video-centric pipeline elements that
            # assume a compressed input stream (parsebin, video
            # decoders, mp4 muxers without an encoder upstream). For
            # image-set sources the stream is already raw video right
            # after the image decoder, so these elements either need
            # to be removed, replaced with ``identity``, or paired
            # with a fresh encoder.
            modified_graph._adapt_image_set_video_pipeline(target_device)
            # Step 2: VA memory hand-off / redundant decodebin3 prune.
            modified_graph._upgrade_image_set_for_va_memory(target_device)
            return modified_graph

        if codec is None:
            logger.warning("Codec is None, keeping decodebin3 as-is (fallback)")
            return modified_graph

        # --- Phase 1: Determine replacements ---

        decoder_element = video_decoder.select_decoder(codec, target_device)
        is_raw = video_decoder.is_raw_format(codec)

        if decoder_element is not None:
            replacement_kind = "parsebin_decoder"
        elif is_raw:
            replacement_kind = "videoconvert"
        else:
            replacement_kind = "keep"
            logger.warning(
                f"Cannot find decoder for codec '{codec}' on device '{target_device}', "
                f"keeping decodebin3 as fallback"
            )

        if replacement_kind == "keep":
            return modified_graph

        # Determine output caps type based on target device.
        # VA-API decoders (GPU/NPU) output to VAMemory, CPU decoders output raw.
        device_upper = target_device.upper()
        if device_upper in {"GPU", "NPU"}:
            output_caps_type = "video/x-raw(memory:VAMemory)"
        else:
            output_caps_type = "video/x-raw"

        # Determine if a v4l2src capsfilter node is needed
        v4l2_caps_node_info = self._build_v4l2_caps_node(modified_graph.nodes)

        # Determine if a post-decoder videoconvert is needed:
        # - for v4l2src USB camera compatibility, or
        # - when gvamotiondetect is present and decoding on CPU
        has_gvamotiondetect = any(
            n.type == "gvamotiondetect" for n in modified_graph.nodes
        )
        needs_post_decoder_converter = v4l2_caps_node_info is not None or (
            has_gvamotiondetect and device_upper == "CPU"
        )

        # Find max existing ID across all nodes and edges for generating new IDs
        max_id = 0
        for node in modified_graph.nodes:
            try:
                max_id = max(max_id, int(node.id))
            except ValueError:
                pass
        for edge in modified_graph.edges:
            try:
                max_id = max(max_id, int(edge.id))
            except ValueError:
                pass

        next_id = max_id + 1

        # --- Phase 1b: Build replacement descriptors for each decodebin3 node ---
        # Each descriptor is a tuple: (db_node_id, new_nodes_to_insert)
        # where new_nodes_to_insert is a list of Node objects to place in
        # the graph after the (renamed) decodebin3 node.

        decodebin3_node_ids = [
            n.id for n in modified_graph.nodes if n.type == "decodebin3"
        ]

        # Pre-build all new nodes and record their IDs before mutating the graph.
        # Structure per decodebin3:
        #   replacement_kind == "videoconvert": rename node, no inserts
        #   replacement_kind == "parsebin_decoder":
        #       rename to parsebin, insert [decoder_node, output_caps_node]
        replacements: list[
            tuple[str, str, list[Node], list[Edge]]
        ] = []  # (db_node_id, kind, nodes_to_insert, edges_to_add)

        for db_node_id in decodebin3_node_ids:
            if replacement_kind == "videoconvert":
                if device_upper in {"GPU", "NPU"}:
                    element_type = "vapostproc"
                else:
                    element_type = "videoconvert"
                replacements.append((db_node_id, element_type, [], []))

            elif replacement_kind == "parsebin_decoder":
                assert decoder_element is not None

                # Decoder node
                decoder_node_id = str(next_id)
                next_id += 1
                decoder_node = Node(id=decoder_node_id, type=decoder_element, data={})

                nodes_to_insert_list = [decoder_node]
                edges_to_add_list = []

                # Determine the source for the caps node (either decoder or converter)
                caps_source_id = decoder_node_id

                # Post-decoder converter (videoconvert/vapostproc) needed for USB camera
                # compatibility or when gvamotiondetect is present on CPU
                if needs_post_decoder_converter:
                    converter_node_id = str(next_id)
                    next_id += 1
                    if device_upper in {"GPU", "NPU"}:
                        converter_element = "vapostproc"
                    else:
                        converter_element = "videoconvert"
                    converter_node = Node(
                        id=converter_node_id, type=converter_element, data={}
                    )
                    nodes_to_insert_list.append(converter_node)
                    caps_source_id = converter_node_id

                # Output caps node after decoder (or after converter if present)
                caps_node_id = str(next_id)
                next_id += 1
                caps_node = Node(
                    id=caps_node_id,
                    type=output_caps_type,
                    data={NODE_KIND_KEY: NODE_KIND_CAPS},
                )
                nodes_to_insert_list.append(caps_node)

                # Edges: parsebin → decoder → [converter] → caps → (original target)
                # We need to know the original outgoing edge from decodebin3
                # to rewire it. We'll handle that during phase 2, but we can
                # pre-build the internal edges now.
                edge_parsebin_to_decoder_id = str(next_id)
                next_id += 1
                edge_parsebin_to_decoder = Edge(
                    id=edge_parsebin_to_decoder_id,
                    source=db_node_id,  # parsebin (renamed decodebin3)
                    target=decoder_node_id,
                )
                edges_to_add_list.append(edge_parsebin_to_decoder)

                # If converter node exists, add edge decoder → converter
                if needs_post_decoder_converter:
                    edge_decoder_to_converter_id = str(next_id)
                    next_id += 1
                    edge_decoder_to_converter = Edge(
                        id=edge_decoder_to_converter_id,
                        source=decoder_node_id,
                        target=caps_source_id,
                    )
                    edges_to_add_list.append(edge_decoder_to_converter)

                # Edge from caps source (decoder or converter) to caps
                edge_to_caps_id = str(next_id)
                next_id += 1
                edge_to_caps = Edge(
                    id=edge_to_caps_id,
                    source=caps_source_id,
                    target=caps_node_id,
                )
                edges_to_add_list.append(edge_to_caps)

                replacements.append(
                    (
                        db_node_id,
                        "parsebin_decoder",
                        nodes_to_insert_list,
                        edges_to_add_list,
                    )
                )

        # Also reserve IDs for v4l2src capsfilter if needed
        v4l2_caps_node_id: Optional[str] = None
        v4l2_caps_node: Optional[Node] = None
        v4l2_edge: Optional[Edge] = None
        v4l2_node_id: Optional[str] = None

        if v4l2_caps_node_info is not None:
            v4l2_node_id, caps_base_type, caps_data = v4l2_caps_node_info

            v4l2_caps_node_id = str(next_id)
            next_id += 1
            v4l2_caps_node = Node(
                id=v4l2_caps_node_id, type=caps_base_type, data=caps_data
            )

            v4l2_edge_id = str(next_id)
            next_id += 1
            v4l2_edge = Edge(
                id=v4l2_edge_id,
                source=v4l2_node_id,
                target=v4l2_caps_node_id,
            )

        # --- Phase 2: Apply all mutations to the graph ---

        # 2a. Insert v4l2src capsfilter
        if (
            v4l2_node_id is not None
            and v4l2_caps_node is not None
            and v4l2_caps_node_id is not None
            and v4l2_edge is not None
        ):
            # Insert caps node after v4l2src in the nodes list
            for i, node in enumerate(modified_graph.nodes):
                if node.id == v4l2_node_id:
                    modified_graph.nodes.insert(i + 1, v4l2_caps_node)
                    break

            # Rewire: old edge from v4l2src→X becomes caps→X, add v4l2src→caps
            for edge in modified_graph.edges:
                if edge.source == v4l2_node_id:
                    edge.source = v4l2_caps_node_id
                    modified_graph.edges.append(v4l2_edge)
                    break

            logger.debug(f"Inserted capsfilter after v4l2src (node {v4l2_node_id})")

        # 2b. Apply decodebin3 replacements
        for db_node_id, kind, nodes_to_insert, edges_to_add in replacements:
            # Find the decodebin3 node in the (possibly shifted) nodes list
            db_node = None
            db_index = -1
            for i, node in enumerate(modified_graph.nodes):
                if node.id == db_node_id:
                    db_node = node
                    db_index = i
                    break

            if db_node is None:
                continue

            if kind in {"videoconvert", "vapostproc"}:
                db_node.type = kind
                logger.debug(
                    f"Replaced decodebin3 (node {db_node_id}) with {kind} "
                    f"for raw format '{codec}'"
                )

            elif kind == "parsebin_decoder":
                # Rename decodebin3 → parsebin
                db_node.type = "parsebin"

                # Insert new nodes (decoder, caps) right after parsebin
                for offset, new_node in enumerate(nodes_to_insert):
                    modified_graph.nodes.insert(db_index + 1 + offset, new_node)

                # The last inserted node is the output caps node.
                # Rewire the original outgoing edge: parsebin→X becomes caps→X
                last_inserted_id = nodes_to_insert[-1].id

                for edge in modified_graph.edges:
                    if edge.source == db_node_id:
                        edge.source = last_inserted_id
                        break

                # Add internal edges (parsebin→decoder, decoder→caps)
                modified_graph.edges.extend(edges_to_add)

                logger.debug(
                    f"Replaced decodebin3 (node {db_node_id}) with "
                    f"parsebin + {nodes_to_insert[0].type} + {nodes_to_insert[1].type}"
                )

        return modified_graph

    def _adapt_image_set_video_pipeline(self, target_device: str = "CPU") -> None:
        """
        In-place adaptation of a video-centric pipeline (e.g. Smart NVR
        templates) to make it compatible with image-set sources.

        Image-set graphs feed *raw* video into the pipeline right after
        the dedicated image decoder (jpegdec / pngdec / ...). However,
        many built-in templates were authored for compressed video
        sources and contain elements that assume a compressed input
        stream:

            * ``parsebin`` / ``h264parse`` / ``h265parse`` etc.
              parse a compressed bitstream that no longer exists.
            * ``avdec_h264`` / ``vah264dec`` / ``vah265dec`` /
              ``vaapidecodebin`` etc. decode a compressed bitstream
              that no longer exists.
            * ``splitmuxsink`` / ``mp4mux`` containers in a "recorder"
              tee branch require an encoded H264 stream.

        This pass walks the graph forward from each image-set source
        and:

            1. Replaces redundant parsers / video decoders with
               ``identity`` so the downstream chain stays linked.
            1b. (CPU only) Degrades any leftover
                ``video/x-raw(memory:VAMemory)`` capsfilter (originally
                paired with the now-replaced VA video decoder) to plain
                ``video/x-raw`` so the ``identity`` substitute can
                negotiate it. For GPU/NPU targets this downgrade must
                NOT happen: ``_upgrade_image_set_for_va_memory`` lifts
                every frame into VA memory by inserting
                ``vapostproc ! video/x-raw(memory:VAMemory),format=NV12``
                right after the image decoder, so a leftover VAMemory
                capsfilter further downstream (e.g. inside a ``tee``
                branch in Smart NVR GPU) is already compatible with the
                actual frames and must stay intact - degrading it would
                force ``identity`` to negotiate sysmem against an
                upstream VA producer and break the pipeline at parse
                time.
            2. Inserts ``[videoconvert !] <h264 encoder> ! h264parse``
                in front of any container/recorder sink
                (``splitmuxsink``, ``mp4mux``, or ``filesink`` whose
                ``location`` ends with a known mux extension) that does
                not already have an H264 encoder upstream. The encoder
                is target-aware: ``openh264enc`` for CPU, ``vah264lpenc``
                (or ``vah264enc``) for GPU/NPU. The leading
                ``videoconvert`` is only emitted for the CPU path -
                ``vah264lpenc`` accepts NV12 frames in either system or
                VA memory, so the extra conversion is unnecessary on
                GPU/NPU.
            3. (CPU only) injects ``videoconvert ! video/x-raw,format=NV12``
                in front of any reachable NV12-only consumer (such as
                ``gvamotiondetect``) that does not already have NV12 caps
                upstream. For GPU/NPU targets this step is a no-op
                because ``_upgrade_image_set_for_va_memory`` lifts the
                whole chain into ``video/x-raw(memory:VAMemory),format=NV12``,
                which every NV12-only DLStreamer consumer also accepts.

        The substitutions are deliberately structural (no edge
        rewiring) for steps 1 / 1b so that tee branches and downstream
        caps negotiation keep working as in the original template.

        Args:
            target_device: Inference target (``"CPU"``, ``"GPU"``,
                ``"NPU"``). NPU is treated like GPU for the purpose of
                encoder selection. Defaults to ``"CPU"`` for backwards
                compatibility with callers that did not pass an explicit
                device.
        """
        # Elements that should become a no-op for raw video input.
        REDUNDANT_PARSERS = {
            "parsebin",
            "h264parse",
            "h265parse",
            "h264parser",
            "h265parser",
            "mpegvideoparse",
            "mpeg4videoparse",
            "vp8parse",
            "vp9parse",
            "av1parse",
        }
        REDUNDANT_VIDEO_DECODERS = {
            # Note: ``decodebin`` / ``decodebin3`` are intentionally
            # NOT in this set. They are pruned (with edge rewiring)
            # later by ``_upgrade_image_set_for_va_memory`` so the
            # final graph has one fewer node, which keeps debug dumps
            # compact and matches the long-standing behaviour for
            # image-set graphs.
            "vaapidecodebin",
            "avdec_h264",
            "avdec_h265",
            "avdec_mpeg2video",
            "avdec_mpeg4",
            "avdec_vp8",
            "avdec_vp9",
            "avdec_av1",
            "vah264dec",
            "vah265dec",
            "vavp8dec",
            "vavp9dec",
            "vaav1dec",
            "qsvh264dec",
            "qsvh265dec",
        }
        REDUNDANT = REDUNDANT_PARSERS | REDUNDANT_VIDEO_DECODERS

        # Container sinks that require compressed H264 in front of them.
        CONTAINER_SINK_TYPES = {"splitmuxsink", "mp4mux"}
        MUX_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi"}

        # Only act if the graph actually contains an image-set source.
        image_set_sources = [
            n
            for n in self.nodes
            if n.type == "multifilesrc" and _IMAGE_SET_NODE_FLAG in n.data
        ]
        if not image_set_sources:
            return

        # Collect the set of node ids that are reachable forward from
        # any image-set source. Only those nodes are candidates for
        # rewriting; the rest of the graph (e.g. an unrelated branch)
        # is left alone.
        edges_from: dict[str, list[str]] = {}
        for edge in self.edges:
            edges_from.setdefault(edge.source, []).append(edge.target)
        nodes_by_id = {n.id: n for n in self.nodes}

        reachable: set[str] = set()
        stack = [src.id for src in image_set_sources]
        while stack:
            current = stack.pop()
            if current in reachable:
                continue
            reachable.add(current)
            for nxt in edges_from.get(current, []):
                if nxt not in reachable:
                    stack.append(nxt)

        # Step 1: replace redundant parsers / video decoders with
        # identity. Skip the image decoder itself (it is the immediate
        # successor of the multifilesrc and is required).
        image_decoder_ids: set[str] = set()
        for src in image_set_sources:
            for tgt in edges_from.get(src.id, []):
                # The image decoder is always the very first downstream
                # node from the multifilesrc.
                image_decoder_ids.add(tgt)

        # Step 0 (CPU only): force a uniform, DLStreamer-friendly raw
        # video format right after every software image decoder by
        # injecting ``videoconvert ! video/x-raw,format=I420`` between
        # the decoder and its current successors.
        #
        # Different image decoders expose very different sink caps for
        # downstream elements:
        #
        #   * ``pngdec``     -> only RGB / RGBA / GRAY8 / GRAY16_BE,
        #     none of which ``gvadetect`` / ``gvaclassify`` accept
        #     (their sink template is BGRx / BGRA / BGR / NV12 / I420).
        #     Without this step the pipeline fails to parse with
        #     "could not link pngdec0 to gvadetect0".
        #   * ``jpegdec``    -> I420 / RGB / BGR / xRGB / ...  - matches
        #     gvadetect natively, but a caps mismatch is still possible
        #     if the next element happens to renegotiate to a format
        #     the decoder cannot honour.
        #   * ``avdec_bmp``  -> a very long list including I420.
        #   * ``avdec_tiff`` -> a very long list including I420.
        #
        # ``I420`` is the lowest common denominator: every supported
        # software image decoder can output it directly, every
        # DLStreamer plugin used in the built-in pipelines
        # (``gvadetect``, ``gvaclassify``, ``gvatrack``,
        # ``gvawatermark``, ``gvafpscounter``, ``gvametaconvert``)
        # accepts it on input, the software H264 encoders
        # (``openh264enc`` / ``x264enc``) we pick for the file-output
        # branch take I420 natively, and the dedicated step 3 below
        # still gets to insert an extra ``videoconvert ! NV12`` in
        # front of NV12-only consumers (such as ``gvamotiondetect``).
        # The result is a single, deterministic raw-video format on
        # the wire between the decoder and the rest of the chain.
        #
        # GPU/NPU paths skip this step:
        # ``_upgrade_image_set_for_va_memory`` lifts the whole chain
        # into ``video/x-raw(memory:VAMemory),format=NV12`` via a
        # ``vapostproc`` bridge right after the image decoder, which
        # already gives every downstream plugin a uniform, DLStreamer-
        # friendly format.
        #
        # The injection is idempotent: if the decoder is already
        # followed by ``videoconvert`` or by an explicit format caps
        # node we skip it, so calling ``_adapt_image_set_video_pipeline``
        # twice on the same graph (or running the same conversion
        # repeatedly in the UI) does not stack up adapter pairs.
        _device_norm_step0 = (target_device or "").upper()
        _skip_cpu_format_force = _device_norm_step0 in {"GPU", "NPU"}

        def _successor_already_forces_format(decoder_id: str) -> bool:
            """Return ``True`` iff the decoder is immediately followed
            by a ``videoconvert`` element or by an explicit
            ``video/x-raw[,format=...]`` capsfilter."""
            for nxt_id in edges_from.get(decoder_id, []):
                nxt_node = nodes_by_id.get(nxt_id)
                if nxt_node is None:
                    continue
                if nxt_node.type == "videoconvert":
                    return True
                is_caps_node = nxt_node.data.get(NODE_KIND_KEY) == NODE_KIND_CAPS
                looks_like_raw_caps = nxt_node.type.startswith("video/x-raw")
                has_format = bool(str(nxt_node.data.get("format", "")).strip())
                if (is_caps_node or looks_like_raw_caps) and has_format:
                    return True
            return False

        if not _skip_cpu_format_force:
            sw_image_decoders_step0 = {
                "jpegdec",
                "pngdec",
                "avdec_bmp",
                "avdec_tiff",
            }

            # Sub-step 0a: prune a redundant ``decodebin3`` sitting
            # right after the image decoder. This mirrors the same
            # prune step in ``_upgrade_image_set_for_va_memory`` (which
            # only runs on GPU/NPU paths) and must happen here on the
            # CPU path before we inject the format-forcing
            # ``videoconvert``/caps pair below - otherwise the new
            # nodes would sit *between* the decoder and ``decodebin3``
            # and prevent the GPU/NPU prune from kicking in if this
            # method is later called with a different target. For CPU
            # the ``decodebin3`` is also a no-op (the dedicated image
            # decoder already produced raw frames), and leaving it in
            # the graph causes the same caps negotiation issues that
            # motivated the prune on GPU/NPU.
            for d_id in list(image_decoder_ids):
                decoder_node = nodes_by_id.get(d_id)
                if (
                    decoder_node is None
                    or decoder_node.type not in sw_image_decoders_step0
                ):
                    continue
                successors = list(edges_from.get(d_id, []))
                if len(successors) != 1:
                    continue
                db_id = successors[0]
                db_node = nodes_by_id.get(db_id)
                if db_node is None or db_node.type != "decodebin3":
                    continue
                # Rewire every edge leaving decodebin3 to leave the
                # image decoder, drop the decoder->decodebin3 edge and
                # the decodebin3 node itself.
                for edge in self.edges:
                    if edge.source == db_id:
                        edge.source = d_id
                self.edges = [
                    e
                    for e in self.edges
                    if not (e.source == d_id and e.target == db_id)
                ]
                self.nodes = [n for n in self.nodes if n.id != db_id]
                reachable.discard(db_id)
                logger.debug(
                    "Image-set adaptation (CPU): pruned redundant "
                    "decodebin3 (node %s) after image decoder (node %s)",
                    db_id,
                    d_id,
                )
                # Refresh local adjacency / id map after the prune.
                edges_from = {}
                for edge in self.edges:
                    edges_from.setdefault(edge.source, []).append(edge.target)
                nodes_by_id = {n.id: n for n in self.nodes}

            decoders_to_adapt: list[Node] = [
                nodes_by_id[d_id]
                for d_id in image_decoder_ids
                if d_id in nodes_by_id
                and nodes_by_id[d_id].type in sw_image_decoders_step0
                and not _successor_already_forces_format(d_id)
            ]

            for decoder in decoders_to_adapt:
                existing_ids = [int(n.id) for n in self.nodes if n.id.isdigit()] + [
                    int(e.id) for e in self.edges if e.id.isdigit()
                ]
                next_int = (max(existing_ids) + 1) if existing_ids else 0

                videoconvert_id = str(next_int)
                next_int += 1
                caps_id = str(next_int)
                next_int += 1

                videoconvert_node = Node(
                    id=videoconvert_id, type="videoconvert", data={}
                )
                caps_node = Node(
                    id=caps_id,
                    type="video/x-raw",
                    data={NODE_KIND_KEY: NODE_KIND_CAPS, "format": "I420"},
                )

                logger.debug(
                    "Image-set adaptation: injecting 'videoconvert ! "
                    "video/x-raw,format=I420' right after image decoder "
                    "'%s' (node %s) to give every downstream DLStreamer "
                    "consumer a uniform raw-video format",
                    decoder.type,
                    decoder.id,
                )

                # Insert the new chain in the node list right after the
                # decoder to keep debug dumps readable.
                insert_at = next(
                    (i for i, n in enumerate(self.nodes) if n.id == decoder.id),
                    len(self.nodes) - 1,
                )
                self.nodes[insert_at + 1 : insert_at + 1] = [
                    videoconvert_node,
                    caps_node,
                ]

                # Rewire: every edge that previously originated at the
                # decoder now originates at ``caps`` instead, and we
                # add the new bridge ``decoder -> videoconvert -> caps``.
                for edge in self.edges:
                    if edge.source == decoder.id:
                        edge.source = caps_id
                self.edges.append(
                    Edge(
                        id=str(next_int),
                        source=decoder.id,
                        target=videoconvert_id,
                    )
                )
                next_int += 1
                self.edges.append(
                    Edge(id=str(next_int), source=videoconvert_id, target=caps_id)
                )

                # Refresh adjacency / id map / reachability for
                # subsequent steps.
                edges_from = {}
                for edge in self.edges:
                    edges_from.setdefault(edge.source, []).append(edge.target)
                nodes_by_id = {n.id: n for n in self.nodes}
                # The new nodes are reachable from an image-set source
                # by construction; add them so later steps that gate
                # on ``reachable`` see them too.
                reachable.add(videoconvert_id)
                reachable.add(caps_id)

        for node in self.nodes:
            if node.id not in reachable:
                continue
            if node.id in image_decoder_ids:
                continue
            if node.type in REDUNDANT:
                logger.debug(
                    "Image-set adaptation: replacing redundant '%s' "
                    "(node %s) with 'identity'",
                    node.type,
                    node.id,
                )
                node.type = "identity"
                node.data.clear()

        # Step 1b (CPU only): degrade any pre-existing
        # ``video/x-raw(memory:VAMemory)*`` capsfilter that survived
        # the parser/decoder rewrite to plain ``video/x-raw*``. The
        # original VA capsfilters were paired with a VA video decoder
        # (``vah264dec`` etc.) in the YAML template; on a CPU target
        # that decoder has just been replaced with ``identity`` and
        # there is no upstream VA producer, so the VAMemory caps
        # filter would fail at parse time with ``can't handle caps
        # video/x-raw(memory:VAMemory)``.
        #
        # On GPU/NPU targets the downgrade must NOT happen:
        # ``_upgrade_image_set_for_va_memory`` (step 3) inserts a
        # ``vapostproc ! video/x-raw(memory:VAMemory),format=NV12``
        # bridge right after the software image decoder, so every
        # frame downstream is already in VA memory. A pre-existing
        # ``video/x-raw(memory:VAMemory)`` capsfilter sitting further
        # down the chain (typically inside a ``tee`` branch, e.g.
        # ``tee ! queue ! identity ! video/x-raw(memory:VAMemory) !
        # gvafpscounter ...`` in the Smart NVR GPU template) is then
        # perfectly compatible with what flows through it, and
        # ``identity`` passes VA memory through untouched. Degrading
        # it to plain ``video/x-raw`` would instead force a sysmem
        # negotiation that the upstream VA producer cannot satisfy
        # ("identity can't handle caps video/x-raw").
        # Note: ``Graph.from_pipeline_description`` only marks a caps
        # node with ``NODE_KIND_CAPS`` when the YAML segment carries
        # at least one ``key=value`` pair (e.g.
        # ``video/x-raw(memory:VAMemory),width=320``). A bare caps
        # segment such as ``video/x-raw(memory:VAMemory)`` is parsed
        # as a regular element node with empty ``data``. Both forms
        # appear in built-in templates (Simple NVR uses both), so we
        # match either: an explicit caps node, or any node whose
        # ``type`` literally starts with ``video/x-raw(memory:`` —
        # there is no GStreamer element with such a name, so this
        # cannot misfire on a real element.
        _device_norm_step1b = (target_device or "").upper()
        _skip_va_downgrade = _device_norm_step1b in {"GPU", "NPU"}
        for node in self.nodes:
            if _skip_va_downgrade:
                break
            if node.id not in reachable:
                continue
            is_caps_node = node.data.get(NODE_KIND_KEY) == NODE_KIND_CAPS
            looks_like_va_caps = node.type.startswith("video/x-raw(memory:")
            if not (is_caps_node or looks_like_va_caps):
                continue
            if "(memory:VAMemory)" not in node.type:
                continue
            new_type = node.type.replace("(memory:VAMemory)", "")
            logger.debug(
                "Image-set adaptation: degrading VAMemory capsfilter "
                "'%s' (node %s) to '%s' because the upstream decoder "
                "is now software / identity",
                node.type,
                node.id,
                new_type,
            )
            node.type = new_type

        # Step 2: container/recorder sinks need a compressed stream.
        # Walk each one and check whether an H264 encoder is reachable
        # backwards within the same connected sub-graph; if not,
        # synthesise ``videoconvert ! <encoder> ! h264parse`` in front
        # of it.
        edges_to: dict[str, list[str]] = {}
        for edge in self.edges:
            edges_to.setdefault(edge.target, []).append(edge.source)

        def _is_container_sink(n: Node) -> bool:
            if n.type in CONTAINER_SINK_TYPES:
                return True
            if n.type == "filesink":
                location = str(n.data.get("location", "")).lower()
                return any(location.endswith(ext) for ext in MUX_EXTENSIONS)
            return False

        def _has_h264_encoder_upstream(start_id: str) -> bool:
            """Backwards BFS from ``start_id`` looking for an h264 encoder."""
            seen: set[str] = set()
            queue = list(edges_to.get(start_id, []))
            while queue:
                cur = queue.pop()
                if cur in seen:
                    continue
                seen.add(cur)
                cur_node = nodes_by_id.get(cur)
                if cur_node is None:
                    continue
                # Encoder element names typically contain "264enc"
                # (openh264enc, x264enc, vah264enc, vah264lpenc,
                # qsvh264enc, ...). This is robust to the exact
                # element-string form returned by VideoEncoder.
                cur_type_first_word = cur_node.type.split()[0] if cur_node.type else ""
                if "264enc" in cur_type_first_word:
                    return True
                queue.extend(edges_to.get(cur, []))
            return False

        # Pick an encoder element string once, target-aware.
        # GPU/NPU pipelines benefit from a VA encoder
        # (``vah264lpenc`` / ``vah264enc``) because the inference
        # branch has already lifted frames into VA memory; a software
        # encoder would force a sysmem download with no benefit and
        # would in fact break caps negotiation for an all-VA chain.
        # The CPU path keeps the historical ``openh264enc`` selection.
        from video_encoder import (
            ENCODER_DEVICE_CPU,
            ENCODER_DEVICE_GPU,
            VideoEncoder,
        )

        device_norm = (target_device or "").upper()
        wants_va_encoder = device_norm in {"GPU", "NPU"}
        encoder_device = ENCODER_DEVICE_GPU if wants_va_encoder else ENCODER_DEVICE_CPU
        encoder_element_str = VideoEncoder()._select_element(
            encoder_device, streaming=False
        )
        # Fallback: if the requested device has no available encoder
        # (e.g. running on a CPU-only host that still requested GPU),
        # try the other device so the recorder branch is still usable.
        if encoder_element_str is None and wants_va_encoder:
            encoder_element_str = VideoEncoder()._select_element(
                ENCODER_DEVICE_CPU, streaming=False
            )
            if encoder_element_str is not None:
                logger.debug(
                    "Image-set adaptation: no VA H264 encoder available, "
                    "falling back to CPU encoder '%s' for container sinks",
                    encoder_element_str,
                )
                wants_va_encoder = False

        # ``videoconvert`` is only needed for the CPU path:
        # ``openh264enc`` / ``x264enc`` accept a narrow set of formats
        # (typically I420). VA encoders happily negotiate NV12 in
        # either system or VA memory, which the upstream chain already
        # produces, so the extra element is wasteful.
        emit_videoconvert_before_encoder = not wants_va_encoder

        # Snapshot container sinks before mutating the edge list.
        container_sinks = [
            n for n in self.nodes if n.id in reachable and _is_container_sink(n)
        ]

        for sink in container_sinks:
            if _has_h264_encoder_upstream(sink.id):
                continue
            if encoder_element_str is None:
                logger.warning(
                    "Image-set adaptation: container sink '%s' (node %s) "
                    "needs an H264 encoder upstream, but none is available "
                    "in the runtime; the recorder branch may fail.",
                    sink.type,
                    sink.id,
                )
                continue

            logger.debug(
                "Image-set adaptation: injecting '%s%s ! h264parse' in "
                "front of container sink '%s' (node %s)",
                "videoconvert ! " if emit_videoconvert_before_encoder else "",
                encoder_element_str,
                sink.type,
                sink.id,
            )

            # Allocate fresh node ids for the new chain. ``videoconvert``
            # is optional (CPU-only).
            existing_ids = [int(n.id) for n in self.nodes if n.id.isdigit()] + [
                int(e.id) for e in self.edges if e.id.isdigit()
            ]
            next_int = (max(existing_ids) + 1) if existing_ids else 0

            new_chain_nodes: list[Node] = []
            videoconvert_id: Optional[str] = None
            if emit_videoconvert_before_encoder:
                videoconvert_id = str(next_int)
                next_int += 1
                new_chain_nodes.append(
                    Node(id=videoconvert_id, type="videoconvert", data={})
                )

            encoder_id = str(next_int)
            next_int += 1
            h264parse_id = str(next_int)
            next_int += 1

            # ``encoder_element_str`` already contains properties (e.g.
            # "openh264enc bitrate=16000000 complexity=low"); render it
            # as a single token via ``node.type`` with empty data so
            # ``_build_chain`` outputs it verbatim.
            new_chain_nodes.append(
                Node(id=encoder_id, type=encoder_element_str, data={})
            )
            new_chain_nodes.append(Node(id=h264parse_id, type="h264parse", data={}))

            # Insert the new chain before the sink in the node list to
            # keep debug dumps readable.
            insert_at = next(
                (i for i, n in enumerate(self.nodes) if n.id == sink.id),
                len(self.nodes),
            )
            self.nodes[insert_at:insert_at] = new_chain_nodes

            # Rewire: every edge that previously targeted the sink now
            # targets the head of the new chain instead, and we add
            # the new chain ``[videoconvert ->] encoder -> h264parse
            # -> sink``.
            chain_head_id = (
                videoconvert_id if videoconvert_id is not None else encoder_id
            )
            for edge in self.edges:
                if edge.target == sink.id:
                    edge.target = chain_head_id
            if videoconvert_id is not None:
                self.edges.append(
                    Edge(id=str(next_int), source=videoconvert_id, target=encoder_id)
                )
                next_int += 1
            self.edges.append(
                Edge(id=str(next_int), source=encoder_id, target=h264parse_id)
            )
            next_int += 1
            self.edges.append(
                Edge(id=str(next_int), source=h264parse_id, target=sink.id)
            )

            # Refresh adjacency for subsequent iterations.
            edges_to = {}
            for edge in self.edges:
                edges_to.setdefault(edge.target, []).append(edge.source)
            nodes_by_id = {n.id: n for n in self.nodes}

        # Step 3: some downstream elements only accept NV12 raw video
        # (notably ``gvamotiondetect``). Image decoders such as
        # ``jpegdec`` / ``pngdec`` produce I420 (or RGB) by default, so
        # the link to such an element fails at parse time with
        # "could not link jpegdec0 to gvamotiondetect0". Inject
        # ``videoconvert ! video/x-raw,format=NV12`` right in front of
        # every reachable NV12-only consumer that does not already have
        # NV12 caps upstream within its connected sub-graph.
        #
        # This step only applies to the CPU path. For GPU/NPU,
        # ``_upgrade_image_set_for_va_memory`` lifts the whole chain
        # into ``video/x-raw(memory:VAMemory),format=NV12`` which every
        # NV12-only DLStreamer consumer also accepts (verified
        # empirically with ``gvamotiondetect`` on real Intel GPUs).
        if wants_va_encoder:
            return

        NV12_ONLY_CONSUMERS = {"gvamotiondetect"}

        def _has_nv12_caps_upstream(start_id: str) -> bool:
            """Backwards BFS from ``start_id`` looking for an NV12 caps node."""
            seen: set[str] = set()
            queue = list(edges_to.get(start_id, []))
            while queue:
                cur = queue.pop()
                if cur in seen:
                    continue
                seen.add(cur)
                cur_node = nodes_by_id.get(cur)
                if cur_node is None:
                    continue
                if cur_node.type.startswith("video/x-raw"):
                    fmt = str(cur_node.data.get("format", "")).upper()
                    if fmt == "NV12":
                        return True
                    # A different explicit format already locks the
                    # caps; do not walk further past it.
                    if fmt:
                        continue
                queue.extend(edges_to.get(cur, []))
            return False

        nv12_consumers = [
            n for n in self.nodes if n.id in reachable and n.type in NV12_ONLY_CONSUMERS
        ]

        for consumer in nv12_consumers:
            if _has_nv12_caps_upstream(consumer.id):
                continue

            logger.debug(
                "Image-set adaptation: injecting 'videoconvert ! "
                "video/x-raw,format=NV12' in front of NV12-only "
                "consumer '%s' (node %s)",
                consumer.type,
                consumer.id,
            )

            existing_ids = [int(n.id) for n in self.nodes if n.id.isdigit()] + [
                int(e.id) for e in self.edges if e.id.isdigit()
            ]
            next_int = (max(existing_ids) + 1) if existing_ids else 0

            videoconvert_id = str(next_int)
            next_int += 1
            caps_id = str(next_int)
            next_int += 1

            videoconvert_node = Node(id=videoconvert_id, type="videoconvert", data={})
            caps_node = Node(
                id=caps_id,
                type="video/x-raw",
                data={NODE_KIND_KEY: NODE_KIND_CAPS, "format": "NV12"},
            )

            insert_at = next(
                (i for i, n in enumerate(self.nodes) if n.id == consumer.id),
                len(self.nodes),
            )
            self.nodes[insert_at:insert_at] = [videoconvert_node, caps_node]

            # Rewire: every edge that previously targeted the consumer
            # now targets ``videoconvert`` instead, and we add the new
            # chain ``videoconvert -> caps -> consumer``.
            for edge in self.edges:
                if edge.target == consumer.id:
                    edge.target = videoconvert_id
            self.edges.append(
                Edge(id=str(next_int), source=videoconvert_id, target=caps_id)
            )
            next_int += 1
            self.edges.append(
                Edge(id=str(next_int), source=caps_id, target=consumer.id)
            )

            # Refresh adjacency for subsequent iterations.
            edges_to = {}
            for edge in self.edges:
                edges_to.setdefault(edge.target, []).append(edge.source)
            nodes_by_id = {n.id: n for n in self.nodes}

    def _upgrade_image_set_for_va_memory(self, target_device: str) -> None:
        """
        In-place upgrade of an image-set graph so that the downstream
        inference plugins can run with a VA-memory pre-process backend.

        The simple-view-to-advanced transformation injects a software
        image decoder (jpegdec / pngdec / avdec_bmp / avdec_tiff) right
        after the ``multifilesrc`` source. That software decoder produces
        ``video/x-raw`` in system memory, which is incompatible with
        ``pre-process-backend=va-surface-sharing`` on ``gvadetect`` /
        ``gvaclassify`` (DLStreamer rejects the pipeline at runtime with
        "For system memory only supports ie, opencv image preprocessors").

        For GPU/NPU targets this method applies four pipeline-agnostic
        transformations, in order:

            2. Prune any ``decodebin3`` immediately downstream of the
               image decoder (it is a no-op once the dedicated image
               decoder is in place and only confuses caps negotiation).
               Runs for both CPU and GPU/NPU.
            3. Insert ``vapostproc ! video/x-raw(memory:VAMemory),format=NV12``
               right after the software image decoder. This single
               element pair lifts every downstream consumer
               (``gvadetect``, ``gvaclassify``, ``gvamotiondetect``,
               ``gvafpscounter``, ``gvawatermark``, ...) into VA memory
               with the canonical NV12 format that every VA-aware
               DLStreamer plugin understands. GPU/NPU only.
               For RGB-emitting decoders (``pngdec``, ``avdec_bmp``,
               ``avdec_tiff``) an additional ``videoconvert !
               video/x-raw,format=NV12`` is interposed *before*
               ``vapostproc`` (step 3a) - on some Intel GPU stacks
               (Battlemage / BMG) ``vapostproc`` refuses to negotiate a
               direct RGB-sysmem -> VAMemory-NV12 link, so the pipeline
               needs a CPU-side NV12 normalisation first. ``jpegdec``
               emits I420 natively and skips this bridge.
            5. Swap any reachable software H264 encoder
               (``openh264enc`` / ``x264enc``) for a VA-API counterpart
               (``vah264lpenc`` / ``vah264enc`` / ``vaapih264lpenc`` /
               ``vaapih264enc``). Software H264 encoders cannot accept
               ``video/x-raw(memory:VAMemory)`` and would break the
               all-VA chain we just built. GPU/NPU only.
            6. Promote any ``vapostproc ! video/x-raw[,...]`` (system
               memory caps) pair reachable in the same branch to
               ``vapostproc ! video/x-raw(memory:VAMemory)[,...]``. Such
               pairs typically appear in built-in templates as a
               downscale step before the file-output encoder
               (e.g. ``vapostproc ! video/x-raw,width=320,height=240``);
               keeping them in VA memory matches the VA encoder
               selected in step 5 and avoids a needless sysmem
               round-trip. GPU/NPU only.

        Note: a previous revision also tried to swap ``jpegdec`` for
        ``vajpegdec`` (former "step 1") and to promote a CPU-only
        ``videoconvert ! NV12`` adapter pair injected by
        ``_adapt_image_set_video_pipeline`` (former "step 4"). Both
        steps were removed: ``vajpegdec`` rejects perfectly valid
        JPEGs at runtime on real Intel GPUs (Battlemage / Arc) with
        ``subclass failed to handle new picture``, and the CPU-only
        adapter pair is no longer emitted on GPU/NPU paths because
        step 3 here lifts everything into VA NV12 unconditionally.

        Args:
            target_device: Target inference device (``"CPU"``, ``"GPU"``,
                ``"NPU"``). NPU is treated like GPU for the purpose of
                memory hand-off (the VA-API stack handles both).
        """
        device = (target_device or "").upper()
        wants_va_memory = device in {"GPU", "NPU"}

        # Map software decoder name -> image-set node id (the
        # multifilesrc itself).
        sw_image_decoders = {"jpegdec", "pngdec", "avdec_bmp", "avdec_tiff"}

        # Build adjacency: node_id -> [(edge_index, target_id)] for fast
        # lookups and rewiring.
        edges_from: dict[str, list[int]] = {}
        for idx, edge in enumerate(self.edges):
            edges_from.setdefault(edge.source, []).append(idx)

        nodes_by_id = {n.id: n for n in self.nodes}

        # Find each image-set multifilesrc node and its immediate
        # successor (the software image decoder injected by
        # apply_simple_view_changes).
        for src_node in list(self.nodes):
            if src_node.type != "multifilesrc":
                continue
            if _IMAGE_SET_NODE_FLAG not in src_node.data:
                continue

            outgoing = edges_from.get(src_node.id, [])
            if not outgoing:
                continue

            decoder_edge_idx = outgoing[0]
            decoder_id = self.edges[decoder_edge_idx].target
            decoder_node = nodes_by_id.get(decoder_id)
            if decoder_node is None or decoder_node.type not in sw_image_decoders:
                # Unexpected layout - bail out rather than mutate
                # something we do not understand.
                continue

            # Step 2: prune a redundant decodebin3 sitting right after
            # the image decoder, regardless of target device. The
            # dedicated image decoder already produces raw frames, so
            # decodebin3 here is a no-op that confuses caps negotiation.
            decoder_outgoing = edges_from.get(decoder_id, [])
            if decoder_outgoing:
                first_after_decoder_edge_idx = decoder_outgoing[0]
                next_id = self.edges[first_after_decoder_edge_idx].target
                next_node = nodes_by_id.get(next_id)
                if next_node is not None and next_node.type == "decodebin3":
                    # Rewire: every edge that previously left the
                    # decodebin3 now leaves the decoder.
                    for edge in self.edges:
                        if edge.source == next_id:
                            edge.source = decoder_id
                    # Drop the edge decoder->decodebin3 and the
                    # decodebin3 node itself.
                    self.edges = [
                        e
                        for e in self.edges
                        if not (e.source == decoder_id and e.target == next_id)
                    ]
                    self.nodes = [n for n in self.nodes if n.id != next_id]
                    logger.debug(
                        "Pruned redundant decodebin3 (node %s) after image "
                        "decoder (node %s)",
                        next_id,
                        decoder_id,
                    )
                    # Rebuild fast lookups after structural change.
                    edges_from = {}
                    for idx, edge in enumerate(self.edges):
                        edges_from.setdefault(edge.source, []).append(idx)
                    nodes_by_id = {n.id: n for n in self.nodes}

            if not wants_va_memory:
                # CPU path: nothing else to do for this source.
                continue

            # Step 3: lift every downstream consumer into VA memory by
            # inserting ``vapostproc ! video/x-raw(memory:VAMemory),
            # format=NV12`` after the software decoder. A standalone
            # ``vapostproc`` is not enough - without an explicit caps
            # filter behind it, the element forwards system-memory
            # I420 frames downstream, which ``gvadetect`` with
            # ``pre-process-backend=va-surface-sharing`` rejects with
            # "For system memory only supports ie, opencv image
            # preprocessors".
            #
            # Step 3a (RGB-emitting decoders only): some software image
            # decoders emit RGB-family caps in system memory:
            #   - pngdec     -> RGB / RGBA / GRAY
            #   - avdec_bmp  -> BGRx / BGRA / RGB
            #   - avdec_tiff -> RGB / RGBA
            # ``vapostproc`` on some Intel GPU stacks (observed on
            # Battlemage / BMG) refuses to negotiate a direct
            # ``video/x-raw,format={RGB,RGBA,BGRx},memory:SystemMemory``
            # -> ``video/x-raw(memory:VAMemory),format=NV12`` link and
            # the pipeline dies at start with
            # "streaming stopped, reason not-negotiated (-4)".
            # ``jpegdec`` is unaffected because it emits I420 (a
            # native VA-friendly YUV format).
            # The fix is to interpose a CPU-side ``videoconvert !
            # video/x-raw,format=NV12`` so ``vapostproc`` always sees a
            # plain sysmem-NV12 input, which every Intel GPU driver
            # uploads to VAMemory reliably. The conversion runs once
            # per frame and the image-set use case is bounded to a few
            # frames, so the CPU cost is negligible.
            rgb_emitting_decoders = {"pngdec", "avdec_bmp", "avdec_tiff"}
            needs_sysmem_nv12_bridge = decoder_node.type in rgb_emitting_decoders

            existing_ids = [int(n.id) for n in self.nodes if n.id.isdigit()] + [
                int(e.id) for e in self.edges if e.id.isdigit()
            ]
            next_id_int = (max(existing_ids) + 1) if existing_ids else 0

            # Optional pre-stage: videoconvert ! video/x-raw,format=NV12
            pre_videoconvert_node: Node | None = None
            pre_caps_node: Node | None = None
            pre_edges: list[Edge] = []
            upload_source_id = decoder_id
            if needs_sysmem_nv12_bridge:
                pre_videoconvert_id = str(next_id_int)
                next_id_int += 1
                pre_videoconvert_node = Node(
                    id=pre_videoconvert_id,
                    type="videoconvert",
                    data={},
                )

                pre_caps_id = str(next_id_int)
                next_id_int += 1
                pre_caps_node = Node(
                    id=pre_caps_id,
                    type="video/x-raw",
                    data={NODE_KIND_KEY: NODE_KIND_CAPS, "format": "NV12"},
                )

                pre_edges.append(
                    Edge(
                        id=str(next_id_int),
                        source=decoder_id,
                        target=pre_videoconvert_id,
                    )
                )
                next_id_int += 1
                pre_edges.append(
                    Edge(
                        id=str(next_id_int),
                        source=pre_videoconvert_id,
                        target=pre_caps_id,
                    )
                )
                next_id_int += 1
                upload_source_id = pre_caps_id

            vapostproc_id = str(next_id_int)
            next_id_int += 1
            vapostproc_node = Node(id=vapostproc_id, type="vapostproc", data={})

            caps_id = str(next_id_int)
            next_id_int += 1
            caps_node = Node(
                id=caps_id,
                type="video/x-raw(memory:VAMemory)",
                data={NODE_KIND_KEY: NODE_KIND_CAPS, "format": "NV12"},
            )

            edge_upload_in = Edge(
                id=str(next_id_int),
                source=upload_source_id,
                target=vapostproc_id,
            )
            next_id_int += 1
            edge_vapostproc_to_caps = Edge(
                id=str(next_id_int),
                source=vapostproc_id,
                target=caps_id,
            )
            next_id_int += 1

            # Rewire: every edge that previously left the decoder now
            # leaves the final caps node (after we add the new bridging
            # edges below).
            for edge in self.edges:
                if edge.source == decoder_id:
                    edge.source = caps_id

            # Insert nodes right after the decoder for readability in
            # any debug dump.
            inserted_nodes: list[Node] = []
            if pre_videoconvert_node is not None and pre_caps_node is not None:
                inserted_nodes.extend([pre_videoconvert_node, pre_caps_node])
            inserted_nodes.extend([vapostproc_node, caps_node])
            for i, n in enumerate(self.nodes):
                if n.id == decoder_id:
                    self.nodes[i + 1 : i + 1] = inserted_nodes
                    break

            self.edges.extend(pre_edges)
            self.edges.append(edge_upload_in)
            self.edges.append(edge_vapostproc_to_caps)

            if needs_sysmem_nv12_bridge:
                logger.debug(
                    "Inserted 'videoconvert ! video/x-raw,format=NV12 ! "
                    "vapostproc ! video/x-raw(memory:VAMemory),format=NV12' "
                    "after RGB-emitting decoder '%s' (node %s) to lift "
                    "frames into VA memory via a sysmem-NV12 bridge",
                    decoder_node.type,
                    decoder_id,
                )
            else:
                logger.debug(
                    "Inserted 'vapostproc ! video/x-raw"
                    "(memory:VAMemory),format=NV12' (nodes %s, %s) "
                    "after software image decoder (node %s) to lift "
                    "frames into VA memory",
                    vapostproc_id,
                    caps_id,
                    decoder_id,
                )

            # Refresh adjacency for steps 5 / 6.
            edges_from = {}
            for idx, edge in enumerate(self.edges):
                edges_from.setdefault(edge.source, []).append(idx)
            nodes_by_id = {n.id: n for n in self.nodes}

            # Compute reachability from the current image-set source
            # so steps 5 and 6 only touch nodes in this branch.
            edges_from_reach: dict[str, list[str]] = {}
            for edge in self.edges:
                edges_from_reach.setdefault(edge.source, []).append(edge.target)
            reachable_from_src: set[str] = set()
            stack = [src_node.id]
            while stack:
                cur = stack.pop()
                if cur in reachable_from_src:
                    continue
                reachable_from_src.add(cur)
                for nxt in edges_from_reach.get(cur, []):
                    if nxt not in reachable_from_src:
                        stack.append(nxt)

            # Step 5: swap any reachable software H264 encoder
            # (``openh264enc`` / ``x264enc``) for a VA-API counterpart.
            # Software H264 encoders cannot accept
            # ``video/x-raw(memory:VAMemory)``, which makes them
            # incompatible with the all-VA inference chain we just
            # built. Property strings already set on the sw encoder
            # node (e.g. ``bitrate``) are discarded because the VA
            # encoders use a different property surface
            # (``rate-control``, ``target-usage``, ...) and would be
            # rejected by GStreamer. Fallback: if no VA encoder is
            # registered we leave the encoder alone (the pipeline may
            # still fail, but we do not make things worse).
            from explore import GstInspector

            available_elements = {e[1] for e in GstInspector().elements}
            # Order matters: low-power encoder first (more efficient
            # on Intel iGPUs), then full-power, then legacy vaapi
            # naming.
            VA_H264_ENCODER_PREFERENCE = [
                "vah264lpenc",
                "vah264enc",
                "vaapih264lpenc",
                "vaapih264enc",
            ]
            SW_H264_ENCODERS = {"openh264enc", "x264enc"}

            va_encoder = next(
                (
                    cand
                    for cand in VA_H264_ENCODER_PREFERENCE
                    if cand in available_elements
                ),
                None,
            )

            if va_encoder is not None:
                for node in self.nodes:
                    if node.id not in reachable_from_src:
                        continue
                    # ``node.type`` for an encoder may carry inline
                    # properties (e.g. "openh264enc bitrate=16000000
                    # complexity=low"). Compare only the first
                    # whitespace-separated token.
                    first_token = node.type.split()[0] if node.type else ""
                    if first_token in SW_H264_ENCODERS:
                        logger.debug(
                            "Replacing software H264 encoder '%s' "
                            "(node %s) with VA encoder '%s' for "
                            "image-set source %s on target %s",
                            node.type,
                            node.id,
                            va_encoder,
                            src_node.id,
                            device,
                        )
                        node.type = va_encoder
                        node.data.clear()

            # Step 6: promote every reachable
            # ``vapostproc ! video/x-raw[,props]`` pair (sysmem caps)
            # to ``vapostproc ! video/x-raw(memory:VAMemory)[,props]``.
            # This typically catches the downscale step that templates
            # place before the main file-output encoder
            # (e.g. ``vapostproc ! video/x-raw,width=320,height=240 !
            # vah264lpenc ! ...``); keeping it in VA memory avoids a
            # needless sysmem round-trip and matches the VA encoder
            # selected in step 5. The newly inserted pair from step 3
            # is already VA-aware so it is safe to skip.
            for node in self.nodes:
                if node.id not in reachable_from_src:
                    continue
                if node.type != "vapostproc":
                    continue
                if node.id == vapostproc_id:
                    # Pair we just inserted in step 3 - already VA.
                    continue
                vp_outgoing = edges_from.get(node.id, [])
                if len(vp_outgoing) != 1:
                    continue
                caps_target_id = self.edges[vp_outgoing[0]].target
                caps_target = nodes_by_id.get(caps_target_id)
                if caps_target is None:
                    continue
                # Match either an explicit caps node (``__node_kind=caps``)
                # or a bare ``video/x-raw[(...)]`` segment that the
                # YAML parser left unmarked. Skip anything that is
                # already a VAMemory caps.
                is_caps = caps_target.data.get(
                    NODE_KIND_KEY
                ) == NODE_KIND_CAPS or caps_target.type.startswith("video/x-raw")
                if not is_caps:
                    continue
                if "(memory:VAMemory)" in caps_target.type:
                    continue
                if not caps_target.type.startswith("video/x-raw"):
                    continue
                new_type = caps_target.type.replace(
                    "video/x-raw", "video/x-raw(memory:VAMemory)", 1
                )
                logger.debug(
                    "Promoting sysmem caps '%s' (node %s) downstream of "
                    "vapostproc (node %s) to '%s' for image-set source %s",
                    caps_target.type,
                    caps_target.id,
                    node.id,
                    new_type,
                    src_node.id,
                )
                caps_target.type = new_type

    def validate_camera_sources_followed_by_decodebin3(self) -> None:
        """
        Validate that all camera sources (rtspsrc or v4l2src) are followed by decodebin3.

        This validation ensures that camera pipelines have the required decoder element
        after the source element to properly handle the incoming stream.

        This function only validates direct camera source nodes (v4l2src, rtspsrc) which
        appear in advanced view.

        Args:
            None

        Returns:
            None

        Raises:
            ValueError: If any camera source is not followed by any element
            ValueError: If any camera source is not followed by decodebin3

        Example:
            Validates that: rtspsrc -> decodebin3 or v4l2src -> decodebin3
        """
        # Build a mapping of node IDs to nodes for quick lookup
        node_by_id = {node.id: node for node in self.nodes}

        # Build adjacency map for outgoing edges
        edges_from: dict[str, list[str]] = {}
        for edge in self.edges:
            edges_from.setdefault(edge.source, []).append(edge.target)

        for node in self.nodes:
            if node.type not in {"v4l2src", "rtspsrc"}:
                continue

            next_nodes = edges_from.get(node.id, [])
            if not next_nodes:
                raise ValueError(
                    f"Camera source '{node.type}' requires a decodebin3 element to follow it, "
                    "but no element follows the camera source"
                )

            next_node_id = next_nodes[0]
            next_node = node_by_id.get(next_node_id)

            if not next_node or next_node.type != "decodebin3":
                next_type = next_node.type if next_node else "unknown"
                raise ValueError(
                    f"Camera source '{node.type}' requires a decodebin3 element to follow it, "
                    f"but found '{next_type}' instead"
                )

    @staticmethod
    def _build_v4l2_caps_node(
        nodes: list[Node],
    ) -> Optional[tuple[str, str, dict[str, str]]]:
        """Build a caps node description for the first valid v4l2src in the graph.

        Looks up the USB camera's best_capture configuration via CameraManager
        and builds the caps string using VideoDecoder. Only processes the first
        v4l2src node that has a valid device path, camera, best_capture, and
        caps string. All other v4l2src nodes are ignored.

        This method does NOT modify the graph. It returns the information
        needed for the caller to insert the caps node.

        Args:
            nodes: List of nodes to search for v4l2src elements.

        Returns:
            Tuple of (v4l2_node_id, caps_base_type, caps_data_dict) if a caps
            node should be inserted, or None if no valid v4l2src is found.
            The caps_data_dict includes the NODE_KIND_KEY marker and all
            caps properties.
        """
        from managers.camera_manager import CameraManager
        # TODO: temporary, to avoid circular import. In the near future, this file will be refactored to not depend on managers at all.

        video_decoder = VideoDecoder()

        for node in nodes:
            if node.type != "v4l2src":
                continue

            device_path = node.data.get("device", "")
            if not device_path:
                continue

            details = CameraManager().get_usb_camera_details_by_device_path(device_path)
            if details is None:
                continue

            best_capture = details.best_capture
            if best_capture is None:
                continue

            caps_string = video_decoder.build_caps_string(
                best_capture.fourcc,
                best_capture.width,
                best_capture.height,
                best_capture.fps,
            )
            if caps_string is None:
                continue

            # Parse caps string into base type and properties
            # e.g., "image/jpeg,width=1920,height=1080,framerate=30/1"
            caps_parts = caps_string.split(",")
            caps_base = caps_parts[0]
            caps_data: dict[str, str] = {NODE_KIND_KEY: NODE_KIND_CAPS}
            for part in caps_parts[1:]:
                if "=" in part:
                    k, v = part.split("=", 1)
                    caps_data[k.strip()] = v.strip()

            logger.debug(f"Built caps node for v4l2src (node {node.id}): {caps_string}")
            return node.id, caps_base, caps_data

        return None


def _is_node_visible(node: Node, visible_patterns: list[re.Pattern]) -> bool:
    """
    Determine if a node should be visible in Simple View based on pattern matching.

    A node is visible if its type matches any of the visible patterns.
    Caps nodes (identified by __node_kind="caps" in data) are always hidden.

    Args:
        node: The node to check for visibility
        visible_patterns: List of compiled regex patterns to match against node type

    Returns:
        bool: True if node should be visible in simple view, False if it should be hidden

    Examples:
        - Node with type "filesrc" matches pattern "*src" -> visible
        - Node with type "gvadetect" matches pattern "gva*" -> visible
        - Node with type "queue" doesn't match any pattern -> hidden
        - Node with __node_kind="caps" -> always hidden regardless of type
    """
    # Always hide caps nodes regardless of their type
    if node.data.get(NODE_KIND_KEY) == NODE_KIND_CAPS:
        return False

    node_type = node.type

    # Step 1: Check if node type matches any visible pattern
    matches_visible = False
    for pattern in visible_patterns:
        if pattern.match(node_type):
            matches_visible = True
            break

    if not matches_visible:
        return False

    # Step 2: Check if node type matches any invisible pattern (exclusion)
    for pattern in _COMPILED_INVISIBLE_PATTERNS:
        if pattern.match(node_type):
            return False

    return True


def _find_visible_targets(
    source_id: str,
    edges_from: dict[str, list[str]],
    visible_node_ids: set[str],
) -> set[str]:
    """
    Find all visible nodes reachable from source_id by traversing through hidden nodes.

    This function performs a breadth-first search starting from source_id,
    skipping over hidden nodes, and collecting all visible nodes encountered.

    Algorithm:
      1. Start from the immediate children of source_id
      2. For each child:
         - If visible, add to results
         - If hidden, recursively explore its children
      3. Use visited set to avoid infinite loops in case of cycles

    Args:
        source_id: Starting node ID to search from
        edges_from: Adjacency map (node_id -> list of target node IDs)
        visible_node_ids: Set of node IDs that are visible in simple view

    Returns:
        set[str]: Set of visible node IDs reachable from source_id

    Example:
        If graph is: A(visible) -> B(hidden) -> C(hidden) -> D(visible)
        Calling _find_visible_targets("A", ...) will return {"D"}
    """
    visible_targets: set[str] = set()
    visited: set[str] = set()

    # Queue for breadth-first search: stores node IDs to explore
    queue: list[str] = list(edges_from.get(source_id, []))

    while queue:
        current_id = queue.pop(0)

        # Skip if already visited (avoid infinite loops)
        if current_id in visited:
            continue
        visited.add(current_id)

        if current_id in visible_node_ids:
            # Found a visible node - add to results
            visible_targets.add(current_id)
        else:
            # Hidden node - continue traversing through its children
            queue.extend(edges_from.get(current_id, []))

    return visible_targets


def _parse_caps_segment(segment: str) -> tuple[str, dict[str, str]] | None:
    """
    Try to parse a whole segment (between '!' delimiters) as a GStreamer caps string.

    We intentionally use a very simple and explicit definition of "caps string"
    to avoid relying on any hard-coded list of media types or heuristics based
    on slashes or parentheses.

    A segment is treated as caps if and only if:
        - It contains at least one comma ',', and
        - After splitting by commas:
            parts[0] is the caps base (for example "video/x-raw" or
            "video/x-raw(memory:VAMemory)"), and
            every subsequent part is a property in the exact form
                key=value
              with both key and value being non-empty strings after trimming.

    Args:
        segment: Raw string segment from pipeline description (between '!' separators)

    Returns:
        tuple[str, dict[str, str]] | None:
            - If segment is valid caps: (caps_base, properties_dict)
            - If segment is not caps: None

    Raises:
        ValueError: If segment has commas but invalid property format (empty base, missing '=', empty key/value)

    Examples of valid caps (returns tuple):
        "video/x-raw(memory:VAMemory),width=320,height=240"
        "video/x-raw,width=320,height=240"
        "video/x-raw(memory:NVMM),format=UYVY,width=2592,height=1944,framerate=28/1"
        "video/x-raw,format=(string)UYVY,width=(int)2592,height=(int)1944,framerate=(fraction)28/1"

    Examples of non-caps (returns None):
        "video/x-raw(memory:NVMM)"  - no comma
        "video/x-raw"                - no comma
        "filesrc"                    - no comma

    Examples that raise ValueError:
        ",width=320"              - empty caps base
        "video/x-raw,width"       - property missing '='
        "video/x-raw,=320"        - empty key
        "video/x-raw,width="      - empty value
    """
    text = segment.strip()
    if not text:
        return None

    # Fast path: if there is no comma at all, this cannot be caps by our rules.
    if "," not in text:
        return None

    parts = [p.strip() for p in text.split(",")]
    # parts is guaranteed to be non-empty for a non-empty string, but we still
    # validate that the first part (caps base) is not empty.
    if not parts[0]:
        # Something like ",width=320" – treat as invalid caps.
        raise ValueError(f"Invalid caps segment (empty base): '{segment}'")

    caps_base = parts[0]
    props: dict[str, str] = {}

    # All remaining parts must be 'key=value' with non-empty key and value.
    for raw_prop in parts[1:]:
        if not raw_prop:
            raise ValueError(f"Invalid caps segment (empty property) in: '{segment}'")

        if "=" not in raw_prop:
            raise ValueError(
                f"Invalid caps property (missing '=') in segment '{segment}': '{raw_prop}'"
            )

        key, value = raw_prop.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not key or not value:
            raise ValueError(
                f"Invalid caps property (empty key or value) in segment '{segment}': '{raw_prop}'"
            )

        props[key] = value

    return caps_base, props


def _tokenize(element: str) -> Iterator[_Token]:
    """
    Tokenize a non-caps pipeline segment into TYPE/PROPERTY/TEE_END tokens.

    This tokenizer is only used for segments that were NOT recognized as caps
    by _parse_caps_segment(). In other words, it is responsible for:
      - regular elements (e.g. "filesrc location=/tmp/foo.mp4"),
      - tee endpoints ("t."),
      - their key=value properties.

    NOTE: Historically this tokenizer also tried to parse caps-like patterns.
    This caused multiple subtle bugs for caps without parentheses. The caps
    handling has been refactored out into _parse_caps_segment(), and this
    tokenizer is now intentionally simple and focused purely on elements.

    Args:
        element: Non-caps segment string to tokenize (e.g., "filesrc location=/tmp/foo.mp4")

    Yields:
        _Token: Tokens with kind TYPE, PROPERTY, TEE_END, or MISMATCH

    Token kinds:
        - TYPE: Element type (e.g., "filesrc", "gvadetect")
        - PROPERTY: Key=value pair (e.g., "location=/tmp/foo.mp4")
        - TEE_END: Tee branch endpoint (e.g., "t.")
        - MISMATCH: Unrecognized token (caller should raise error)
        - SKIP: Whitespace (filtered out, never yielded)

    Example:
        Input: "filesrc location=/tmp/foo.mp4"
        Output: [Token(TYPE, "filesrc"), Token(PROPERTY, "location=/tmp/foo.mp4")]
    """
    token_specification = [
        # Property in key=value format, with support for quoted values containing spaces
        # Matches: key=value, key="quoted value", key='quoted value'
        ("PROPERTY", r'\S+\s*=\s*(?:"[^"]*"|\'[^\']*\'|\S+)'),
        # End of tee branch: "t." where t is the tee name
        ("TEE_END", r"\S+\.(?:\s|\Z)"),
        # Type of element (catch-all for non-property tokens)
        ("TYPE", r"\S+"),
        # Skip over whitespace
        ("SKIP", r"\s+"),
        # Any other character (treated as hard error)
        ("MISMATCH", r"."),
    ]

    tok_regex = "|".join(
        f"(?P<{name}>{pattern})" for name, pattern in token_specification
    )

    for mo in re.finditer(tok_regex, element):
        kind = mo.lastgroup
        value = mo.group().strip()
        if kind == "SKIP":
            continue

        yield _Token(kind, value)


def _add_caps_node(
    nodes: list[Node],
    edges: list[Edge],
    node_id: int,
    caps_base: str,
    caps_props: dict[str, str],
    tee_stack: list[str],
    prev_token_kind: str | None,
    edge_id: int,
) -> int:
    """
    Append a caps node to the graph and connect it with the previous node.

    This is used when a whole segment between '!' delimiters was recognized
    as a caps string by _parse_caps_segment().

    Node layout:
        Node(
            id=str(node_id),
            type=caps_base,
            data={
                "__node_kind": "caps",
                **caps_props,
            },
        )

    Edge logic:
        - If this is the first node (node_id == 0), no incoming edge is added.
        - Otherwise:
            * If the previous token kind was TEE_END, we pop the last tee
              node id from the stack and connect from that node.
              If the tee stack is empty in this situation, the pipeline
              syntax is inconsistent and a clear error is raised.
            * Otherwise we create a linear edge from the previous node.
        - Edge IDs are assigned from a separate monotonically increasing
          integer counter (edge_id) and stored as strings. This guarantees
          that edge IDs are unique even when multiple caps nodes appear
          in sequence, while preserving the representation as strings.

    Args:
        nodes: List of nodes to append the new caps node to (modified in place)
        edges: List of edges to append new edge to (modified in place)
        node_id: Numeric ID for the new caps node
        caps_base: Base caps type (e.g., "video/x-raw" or "video/x-raw(memory:VAMemory)")
        caps_props: Dictionary of caps properties (key=value pairs)
        tee_stack: Stack of tee node IDs for handling tee branches (modified in place)
        prev_token_kind: Kind of the previous token (used to determine edge source)
        edge_id: Current edge ID counter for generating unique edge IDs

    Returns:
        int: Updated edge_id counter (incremented by 1 if edge was added, unchanged otherwise)

    Raises:
        ValueError: If prev_token_kind is TEE_END but tee_stack is empty
    """
    node_id_str = str(node_id)
    logger.debug(
        f"Adding caps node {node_id_str}: base={caps_base}, props={caps_props}"
    )

    # Inject the internal node kind discriminator into the data dictionary.
    # This lets us distinguish caps nodes during serialization without
    # extending the public Node schema.
    data_with_kind: dict[str, str] = {
        NODE_KIND_KEY: NODE_KIND_CAPS,
        **caps_props,
    }

    nodes.append(Node(id=node_id_str, type=caps_base, data=data_with_kind))

    if node_id > 0:
        if prev_token_kind == "TEE_END":
            # A tee endpoint ("t.") was seen before this caps node, so we must
            # have a corresponding tee node on the stack. If the stack is
            # empty here, the pipeline description is malformed and should
            # be reported with a clear error instead of raising IndexError.
            if not tee_stack:
                raise ValueError(
                    "TEE_END without corresponding tee element in pipeline description"
                )
            source_id = tee_stack.pop()
        else:
            source_id = str(node_id - 1)

        edges.append(Edge(id=str(edge_id), source=source_id, target=node_id_str))
        logger.debug(f"Adding edge: {source_id} -> {node_id_str} (id={edge_id})")
        edge_id += 1

    return edge_id


def _add_node(
    nodes: list[Node],
    edges: list[Edge],
    node_id: int,
    token: _Token,
    prev_token_kind: str | None,
    tee_stack: list[str],
    edge_id: int,
) -> int:
    """
    Append a regular element node to the graph.

    The element type is taken from token.value. Properties are added later via
    _add_property_to_last_node() as PROPERTY tokens are parsed.

    Edge logic:
        - If this is the first node (node_id == 0), no incoming edge is added.
        - Otherwise:
            * If the previous token kind was TEE_END, we pop the last tee
              node id from the stack and connect from that node.
              If the tee stack is empty in this situation, the pipeline
              syntax is inconsistent and a clear error is raised.
            * Otherwise we create a linear edge from the previous node.
        - Edge IDs are assigned from a separate monotonically increasing
          integer counter (edge_id) and stored as strings. This keeps edge
          IDs unique across the whole graph.

    Tee handling:
        - If the new node is a "tee" element, we push its id onto tee_stack
          so that subsequent tee endpoints ("t.") can connect from it.

    Args:
        nodes: List of nodes to append the new element node to (modified in place)
        edges: List of edges to append new edge to (modified in place)
        node_id: Numeric ID for the new element node
        token: Token containing the element type in token.value
        prev_token_kind: Kind of the previous token (used to determine edge source)
        tee_stack: Stack of tee node IDs for handling tee branches (modified in place if node is tee)
        edge_id: Current edge ID counter for generating unique edge IDs

    Returns:
        int: Updated edge_id counter (incremented by 1 if edge was added, unchanged otherwise)

    Raises:
        ValueError: If prev_token_kind is TEE_END but tee_stack is empty
    """
    node_id_str = str(node_id)
    logger.debug(f"Adding node {node_id_str}: type={token.value}")

    # Regular elements do not carry any special discriminator in data.
    nodes.append(Node(id=node_id_str, type=token.value, data={}))

    if node_id > 0:
        if prev_token_kind == "TEE_END":
            # A tee endpoint ("t.") was seen before this element, so we must
            # have a corresponding tee node on the stack. If the stack is
            # empty here, the pipeline description is malformed and should
            # be reported with a clear error instead of raising IndexError.
            if not tee_stack:
                raise ValueError(
                    "TEE_END without corresponding tee element in pipeline description"
                )
            source_id = tee_stack.pop()
        else:
            source_id = str(node_id - 1)

        edges.append(Edge(id=str(edge_id), source=source_id, target=node_id_str))
        logger.debug(f"Adding edge: {source_id} -> {node_id_str} (id={edge_id})")
        edge_id += 1

    if token.value == "tee":
        tee_stack.append(node_id_str)
        logger.debug(f"Tee node added to stack: {node_id_str}")

    return edge_id


def _add_property_to_last_node(nodes: list[Node], token: _Token) -> None:
    """
    Attach a key=value PROPERTY token to the most recently added node.

    The property format is assumed to be "key=value" with optional spaces
    around the '='. No additional validation is done here; invalid properties
    should be filtered earlier during tokenization or caps parsing.

    Args:
        nodes: List of nodes (the last node will receive the property)
        token: Token containing the property in "key=value" format

    Returns:
        None

    Side effects:
        - Modifies nodes[-1].data by adding the parsed key-value pair
        - Logs warning if nodes list is empty (no-op in that case)

    Example:
        If token.value is "location=/tmp/foo.mp4", this adds
        {"location": "/tmp/foo.mp4"} to the last node's data dict
    """
    if not nodes:
        logger.warning("Attempted to add property but no nodes exist")
        return

    key, value = re.split(r"\s*=\s*", token.value, maxsplit=1)
    nodes[-1].data[key] = value
    logger.debug(f"Added property to node {nodes[-1].id}: {key}={value}")


def _build_chain(
    start_id: str,
    node_by_id: dict[str, Node],
    edges_from: dict[str, list[str]],
    tee_names: dict[str, str],
    visited: set[str],
    result_parts: list[str],
) -> None:
    """
    Recursively build a pipeline description starting from a given node id.

    The function walks forward along outgoing edges (edges_from) and appends
    textual fragments to result_parts:

      - For regular element nodes:
          "type key1=value1 key2=value2"
      - For caps nodes (__node_kind="caps"):
          "type,key1=value1,key2=value2"

    When a node has multiple outgoing edges (tee branches), the first branch
    is followed inline. Additional branches are emitted using the standard
    GStreamer tee notation:

        tee name=t ! queue ! ...
        t. ! queue ! ...

    Args:
        start_id: Node ID to start building the chain from
        node_by_id: Dictionary mapping node IDs to Node objects
        edges_from: Adjacency map (node_id -> list of target node IDs)
        tee_names: Dictionary mapping tee node IDs to their names (for "t." notation)
        visited: Set of already visited node IDs (modified in place to prevent cycles)
        result_parts: List of string fragments forming the pipeline (modified in place)

    Returns:
        None (modifies result_parts and visited in place)

    Side effects:
        - Appends pipeline fragments to result_parts
        - Adds processed node IDs to visited set
        - Recursively calls itself for tee branches

    Example output fragments:
        Regular element: ["filesrc", "location=/tmp/foo.mp4", "!"]
        Caps node: ["video/x-raw,width=320,height=240", "!"]
        Tee branch: ["t.", "!", "queue", "!"]
    """
    current_id = start_id

    while current_id and current_id not in visited:
        visited.add(current_id)
        node = node_by_id.get(current_id)
        if not node:
            break

        # Determine whether this node should be rendered as a caps string.
        # We do this by inspecting the reserved "__node_kind" key inside
        # node.data instead of relying on heuristics (for example checking
        # for parentheses in the type string).
        node_kind = node.data.get(NODE_KIND_KEY)
        is_caps = node_kind == NODE_KIND_CAPS

        if is_caps:
            # For caps nodes we serialize as a single comma-separated caps string:
            #   base,key1=val1,key2=val2,...
            # We must not include any internal/private discriminator keys
            # (those starting with "__", e.g. "__node_kind", "__image_set")
            # in the serialized caps string.

            # Maintain insertion order of properties while skipping the
            # reserved keys, so that the resulting caps string is as close
            # as possible to the original (modulo whitespace).
            props_items = [
                (key, value)
                for key, value in node.data.items()
                if not key.startswith("__")
            ]

            if props_items:
                properties_str = ",".join(
                    f"{key}={value}" for key, value in props_items
                )
                result_parts.append(f"{node.type},{properties_str}")
            else:
                # Bare caps without properties: just the base type.
                result_parts.append(node.type)
        else:
            # Regular element: type followed by space-separated properties.
            # Keys starting with "__" are internal markers (e.g. "__image_set")
            # used by the graph layer for round-tripping between simple and
            # advanced views; they must never reach the GStreamer command line.
            result_parts.append(node.type)
            spec = _model_spec(node.type)
            for key, value in node.data.items():
                if key.startswith("__"):
                    continue
                # Remap the canonical in-memory key ``model`` back to the wire key
                # declared in NODE_MODEL_SPECS for this node type (e.g. ``model-path``
                # for ``gvagenai``). All other keys pass through unchanged.
                output_key = spec.model_key if key == "model" else key
                result_parts.append(f"{output_key}={value}")

        targets = edges_from.get(current_id, [])
        if not targets:
            # No outgoing edges – end of this chain.
            break

        # Separate elements/caps in the chain with '!'.
        result_parts.append("!")

        if len(targets) == 1:
            # Simple linear chain.
            current_id = targets[0]
        else:
            # Tee: follow the first branch inline, then render additional branches.
            _build_chain(
                targets[0], node_by_id, edges_from, tee_names, visited, result_parts
            )

            for target_id in targets[1:]:
                tee_name = tee_names.get(current_id, "t")
                result_parts.append(f"{tee_name}.")
                result_parts.append("!")
                _build_chain(
                    target_id,
                    node_by_id,
                    edges_from,
                    tee_names,
                    visited,
                    result_parts,
                )
            break


def _model_path_to_display_name(nodes: list[Node]) -> None:
    """
    Convert model paths in node.data["model"] into display names.

    This is used when ingesting a pipeline description so that stored graphs
    reference logical model identifiers instead of absolute filesystem paths.

    The canonical in-memory key is always ``model``, regardless of how the
    source pipeline string named it. For node types whose wire key is not
    ``model`` (see ``NODE_MODEL_SPECS``, e.g. ``gvagenai`` uses
    ``model-path``), the original wire key is read from ``node.data`` and
    then removed; the resulting display name is always stored under
    ``node.data["model"]``.

    Args:
        nodes: List of nodes to process (modified in place)

    Returns:
        None

    Side effects:
        - Modifies node.data["model"] to contain display name instead of path
        - Also converts node.data["model-proc"] if present
        - Sets empty strings if model is not found in installed models
        - Logs debug messages for each conversion

    Example:
        Input:  node.data["model"] = "/models/yolov8_license_plate_detector.xml"
        Output: node.data["model"] = "YOLOv8 License Plate Detector"
    """
    for node in nodes:
        spec = _model_spec(node.type)
        model_key = spec.model_key
        model_path = node.data.get(model_key)
        if model_path is None:
            continue

        if model_path == "":
            logger.debug(
                f"Model path is empty string for node {node.id}, skipping model lookup"
            )
            continue

        model_proc_path = node.data.get("model-proc", None)
        # Match against every supported model (installed or not) so that
        # pipelines referencing a not-yet-installed model still get a
        # resolved display name. This lets ``used_by_pipelines`` in the
        # /models endpoint stay populated regardless of install status.
        model = SupportedModelsManager().find_model_by_model_and_proc_path(
            model_path, model_proc_path, installed_only=False
        )

        # Fallback: uploaded (custom) models live in the ModelManager
        # registry, not in supported_models.yaml. Without this, advanced
        # graphs that reference an uploaded model would lose the
        # display-name on ingestion and be rejected on conversion back
        # to a runnable pipeline.
        if model is None:
            # Local import to avoid an import cycle with model_manager.
            from managers.model_manager import ModelManager

            model = ModelManager().find_uploaded_model_by_path(
                model_path, model_proc_path
            )

        if model is not None:
            # Canonical in-memory key is always ``model`` regardless of how
            # the source pipeline string named it (see NodeModelSpec).
            node.data["model"] = model.display_name
            if model_key != "model":
                node.data.pop(model_key, None)
            logger.debug(
                f"Converted model path to display name: {model_path} -> {model.display_name}"
            )
        else:
            node.data["model"] = ""
            if model_key != "model":
                node.data.pop(model_key, None)
            logger.debug(
                f"Model not found in installed models: model_path='{model_path}', model_proc_path='{model_proc_path}'"
            )

        # Remove model-proc to avoid leaking internal filesystem layout.
        node.data.pop("model-proc", None)


def _model_display_name_to_path(nodes: list[Node]) -> None:
    """
    Convert model display names in node.data["model"] back into full filesystem paths.

    This is used when converting a stored graph back into a runnable pipeline
    description. It also injects 'model-proc' immediately after 'model' when
    available so that the resulting pipeline is executable.

    Args:
        nodes: List of nodes to process (modified in place)

    Returns:
        None

    Raises:
        ValueError: If model display name is not found in installed models

    Side effects:
        - Modifies node.data["model"] to contain full path instead of display name
        - Injects node.data["model-proc"] with the model-proc file path if available
        - Logs debug messages for each conversion

    Example:
        Input:  node.data["model"] = "YOLOv8 License Plate Detector"
        Output: node.data["model"] = "/models/yolov8_license_plate_detector.xml"
                node.data["model-proc"] = "/models/yolov8_license_plate_detector.json"
    """
    for node in nodes:
        name = node.data.get("model")
        if name is None:
            continue

        # model handling
        model = SupportedModelsManager().find_installed_model_by_display_name(name)
        if not model:
            # Fallback: the display name may identify an uploaded (custom)
            # model that is tracked by ModelManager rather than the YAML
            # catalogue. Without this fallback the convert-to-advanced
            # flow would reject any pipeline referencing an uploaded
            # model, even though the UI happily lists it.
            from managers.model_manager import ModelManager

            model = ModelManager().find_installed_uploaded_model_by_display_name(name)

        if not model:
            raise ValueError(
                f"Can't find model '{name}' for {node.type}. Choose an installed model or install it first."
            )

        node.data["model"] = model.model_path_full

        spec = _model_spec(node.type)
        if spec.uses_model_proc and model.model_proc_full:
            _insert_model_proc_after_model(node, model.model_proc_full)

        logger.debug(
            f"Converted model display name to path: {name} -> {model.model_path_full}"
        )


def _insert_model_proc_after_model(node: Node, model_proc_path: str) -> None:
    """
    Insert 'model-proc' property immediately after 'model' in node.data.

    This preserves the order of properties by rebuilding the data dictionary.

    Args:
        node: Node whose data dictionary will be modified
        model_proc_path: Full path to the model-proc file

    Returns:
        None

    Side effects:
        - Rebuilds node.data to place 'model-proc' right after 'model'
        - Removes any existing 'model-proc' entry and replaces it
        - Preserves all other properties in their original order

    Example:
        Input:  node.data = {"model": "/path/to/model.xml", "device": "GPU", "model-proc": "/old/path"}
        Output: node.data = {"model": "/path/to/model.xml", "model-proc": "/new/path", "device": "GPU"}
    """
    properties: dict[str, str] = {}

    # Rebuild the dict and re-inject model-proc right after model, dropping any
    # existing model-proc so its position and value are refreshed.
    for key, value in node.data.items():
        if key == "model-proc":
            continue
        properties[key] = value
        if key == "model":
            properties["model-proc"] = model_proc_path

    # Update in place to preserve any external references to node.data
    node.data.clear()
    node.data.update(properties)


def _validate_models_supported_on_devices(nodes: list[Node]) -> None:
    """
    Validate that all (model, device) pairs in the graph are supported.

    This check is performed before converting a graph back into a pipeline
    description to fail early when a user attempts to run an unsupported
    combination.

    Args:
        nodes: List of nodes to validate

    Returns:
        None

    Raises:
        ValueError: If model name is empty (not selected)
        ValueError: If any model is not supported on its specified device

    Side effects:
        - Logs debug messages for each validated model-device pair

    Example validation:
        - Node with model="YOLOv8" and device="GPU" -> checks if YOLOv8 runs on GPU
        - If not supported -> raises ValueError with clear message
    """
    for node in nodes:
        name = node.data.get("model")
        if name is None:
            continue

        device = node.data.get("device")
        if device is None:
            continue

        if name == "":
            raise ValueError(
                f"Model name is required for {node.type}. Select a model to continue."
            )

        if not SupportedModelsManager().is_model_supported_on_device(name, device):
            # Uploaded (custom) models live in the ModelManager registry,
            # not in supported_models.yaml. They carry no
            # ``unsupported_devices`` metadata, so if the registry knows
            # the display name we treat the model as supported on every
            # device. Without this fallback convert-to-advanced would
            # reject any graph that references an uploaded model.
            from managers.model_manager import (
                ModelManager,
            )  # local import to avoid cycle

            if (
                ModelManager().find_installed_uploaded_model_by_display_name(name)
                is None
            ):
                raise ValueError(
                    f"Node {node.type}: model '{name}' is not supported on the '{device}' device"
                )

        logger.debug(f"Model '{name}' is supported on the '{device}' device")


def _input_video_path_to_display_name(nodes: list[Node]) -> None:
    """
    Convert absolute video paths into filenames for file-based source nodes.

    This ensures that stored graphs are independent of the specific
    filesystem layout and instead reference logical video names only.
    Only processes nodes that actually read from video files (filesrc, multifilesrc, urisourcebin).

    Args:
        nodes: List of nodes to process (modified in place)

    Returns:
        None

    Side effects:
        - Modifies node.data["location"] or node.data["source"] for file source nodes
        - Converts absolute paths to filenames only
        - Sets empty string if video path is not found
        - Only processes filesrc, multifilesrc, and urisourcebin node types
        - Logs debug messages for each conversion

    Example:
        Input:  node.type="filesrc", node.data["location"] = "/videos/input/sample.mp4"
        Output: node.type="filesrc", node.data["location"] = "sample.mp4"
    """
    # Only process node types that read from video files
    file_source_types = {"filesrc", "multifilesrc", "urisourcebin"}

    for node in nodes:
        if node.type not in file_source_types:
            continue
        for key in ("source", "location"):
            path = node.data.get(key)
            if path is None:
                continue

            if path == "":
                logger.debug(
                    f"Video path is empty string for node {node.id}, skipping video lookup"
                )
                continue

            if filename := VideosManager().get_video_filename(path):
                node.data[key] = filename
                logger.debug(f"Converted video path to filename: {path} -> {filename}")
            else:
                node.data[key] = ""
                logger.debug(f"Video path not found: {path}")


def _input_video_name_to_path(nodes: list[Node]) -> None:
    """
    Convert logical video filenames back into absolute paths for file-based source nodes.

    This is performed when creating a runnable pipeline description from a stored graph. Only processes nodes that actually read from video files.

    Args:
        nodes: List of nodes to process (modified in place)

    Returns:
        None

    Raises:
        ValueError: If video filename cannot be mapped to a valid path

    Side effects:
        - Modifies node.data["location"] or node.data["source"] for file source nodes
        - Converts filenames to absolute paths
        - Only processes filesrc, multifilesrc, and urisourcebin node types
        - Logs debug messages for each conversion

    Example:
        Input:  node.type="filesrc", node.data["location"] = "sample.mp4"
        Output: node.type="filesrc", node.data["location"] = "/videos/input/sample.mp4"
    """
    # Only process node types that read from video files
    file_source_types = {"filesrc", "multifilesrc", "urisourcebin"}

    for node in nodes:
        if node.type not in file_source_types:
            continue
        for key in ("source", "location"):
            name = node.data.get(key)
            if name is None:
                continue

            # Already-absolute paths (e.g. image-set ``multifilesrc``
            # location patterns like ``/images/input/uploaded/.../foo_%02d.jpg``)
            # bypass the video-name → path mapping; they are taken
            # as-is by GStreamer.
            if name.startswith("/"):
                logger.debug(f"Leaving absolute {node.type} {key} unchanged: {name}")
                continue

            path = VideosManager().get_video_path(name)
            if not path:
                raise ValueError(
                    f"Node {node.id}. {node.type}: can't map '{key}={name}' to video path"
                )

            node.data[key] = path
            logger.debug(f"Converted video filename to path: {name} -> {path}")


def _prepare_generic_input(nodes: list[Node]) -> None:
    """
    Replace source elements with a generic 'source' element.

    This function finds source elements (filesrc, multifilesrc, v4l2src, rtspsrc)
    and replaces them with a generic "source" type, preserving source information
    in standardized data attributes.

    This is called during pipeline parsing (from_pipeline_description) to store
    a UI-friendly representation.

    Args:
        nodes: List of nodes to process (modified in place)

    Returns:
        None

    Side effects:
        - Modifies node.type and node.data for source elements
        - Converts filesrc/multifilesrc to source with kind=InputKind.FILE
        - Converts v4l2src/rtspsrc to source with kind=InputKind.CAMERA
        - Adds "source" attribute with original location/device identifier

    The function adds two data attributes:
        - "kind": Type of source (InputKind.FILE | InputKind.CAMERA)
        - "source": Filename or camera identifier (video.mp4, /dev/video0, or rtsp://...)

    Example:
        Input:  node.type = "filesrc", node.data["location"] = "video.mp4"
        Output: node.type = "source", node.data = {"kind": InputKind.FILE, "source": "video.mp4"}
    """
    for node in nodes:
        # Check for file sources
        if node.type in {"filesrc", "multifilesrc"}:
            # Image-set multifilesrc nodes carry an internal marker
            # placed by ``apply_simple_view_changes``. Round-trip them
            # back to ``kind=image_set`` with the set name derived
            # from the location pattern's parent directory, so the
            # simple view stays stable across save/load cycles.
            if node.type == "multifilesrc" and _IMAGE_SET_NODE_FLAG in node.data:
                location = str(node.data.get("location", ""))
                set_name = ""
                if location:
                    # ``/images/input/uploaded/<set>/<set>_%0Nd.<ext>``
                    # -> ``<set>``.
                    set_name = os.path.basename(os.path.dirname(location))
                node.data.clear()
                node.type = "source"
                node.data["kind"] = InputKind.IMAGE_SET
                node.data["source"] = set_name
                logger.debug(
                    f"Converted image-set multifilesrc to generic source: {set_name}"
                )
                continue

            source_name = node.data.get("location", "")
            node.data.clear()
            node.type = "source"
            node.data["kind"] = InputKind.VIDEO
            node.data["source"] = source_name
            logger.debug(f"Converted file source to generic source: {source_name}")

        # Check for USB camera sources
        elif node.type == "v4l2src":
            source_name = node.data.get("device", "/dev/video0")
            node.data.clear()
            node.type = "source"
            node.data["kind"] = InputKind.CAMERA
            node.data["source"] = source_name
            logger.debug(f"Converted v4l2src to generic source (camera): {source_name}")

        # Check for RTSP camera sources
        elif node.type == "rtspsrc":
            source_name = node.data.get("location", "")
            node.data.clear()
            node.type = "source"
            node.data["kind"] = InputKind.CAMERA
            node.data["source"] = source_name
            logger.debug(f"Converted rtspsrc to generic source (camera): {source_name}")


def _labels_path_to_display_name(nodes: list[Node]) -> None:
    """
    Convert absolute labels paths into filenames for gvadetect and gvaclassify nodes.

    This ensures that stored graphs are independent of the specific
    filesystem layout and instead reference logical labels filenames only.

    Args:
        nodes: List of nodes to process (modified in place)

    Returns:
        None

    Side effects:
        - Modifies node.data["labels"] or node.data["labels-file"] for inference nodes
        - Converts absolute paths to filenames only
        - Only processes gvadetect and gvaclassify node types
        - Logs debug messages for each conversion

    Example:
        Input:  node.data["labels"] = "/labels/coco.txt"
        Output: node.data["labels"] = "coco.txt"
    """
    for node in nodes:
        if node.type not in ("gvadetect", "gvaclassify"):
            continue
        for key in ("labels", "labels-file"):
            path = node.data.get(key)
            if path is None:
                continue

            filename = labels_manager.get_filename(path)
            node.data[key] = filename
            logger.debug(f"Converted labels path to filename: {path} -> {filename}")


def _labels_name_to_path(nodes: list[Node]) -> None:
    """
    Convert logical labels filenames back into absolute paths for gvadetect and gvaclassify nodes.

    This is performed when creating a runnable pipeline description from a stored graph.

    Args:
        nodes: List of nodes to process (modified in place)

    Returns:
        None

    Raises:
        ValueError: If labels filename cannot be mapped to a valid path

    Side effects:
        - Modifies node.data["labels"] or node.data["labels-file"] for inference nodes
        - Converts filenames to absolute paths
        - Only processes gvadetect and gvaclassify node types
        - Logs debug messages for each conversion

    Example:
        Input:  node.data["labels"] = "coco.txt"
        Output: node.data["labels"] = "/labels/coco.txt"
    """
    for node in nodes:
        if node.type not in ("gvadetect", "gvaclassify"):
            continue
        for key in ("labels", "labels-file"):
            name = node.data.get(key)
            if name is None:
                continue

            if not (path := labels_manager.get_path(name)):
                raise ValueError(
                    f"Labels file '{name}' not found for {node.type} element. "
                    f"Please ensure the labels file name is correct."
                )

            node.data[key] = path
            logger.debug(f"Converted labels filename to path: {name} -> {path}")


def _module_path_to_display_name(nodes: list[Node]) -> None:
    """
    Convert absolute python module paths into filenames for gvapython nodes.

    This ensures that stored graphs are independent of the specific
    filesystem layout and instead reference logical python module filenames only.

    Args:
        nodes: List of nodes to process (modified in place)

    Returns:
        None

    Side effects:
        - Modifies node.data["module"] for gvapython nodes
        - Converts absolute paths to filenames only
        - Only processes gvapython node types
        - Logs debug messages for each conversion

    Example:
        Input:  node.data["module"] = "/scripts/custom_processing.py"
        Output: node.data["module"] = "custom_processing.py"
    """
    for node in nodes:
        if node.type != "gvapython":
            continue

        path = node.data.get("module")
        if path is None:
            continue

        filename = scripts_manager.get_filename(path)
        node.data["module"] = filename
        logger.debug(f"Converted module path to filename: {path} -> {filename}")


def _module_name_to_path(nodes: list[Node]) -> None:
    """
    Convert logical scripts filenames back into absolute paths for gvapython nodes.

    This is performed when creating a runnable pipeline description from a stored graph.

    Args:
        nodes: List of nodes to process (modified in place)

    Returns:
        None

    Raises:
        ValueError: If module filename cannot be mapped to a valid path

    Side effects:
        - Modifies node.data["module"] for gvapython nodes
        - Converts filenames to absolute paths
        - Only processes gvapython node types
        - Logs debug messages for each conversion

    Example:
        Input:  node.data["module"] = "custom_processing.py"
        Output: node.data["module"] = "/scripts/custom_processing.py"
    """
    for node in nodes:
        if node.type != "gvapython":
            continue

        name = node.data.get("module")
        if name is None:
            continue

        if not (path := scripts_manager.get_path(name)):
            raise ValueError(
                f"Module file '{name}' not found for {node.type} element. "
                f"Please verify the file name is correct and the file exists in the shared/scripts directory."
            )

        node.data["module"] = path
        logger.debug(f"Converted module filename to path: {name} -> {path}")
