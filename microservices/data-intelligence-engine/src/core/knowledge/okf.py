# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""OKF concept bundles: parsing markdown "OKF" files into concept nodes.

Ported from edgecraftrag/components/data.py (OKFNode + File.convert_file_to_okf_nodes).
An OKF bundle is a directory of markdown files, one per concept, with YAML
frontmatter (``type``, ``title``, ``status``, ``source_files`` /
``source_chunk_ids``, ``links``) plus a body whose markdown links encode the
relations between concepts. The ``index.md`` file (if present) is an index, not
a concept, and is skipped.

An ``OKFNode`` here is a plain dataclass, not a llama-index node: the graph
projection consumes its ``cid`` / ``ctype`` / ``links`` / ``source_chunk_ids``
directly, and the seeders embed ``title`` + ``body``. Nothing in the graph path
needs the assembled display ``text`` the old ``TextNode`` carried, so it is
deliberately absent.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

import config

OKF_TYPE_DIR = {
    "Person": "people",
    "Customer": "customers",
    "TechChoice": "tech",
    "Decision": "decisions",
    "Issue": "issues",
    "Artifact": "artifacts",
    "Event": "events",
}

_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)(?:\s*[—–-]\s*(\S+))?")


@dataclass
class OKFNode:
    """One OKF concept, as parsed from its markdown file."""

    ctype: str = ""
    title: str = ""
    okf_file_path: str = ""
    status: Optional[str] = None
    source_files: List[str] = field(default_factory=list)
    source_chunk_ids: List[str] = field(default_factory=list)
    summaries: List[Tuple[str, str]] = field(default_factory=list)
    links: List[Tuple[str, str]] = field(default_factory=list)
    body: str = ""

    @property
    def cid(self) -> str:
        """The concept id: type-dir prefix + slug(title)."""
        prefix = OKF_TYPE_DIR.get(self.ctype, self.ctype.lower() or "concepts")
        return f"{prefix}/{_slug(self.title)}"


# --- link parsing --------------------------------------------------------------


def _body_links(body: str, md_path: Path, bundle_dir: Path) -> List[Tuple[str, str]]:
    """Markdown links in the body as ``(target, relation)`` pairs.

    A bare relative target resolves to another concept file in the bundle
    (relative path, suffix stripped); an external ``://`` link is kept verbatim.
    """
    pairs = []
    for target, relation in _LINK_RE.findall(body):
        if "://" in target:
            target_id = target
        else:
            try:
                target_id = (
                    (md_path.parent / target)
                    .resolve()
                    .relative_to(bundle_dir.resolve())
                    .with_suffix("")
                    .as_posix()
                )
            except ValueError:
                target_id = target
        pairs.append((target_id, relation or "related"))
    return list(dict.fromkeys(pairs))


def _frontmatter_links(metadata: Dict[str, Any]) -> List[Tuple[str, str]]:
    pairs = []
    for item in metadata.get("links") or []:
        if not isinstance(item, dict) or not item.get("to"):
            continue
        pairs.append((str(item["to"]), str(item.get("rel") or "related")))
    return list(dict.fromkeys(pairs))


def _strip_source_marker(summary: str) -> str:
    """Drop a summary bullet's trailing source annotation.

    The marker set is deployment config (``config.OKF_SUMMARY_SOURCE_MARKERS``),
    so a non-Chinese bundle can use ``(source:`` in place of the full-width
    ``（来源：`` default. The earliest-occurring marker wins.
    """
    cut = len(summary)
    for marker in config.OKF_SUMMARY_SOURCE_MARKERS:
        index = summary.find(marker)
        if index != -1:
            cut = min(cut, index)
    return summary[:cut]


def _slug(title: str) -> str:
    value = title.strip().lower()
    value = re.sub(r"[\s/\\]+", "-", value)
    value = re.sub(r"[^\w一-鿿-]", "", value)
    return value.strip("-") or "unnamed"


# --- parsing -------------------------------------------------------------------


def _parse_okf_node(file_path: Path, bundle_dir: Optional[Path] = None) -> OKFNode:
    import yaml  # local: OKF-only dependency

    text = file_path.read_text(encoding="utf-8")
    frontmatter = ""
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            frontmatter, body = parts[1], parts[2]
    metadata = yaml.safe_load(frontmatter) or {}
    root = bundle_dir or file_path.parent
    try:
        relative_path = file_path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        relative_path = file_path.name
    node = OKFNode(
        ctype=str(metadata.get("type") or ""),
        title=str(metadata.get("title") or ""),
        okf_file_path=f"/{relative_path}",
    )
    node.status = metadata.get("status")
    node.body = body.strip()
    node.source_files = [str(item) for item in metadata.get("source_files") or []]
    node.source_chunk_ids = [
        str(item) for item in metadata.get("source_chunk_ids") or []
    ]
    node.links = list(
        dict.fromkeys(
            [
                *_frontmatter_links(metadata),
                *_body_links(body, file_path, bundle_dir or file_path.parent),
            ]
        )
    )
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            break
        if line.startswith("- "):
            summary = _strip_source_marker(line[2:]).strip()
            if summary:
                node.summaries.append((summary, ""))
    return node


def _bundle_root(md_path: Path, top: Path) -> Path:
    """The bundle a concept file belongs to: the nearest folder (up to `top`)
    holding an ``index.md``, else `top`.

    Links and ``okf_file_path`` are relative to the bundle root, and a concept id
    is ``<type dir>/<slug>`` with no folder above that. Resolving against a
    folder that merely *contains* the bundle (an upload of ``dossier/`` around
    ``dossier/okf_bundle_v2/``) would prefix every link target with the bundle's
    folder name, so no link would ever meet the concept it names.
    """
    top = top.resolve()
    folder = md_path.resolve().parent
    while True:
        if (folder / "index.md").is_file():
            return folder
        if folder == top or top not in folder.parents:
            return top
        folder = folder.parent


def parse_okf_bundle(file_path: Path) -> List[OKFNode]:
    """Every concept in an OKF bundle (a directory, or one markdown file).

    ``index.md`` is the bundle index, not a concept, so it is skipped.
    """
    path = Path(file_path)
    paths = sorted(path.rglob("*.md")) if path.is_dir() else [path]
    bundle_dir = path if path.is_dir() else path.parent
    nodes = [
        _parse_okf_node(md, _bundle_root(md, bundle_dir))
        for md in paths
        if md.name != "index.md"
    ]
    if not nodes:
        raise ValueError(f"No OKF concept files found: {file_path}")
    # Producers may use `person/` while a canonical Person cid uses `people/`,
    # or slug a free-text type such as "Care Plan". Resolve physical bundle
    # targets to the parsed concepts' actual ids instead of assuming equality.
    ids_by_path = {
        Path(node.okf_file_path.lstrip("/")).with_suffix("").as_posix(): node.cid
        for node in nodes
    }
    for node in nodes:
        node.links = list(dict.fromkeys(
            (ids_by_path.get(target, target), relation) for target, relation in node.links
        ))
    return nodes


def _looks_like_okf(md_path: Path) -> bool:
    import yaml  # local: OKF-only dependency

    try:
        text = md_path.read_text(encoding="utf-8")
    except OSError:
        return False
    if not text.startswith("---"):
        return False
    parts = text.split("---", 2)
    if len(parts) != 3:
        return False
    try:
        metadata = yaml.safe_load(parts[1]) or {}
    except Exception:
        return False
    return bool(metadata.get("type")) and bool(metadata.get("title"))


def is_okf(path) -> bool:
    """Whether `path` is an OKF bundle: a directory holding OKF concept markdown
    (or an ``index.md``), or a single markdown file with OKF frontmatter."""
    path = Path(path)
    if path.is_dir():
        for md in path.rglob("*.md"):
            if md.name == "index.md" or _looks_like_okf(md):
                return True
        return False
    return path.suffix.lower() == ".md" and _looks_like_okf(path)


# --- provenance resolution -----------------------------------------------------


def resolve_source_chunk_ids(
    concepts: List[OKFNode], chunk_nodes: List[Any], source_root: Path
) -> None:
    """Fill ``source_chunk_ids`` from ``source_files``, mirroring edgecraftrag's
    ``OKFNode.resolve_source_chunk_ids``.

    Matches each chunk node's ``file_path`` metadata against the concept's
    ``source_files`` (relative to ``source_root``). Concepts that carry
    ``source_files`` always have their ``source_chunk_ids`` recomputed from them,
    so re-chunking a document replaces the ids; concepts without ``source_files``
    are left alone (a hand-written ``source_chunk_ids`` survives, or stays empty).
    """
    chunk_ids_by_source: Dict[str, List[str]] = {}
    for chunk_node in chunk_nodes:
        file_path = (chunk_node.metadata or {}).get("file_path")
        if not file_path:
            continue
        try:
            relative_path = Path(file_path).relative_to(source_root).as_posix()
        except ValueError:
            continue
        chunk_ids_by_source.setdefault(relative_path, []).append(chunk_node.node_id)

    for concept in concepts:
        if not concept.source_files:
            continue
        missing = [sf for sf in concept.source_files if sf not in chunk_ids_by_source]
        if missing:
            raise ValueError(f"OKF sources have no matching chunks: {missing}")
        concept.source_chunk_ids = [
            cid for sf in concept.source_files for cid in chunk_ids_by_source[sf]
        ]


def resolve_task_source_chunk_ids(
    concepts: List[OKFNode], chunk_nodes: List[Any], source_assets: Mapping[str, str],
) -> None:
    """Resolve portable task source names by asset id, not machine-local paths.

    Extraction tasks can contain inline documents and duplicate basenames. The
    client-written task manifest maps their unique logical paths to asset IDs;
    vector chunks already carry these IDs, even after restart or re-chunking.
    """
    chunks_by_asset: Dict[str, List[str]] = {}
    for chunk in chunk_nodes:
        asset_id = str((chunk.metadata or {}).get("asset_id") or "")
        if asset_id:
            chunks_by_asset.setdefault(asset_id, []).append(chunk.node_id)
    for concept in concepts:
        if not concept.source_files:
            raise ValueError("Extracted OKF concepts must cite task source_files")
        missing = [path for path in concept.source_files if path not in source_assets]
        if missing:
            raise ValueError(f"Extracted OKF cites unknown task sources: {missing}")
        asset_ids = [source_assets[path] for path in concept.source_files]
        missing_assets = [asset_id for asset_id in asset_ids if not chunks_by_asset.get(asset_id)]
        if missing_assets:
            raise ValueError(f"Extracted OKF sources have no matching chunks: {missing_assets}")
        concept.source_chunk_ids = list(dict.fromkeys(
            chunk_id for asset_id in asset_ids for chunk_id in chunks_by_asset[asset_id]
        ))
