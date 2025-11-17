import logging
import re
import uuid
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from videos import get_videos_manager

from models import get_supported_models_manager

logger = logging.getLogger(__name__)
models_manager = get_supported_models_manager()
videos_manager = get_videos_manager()


@dataclass
class Node:
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
        nodes = [
            Node(id=node["id"], type=node["type"], data=node["data"])
            for node in data["nodes"]
        ]
        edges = [
            Edge(id=edge["id"], source=edge["source"], target=edge["target"])
            for edge in data["edges"]
        ]

        return Graph(nodes=nodes, edges=edges)

    def to_dict(self) -> dict[str, list[dict[str, str | dict[str, str]]]]:
        return asdict(self)

    @staticmethod
    def from_pipeline_description(pipeline_description: str) -> "Graph":
        logger.debug(f"Parsing pipeline description: {pipeline_description}")

        nodes: list[Node] = []
        edges: list[Edge] = []

        tee_stack: list[str] = []
        prev_token_kind: str | None = None

        elements = pipeline_description.split("!")

        for node_id, element in enumerate(elements):
            for token in _tokenize(element):
                match token.kind:
                    case "TYPE":
                        _add_node(
                            nodes, edges, node_id, token, prev_token_kind, tee_stack
                        )
                    case "PROPERTY":
                        _add_property_to_last_node(nodes, token)
                    case "MISMATCH":
                        raise ValueError(
                            f"Unrecognized token in pipeline description: '{token.value}' (element: '{element.strip()}')"
                        )
                    # CAPSFILTER is pre-processed in _tokenize() and handled as regular type with properties
                    # TEE_END handled in _add_node()
                    # SKIP doesn't need handling

                prev_token_kind = token.kind

        _model_path_to_display_name(nodes)
        _video_path_to_display_name(nodes)

        logger.debug(f"Nodes:\n{nodes}")
        logger.debug(f"Edges:\n{edges}")

        return Graph(nodes, edges)

    def to_pipeline_description(self) -> str:
        if not self.nodes:
            raise ValueError("Empty graph, cannot convert to pipeline description")

        logger.debug("Converting graph to pipeline description")
        logger.debug(f"Nodes:\n{self.nodes}")
        logger.debug(f"Edges:\n{self.edges}")

        nodes = self.nodes[:]
        _model_display_name_to_path(nodes)
        _video_name_to_path(nodes)

        nodes_by_id = {node.id: node for node in nodes}

        edges_from: dict[str, list[str]] = defaultdict(list)
        for edge in self.edges:
            edges_from[edge.source].append(edge.target)

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

        for start_id in sorted(start_nodes):
            if start_id not in visited:
                _build_chain(
                    start_id, nodes_by_id, edges_from, tee_names, visited, result_parts
                )

        pipeline_description = " ".join(result_parts)
        logger.info(f"Generated pipeline description: {pipeline_description}")

        return pipeline_description


@dataclass
class _Token:
    kind: str | None
    value: str


def _tokenize(element: str) -> Iterator[_Token]:
    token_specification = [
        # Capsfilter with optional properties
        ("CAPSFILTER", r"\S+\([^)]*\)(?:,\S+=\S+)+"),
        # Property in key=value format
        ("PROPERTY", r"\S+\s*=\s*\S+"),
        # End of tee
        ("TEE_END", r"\S+\.(?:\s|\Z)"),
        # Type of element
        ("TYPE", r"\S+"),
        # Skip over whitespace
        ("SKIP", r"\s+"),
        # Any other character
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

        # Handle capsfilter with comma-separated properties
        if kind == "CAPSFILTER":
            # Find where properties start (after first comma following closing paren)
            paren_close_idx = value.rfind(")")
            comma_idx = value.find(",", paren_close_idx)

            # Split into type and properties
            type_part = value[:comma_idx]
            props_part = value[comma_idx + 1 :]

            yield _Token("TYPE", type_part)

            # Split comma-separated properties
            for prop in props_part.split(","):
                prop = prop.strip()
                if "=" in prop:
                    yield _Token("PROPERTY", prop)
        else:
            yield _Token(kind, value)


def _add_node(
    nodes: list[Node],
    edges: list[Edge],
    node_id: int,
    token: _Token,
    prev_token_kind: str | None,
    tee_stack: list[str],
) -> None:
    node_id_str = str(node_id)
    logger.debug(f"Adding node {node_id_str}: type={token.value}")

    nodes.append(Node(id=node_id_str, type=token.value, data={}))

    if node_id > 0:
        source_id = (
            tee_stack.pop() if prev_token_kind == "TEE_END" else str(node_id - 1)
        )
        edges.append(Edge(id=str(node_id - 1), source=source_id, target=node_id_str))
        logger.debug(f"Adding edge: {source_id} -> {node_id_str}")

    if token.value == "tee":
        tee_stack.append(node_id_str)
        logger.debug(f"Tee node added to stack: {node_id_str}")


def _add_property_to_last_node(nodes: list[Node], token: _Token) -> None:
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
    current_id = start_id

    while current_id and current_id not in visited:
        visited.add(current_id)
        node = node_by_id.get(current_id)
        if not node:
            break

        # Check if this is a capsfilter (contains parentheses in type)
        is_capsfilter = "(" in node.type

        if is_capsfilter and node.data:
            # For capsfilters, append type and properties as comma-separated
            properties_str = ",".join(
                f"{key}={value}" for key, value in node.data.items()
            )
            result_parts.append(f"{node.type},{properties_str}")
        else:
            # For regular elements, append type and properties separately (space-separated)
            result_parts.append(node.type)
            for key, value in node.data.items():
                result_parts.append(f"{key}={value}")

        targets = edges_from.get(current_id, [])
        if not targets:
            break

        result_parts.append("!")

        if len(targets) == 1:
            current_id = targets[0]
        else:
            _build_chain(
                targets[0], node_by_id, edges_from, tee_names, visited, result_parts
            )

            for target_id in targets[1:]:
                tee_name = tee_names.get(current_id, "t")
                result_parts.append(f"{tee_name}.")
                result_parts.append("!")
                _build_chain(
                    target_id, node_by_id, edges_from, tee_names, visited, result_parts
                )
            break


def _model_path_to_display_name(nodes: list[Node]) -> None:
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
                break
        else:
            node.data["model"] = ""
            logger.debug(f"Model path not found in installed models: {path}")

        node.data.pop("model-proc", None)


def _model_display_name_to_path(nodes: list[Node]) -> None:
    for node in nodes:
        name = node.data.get("model")
        if name is None:
            continue

        model = models_manager.find_installed_model_by_display_name(name)
        if not model:
            raise ValueError(
                f"Node {node.id}. {node.type}: can't map '{name}' to installed model"
            )

        node.data["model"] = model.model_path_full

        if model.model_proc_full:
            # Insert 'model-proc' immediately after 'model'
            properties = {}
            for key, value in node.data.items():
                properties[key] = value
                if key == "model":
                    properties["model-proc"] = model.model_proc_full

            node.data = properties

        logger.debug(
            f"Converted model display name to path: {name} -> {model.model_path_full}"
        )


def _video_path_to_display_name(nodes: list[Node]) -> None:
    for node in nodes:
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


def _video_name_to_path(nodes: list[Node]) -> None:
    for node in nodes:
        for key in ("source", "location"):
            name = node.data.get(key)
            if name is None:
                continue

            path = videos_manager.get_video_path(name)
            if not path:
                # FIXME
                # Generate output path as a workaround to run pipeline.
                # In the long term this should be managed by instance manager
                if node.type.endswith("sink") and key == "location":
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    suffix = uuid.uuid4().hex[0:6]
                    path = f"/tmp/vippet_{timestamp}_{suffix}.mp4"
                else:
                    raise ValueError(
                        f"Node {node.id}. {node.type}: can't map '{key}={name}' to video path"
                    )

            node.data[key] = path
            logger.debug(f"Converted video filename to path: {name} -> {path}")
