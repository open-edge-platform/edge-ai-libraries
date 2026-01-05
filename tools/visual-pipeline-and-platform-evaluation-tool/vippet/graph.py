import logging
import re
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path

from utils import generate_unique_filename
from videos import get_videos_manager, OUTPUT_VIDEO_DIR
from models import get_supported_models_manager
from resources import (
    get_labels_manager,
    get_scripts_manager,
    get_public_model_proc_manager,
)

logger = logging.getLogger(__name__)
models_manager = get_supported_models_manager()
videos_manager = get_videos_manager()
labels_manager = get_labels_manager()
scripts_manager = get_scripts_manager()
model_proc_manager = get_public_model_proc_manager()


# Internal reserved key used to mark special node kinds inside Node.data.
# We cannot extend the public Node schema with a new top-level field, so we
# store this discriminator as a synthetic property that the frontend can treat
# in a special way.
NODE_KIND_KEY = "__node_kind"
NODE_KIND_CAPS = "caps"


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

        The resulting structure is compatible with the public API schema.
        Using asdict() here ensures all dataclass fields are serialized consistently.
        """
        return asdict(self)

    @staticmethod
    def from_pipeline_description(pipeline_description: str) -> "Graph":
        """
        Parse a GStreamer-like pipeline description string into a Graph.

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

        # Work on a shallow copy of nodes so we do not mutate the original
        # graph stored in the database.
        nodes = self.nodes[:]
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

    def prepare_output_sinks(self) -> tuple["Graph", list[str]]:
        """
        Prepare output sink nodes with unique filenames in the output directory.

        Iterates through all sink nodes, generates unique filenames with
        timestamp and random suffix, updates the location to the output
        directory, and collects the output paths.

        Note: This is used only during pipeline execution preparation and does
        not affect the original graph stored in the database.

        Returns:
            tuple: (Graph object with updated sink nodes, list of output file paths)
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

        This intentionally skips sink nodes to avoid collecting output paths.

        Returns:
            list: List of input video filenames.
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

    In that case we return:
        (caps_base, {key1: value1, key2: value2, ...})

    If the segment does not contain a comma at all, it is *never* treated as
    caps and we return None. This means that:
        - "video/x-raw(memory:NVMM)" is a regular element, not caps.
        - "video/x-raw" is a regular element.
        - "weird/no_comma" is a regular element.

    If the segment contains commas but any of the trailing parts is not a
    valid "key=value" pair (or has an empty key or value), we raise ValueError.

    Examples treated as caps:
        "video/x-raw(memory:VAMemory),width=320,height=240"
        "video/x-raw,width=320,height=240"
        "video/x-raw(memory:NVMM),format=UYVY,width=2592,height=1944,framerate=28/1"
        "video/x-raw,format=(string)UYVY,width=(int)2592,height=(int)1944,framerate=(fraction)28/1"

    Examples treated as non-caps (return None, later parsed as elements):
        "video/x-raw(memory:NVMM)"
        "video/x-raw"
        "weird/no_comma"
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

    visited is used to guard against infinite recursion on malformed graphs.
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
    """
    for node in nodes:
        path = node.data.get("model")
        if path is None:
            continue

        for part in Path(path).with_suffix("").parts:
            if model := models_manager.find_installed_model_by_name(part):
                node.data["model"] = model.display_name
                logger.debug(
                    f"Converted model path to display name: {path} -> {model.display_name}"
                )

                # Also convert model-proc if present
                model_proc_path = node.data.get("model-proc")
                if model_proc_path is not None:
                    node.data["model-proc"] = model_proc_manager.get_filename(
                        model_proc_path
                    )
                break
        else:
            node.data["model"] = ""
            node.data["model-proc"] = ""
            logger.debug(f"Model path not found in installed models: {path}")


def _model_display_name_to_path(nodes: list[Node]) -> None:
    """
    Convert model display names in node.data["model"] back into full filesystem paths.

    This is used when converting a stored graph back into a runnable pipeline
    description. It also injects 'model-proc' immediately after 'model' when
    available so that the resulting pipeline is executable.
    """
    for node in nodes:
        name = node.data.get("model")
        if name is None:
            continue

        # model handling
        model = models_manager.find_installed_model_by_display_name(name)
        if not model:
            raise ValueError(
                f"Can't find model '{name}' for {node.type}. Choose an installed model or install it first."
            )

        node.data["model"] = model.model_path_full

        # model-proc handling
        configured_model_proc = node.data.get("model-proc")
        default_model_proc = (
            model_proc_manager.get_filename(model.model_proc)
            if model.model_proc is not None
            else None
        )

        # If a model-proc was explicitly configured and is different from
        # the default, use it. Otherwise, inject the default if available.
        if (
            configured_model_proc is not None
            and configured_model_proc != default_model_proc
        ):
            # Use the user-specified model-proc
            model_proc_path = model_proc_manager.get_path(configured_model_proc)
            if model_proc_path is None:
                raise ValueError(
                    f"Model-proc file '{configured_model_proc}' not found for {node.type} element. "
                    f"Please verify the file name is correct or leave it empty to use the default."
                )

            _insert_model_proc_after_model(node, model_proc_path)
        else:
            # Use the default model-proc if available
            if model.model_proc_full:
                _insert_model_proc_after_model(node, model.model_proc_full)
        logger.debug(
            f"Converted model display name to path: {name} -> {model.model_path_full}"
        )


def _insert_model_proc_after_model(node: Node, model_proc_path: str) -> None:
    """
    Insert 'model-proc' property immediately after 'model' in node.data.

    This preserves the order of properties by rebuilding the data dictionary.
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

        if not models_manager.is_model_supported_on_device(name, device):
            raise ValueError(
                f"Node {node.type}: model '{name}' is not supported on the '{device}' device"
            )

        logger.debug(f"Model '{name}' is supported on the '{device}' device")


def _input_video_path_to_display_name(nodes: list[Node]) -> None:
    """
    Convert absolute video paths into filenames for all non-sink nodes.

    This ensures that stored graphs are independent of the specific
    filesystem layout and instead reference logical video names only.
    """
    for node in nodes:
        if node.type.endswith("sink"):
            # Skip sinks to avoid overwriting output paths
            continue
        for key in ("source", "location"):
            path = node.data.get(key)
            if path is None:
                continue

            if filename := videos_manager.get_video_filename(path):
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
    """
    for node in nodes:
        if node.type.endswith("sink"):
            # Skip sinks to avoid overwriting output paths
            continue
        for key in ("source", "location"):
            name = node.data.get(key)
            if name is None:
                continue

            path = videos_manager.get_video_path(name)
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
