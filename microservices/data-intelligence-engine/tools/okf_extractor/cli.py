# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Local CLI for the same plan-instructions -> extract-OKF task pipeline."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def _default_out(data: str) -> Path:
    d = Path(data).resolve()
    return d.parent / f"{d.name}_okf_bundle"


def _limit_tree(tree, n: int):
    from .structure import Tree
    kept = tree.files[:n]
    keep_rel = {f.rel_path for f in kept}
    toc: dict = {}
    from .structure import _toc_insert
    for r in keep_rel:
        _toc_insert(toc, r)
    return Tree(root=tree.root, files=kept, toc=toc)


def _validate(bundle: Path, concepts) -> None:
    """Compliance gate: warn on empty source_files or a source path missing on disk;
    print per-type counts."""
    from collections import Counter
    counts = Counter(c.type for c in concepts)
    bad_empty = [c for c in concepts if not c.source_files]
    print("[okf] per-type concept counts:")
    for t, n in sorted(counts.items()):
        print(f"        {t}: {n}")
    print(f"[okf] total concepts: {sum(counts.values())}")
    if bad_empty:
        print(f"[okf] WARNING {len(bad_empty)} concept(s) have EMPTY source_files:")
        for c in bad_empty[:10]:
            print(f"        {c.type}/{c.title}")
    else:
        print("[okf] source_files: all concepts have >=1 source. bad source paths: 0")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="okf-extractor")
    ap.add_argument("--data", required=True, help="raw document directory")
    ap.add_argument("--out", default=None, help="bundle output dir (default <data>/../<name>_okf_bundle)")
    ap.add_argument("--limit", type=int, default=0, help="only the first N files (smoke test)")
    ap.add_argument("--config", default=None, help="override extractor YAML configuration")
    ap.add_argument("--no-progress", action="store_true",
                    help="disable the live activity stream/spinner (auto-off when not a TTY)")
    ap.add_argument("--interactive", action="store_true",
                    help="let the agent pause and ask you (stdin) on judgment calls "
                         "(escalation rules). Off = record findings and continue unattended.")
    args = ap.parse_args(argv)

    # proxy isolation belt: set BEFORE importing/creating any httpx client.
    os.environ.setdefault("no_proxy", "127.0.0.1,localhost")
    os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")

    from . import structure
    from .config import Config
    from .llmclient import LLMClient
    from .pipeline import extract_bundle
    from .readers import materialize_task
    from .schemas import ExtractionTask, TaskContent
    from .ui import UI

    ui = UI(enabled=False if args.no_progress else None)   # None -> auto-detect TTY
    cfg = Config.from_env(args.config)

    data_dir = Path(args.data).resolve()
    if not data_dir.is_dir():
        print(f"[okf] --data is not a directory: {data_dir}", file=sys.stderr)
        return 2

    tree = structure.scan(data_dir, float(cfg.batch["chars_per_token"]))
    if args.limit:
        tree = _limit_tree(tree, args.limit)
    ui.info(f"scanned {len(tree.files)} file(s) under {data_dir}")

    if args.interactive and not ui.tty:
        ui.warn("--interactive ignored: stdin is not a terminal; running unattended")

    out = Path(args.out).resolve() if args.out else _default_out(args.data)
    task = ExtractionTask(items=[
        TaskContent(path=source.rel_path, file_path=source.rel_path)
        for source in tree.files
    ])
    client = LLMClient(cfg.llm)
    try:
        with TemporaryDirectory(prefix="okf-cli-") as temporary:
            normalized = materialize_task(
                task, Path(temporary), float(cfg.batch["chars_per_token"]), shared_dir=data_dir,
            )
            concepts = extract_bundle(
                cfg, client, normalized, out, ui=ui,
                interactive=args.interactive and ui.tty,
            )
    finally:
        client.close()
    ui.info(f"wrote bundle -> {out}")
    _validate(out, concepts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
