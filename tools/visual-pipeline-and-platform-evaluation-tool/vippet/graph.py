import copy
import logging
import os
import re
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path

from models import SupportedModelsManager
from resources import (
    get_labels_manager,
    get_public_model_proc_manager,
    get_scripts_manager,
)
from utils import generate_unique_filename
from video_encoder import ENCODER_DEVICE_CPU, ENCODER_DEVICE_GPU
from videos import OUTPUT_VIDEO_DIR, VideosManager

# Internal constant used as a placeholder type for the main output sink in the graph.
OUTPUT_PLACEHOLDER: str = "{OUTPUT_PLACEHOLDER}"

logger = logging.getLogger(__name__)
labels_manager = get_labels_manager()
scripts_manager = get_scripts_manager()
model_proc_manager = get_public_model_proc_manager()

# Configuration for Simple View: comma-separated regex patterns for visible elements.
# All elements matching these patterns will be shown in Simple View.
# All other elements (including caps nodes) will be hidden and their edges reconnected.
SIMPLE_VIEW_VISIBLE_ELEMENTS = os.environ.get(
    "SIMPLE_VIEW_VISIBLE_ELEMENTS", "*src,urisourcebin,gva*,*sink"
)

# Configuration for Simple View: comma-separated regex patterns for invisible elements.
# Elements matching these patterns will be excluded from Simple View even if they
# match SIMPLE_VIEW_VISIBLE_ELEMENTS. This allows fine-grained control over which
# elements are shown. Evaluation order: VISIBLE first, then INVISIBLE exclusions.
SIMPLE_VIEW_INVISIBLE_ELEMENTS = os.environ.get(
    "SIMPLE_VIEW_INVISIBLE_ELEMENTS",
    "gvafpscounter,gvametapublish,gvametaconvert,gvawatermark",
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
        - Replace qtdemux with tsdemux

        Returns:
            Modified Graph object with looping support

        Raises:
            ValueError: If TS file cannot be created for any video source

        Note:
            This creates a deep copy of the graph to avoid modifying the original.
            If TS file does not exist, it will be created automatically.
        """
        videos_manager = VideosManager()
        modified_graph = copy.deepcopy(self)

        for node in modified_graph.nodes:
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
            elif node.type in {"qtdemux", "matroskademux", "avidemux", "flvdemux"}:
                node.type = "tsdemux"
                logger.debug("Replaced demuxer with tsdemux for looping support")

            # Replace splitmuxsink with fakesink (no output files during looping)
            elif node.type == "splitmuxsink":
                node.data.clear()  # Clear all properties to avoid invalid args for fakesink
                node.type = "fakesink"
                logger.debug("Replaced splitmuxsink with fakesink for looping support")

        return modified_graph

    def prepare_main_output_placeholder(self) -> "Graph":
        """
        Convert default fakesink node to a main output placeholder.

        Finds fakesink nodes with name="default_output_sink" and converts them to
        "{OUTPUT_PLACEHOLDER}" type. This placeholder will be later replaced with
        the actual main output subpipeline (file output or live stream).

        Returns:
            Graph: New Graph instance with fakesink converted to placeholder

        Raises:
            ValueError: If no fakesink with name='default_output_sink' is found in the graph

        Note:
            This is used to mark the location where main output (for user viewing)
            should be inserted, distinct from intermediate output sinks that are part
            of the pipeline definition.
        """
        modified_graph = copy.deepcopy(self)
        placeholder_created = False

        for node in modified_graph.nodes:
            if (
                node.type == "fakesink"
                and node.data.get("name") == "default_output_sink"
            ):
                node.data.clear()
                node.type = OUTPUT_PLACEHOLDER
                placeholder_created = True
                logger.debug(f"Converted node {node.id} to OUTPUT_PLACEHOLDER")

        if not placeholder_created:
            raise ValueError(
                "No fakesink with name='default_output_sink' found. "
                "Please add 'fakesink name=default_output_sink' at the end of your pipeline "
                "to specify where the output should be placed."
            )

        return modified_graph

    def prepare_intermediate_output_sinks(self) -> tuple["Graph", list[str]]:
        """
        Prepare intermediate output sink nodes with unique filenames in the output directory.

        This method handles intermediate/simulation output sinks (e.g., video recorder simulation)
        that are part of the pipeline definition. These are distinct from main output sinks
        which replace fakesink elements for user viewing (live stream or file output).

        Returns:
            tuple: (Graph object with updated sink nodes, list of intermediate output file paths)

        Iterates through all sink nodes in the pipeline graph, generates unique filenames with
        timestamp and random suffix, updates the location to the output directory, and collects
        the output paths.
        """
        output_paths: list[str] = []

        for node in self.nodes:
            # Check if node is a sink type
            if not node.type.endswith("sink"):
                continue

            # Check if location key exists
            location = node.data.get("location")
            if not location:
                continue

            # Create new filename with timestamp and suffix
            new_filename = generate_unique_filename(location)

            # Construct new full path
            new_path = str(Path(OUTPUT_VIDEO_DIR) / new_filename)

            # Update node's location
            node.data["location"] = new_path

            # Add to output paths list
            output_paths.append(new_path)

            logger.debug(f"Updated sink node {node.id}: {location} -> {new_path}")

        return self, output_paths

    def get_input_video_filenames(self) -> list[str]:
        """
        Retrieve a list of input video filenames from source nodes in the graph.

        Returns:
            list[str]: List of input video filenames

        This intentionally skips sink nodes to avoid collecting output paths.
        """
        input_filenames: list[str] = []

        for node in self.nodes:
            if node.type.endswith("sink"):
                # Skip sinks to avoid overwriting output paths
                continue
            for key in ("source", "location"):
                filename = node.data.get(key)
                if filename is None:
                    continue
                input_filenames.append(filename)

        return input_filenames

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

        Algorithm:
          1. Identify which nodes should be visible based on SIMPLE_VIEW_VISIBLE_ELEMENTS patterns
          2. Build a mapping of edges to traverse through hidden nodes
          3. Create new graph with only visible nodes
          4. Reconnect edges: if A→hidden→hidden→B, create direct edge A→B
          5. Handle tee branches: preserve branching structure even when tee itself is hidden

        Important invariants:
          * Visible node IDs are preserved from the original graph
          * Edge IDs are regenerated sequentially in the new graph
          * Caps nodes (marked with __node_kind="caps") are always hidden
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
        simple_nodes = [node for node in self.nodes if node.id in visible_node_ids]
        simple_nodes.sort(key=lambda node: int(node.id))

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
          6. Return new advanced graph with updated properties

        Note: Only property modifications of existing visible nodes are supported.
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

        logger.debug(
            f"Successfully applied changes from simple view to advanced view. "
            f"Modified {len(modified_node_ids_with_changes)} nodes."
        )

        return result_advanced


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
        # Property in key=value format (no commas here; caps are handled separately)
        ("PROPERTY", r"\S+\s*=\s*\S+"),
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
            # We must not include the internal "__node_kind" discriminator
            # in the serialized caps string.

            # Maintain insertion order of properties while skipping the
            # reserved key, so that the resulting caps string is as close
            # as possible to the original (modulo whitespace).
            props_items = [
                (key, value) for key, value in node.data.items() if key != NODE_KIND_KEY
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
            result_parts.append(node.type)
            for key, value in node.data.items():
                result_parts.append(f"{key}={value}")

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
        model_path = node.data.get("model")
        if model_path is None:
            continue

        model_proc_path = node.data.get("model-proc", None)
        model = SupportedModelsManager().find_installed_model_by_model_and_proc_path(
            model_path, model_proc_path
        )

        if model is not None:
            node.data["model"] = model.display_name
            logger.debug(
                f"Converted model path to display name: {model_path} -> {model.display_name}"
            )
        else:
            node.data["model"] = ""
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
            raise ValueError(
                f"Can't find model '{name}' for {node.type}. Choose an installed model or install it first."
            )

        node.data["model"] = model.model_path_full

        if model.model_proc_full:
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
            raise ValueError(
                f"Node {node.type}: model '{name}' is not supported on the '{device}' device"
            )

        logger.debug(f"Model '{name}' is supported on the '{device}' device")


def _input_video_path_to_display_name(nodes: list[Node]) -> None:
    """
    Convert absolute video paths into filenames for all non-sink nodes.

    This ensures that stored graphs are independent of the specific
    filesystem layout and instead reference logical video names only.

    Args:
        nodes: List of nodes to process (modified in place)

    Returns:
        None

    Side effects:
        - Modifies node.data["source"] or node.data["location"] for non-sink nodes
        - Converts absolute paths to filenames only
        - Sets empty string if video path is not found
        - Skips sink nodes to preserve output paths
        - Logs debug messages for each conversion

    Example:
        Input:  node.data["location"] = "/videos/input/sample.mp4"
        Output: node.data["location"] = "sample.mp4"
    """
    for node in nodes:
        if node.type.endswith("sink"):
            # Skip sinks to avoid overwriting output paths
            continue
        for key in ("source", "location"):
            path = node.data.get(key)
            if path is None:
                continue

            if filename := VideosManager().get_video_filename(path):
                node.data[key] = filename
                logger.debug(f"Converted video path to filename: {path} -> {filename}")
            else:
                node.data[key] = ""
                logger.debug(f"Video path not found: {path}")


def _input_video_name_to_path(nodes: list[Node]) -> None:
    """
    Convert logical video filenames back into absolute paths for non-sink nodes.

    This is performed when creating a runnable pipeline description from a
    stored graph. Sink nodes are intentionally skipped so that their output
    locations can be overridden by the caller if needed.

    Args:
        nodes: List of nodes to process (modified in place)

    Returns:
        None

    Raises:
        ValueError: If video filename cannot be mapped to a valid path

    Side effects:
        - Modifies node.data["source"] or node.data["location"] for non-sink nodes
        - Converts filenames to absolute paths
        - Skips sink nodes to preserve output paths
        - Logs debug messages for each conversion

    Example:
        Input:  node.data["location"] = "sample.mp4"
        Output: node.data["location"] = "/videos/input/sample.mp4"
    """
    for node in nodes:
        if node.type.endswith("sink"):
            # Skip sinks to avoid overwriting output paths
            continue
        for key in ("source", "location"):
            name = node.data.get(key)
            if name is None:
                continue

            path = VideosManager().get_video_path(name)
            if not path:
                raise ValueError(
                    f"Node {node.id}. {node.type}: can't map '{key}={name}' to video path"
                )

            node.data[key] = path
            logger.debug(f"Converted video filename to path: {name} -> {path}")


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
