#!/usr/bin/env python3
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Export a GME model to the OpenVINO package the service loads.

This runs the same export the service performs on first start, so a package
can be prepared ahead of time, for example on a machine with Hugging Face
access. The package is written to ``<output-dir>/<package dir>``, using the
directory name and weight format registered for ``--model``:

    GME/gme-qwen2-vl-2b-instruct       -> gme-qwen2-vl-2b-instruct-openvino (INT8)
    GME/gme-qwen2-vl-2b-instruct-int4  -> gme-qwen2-vl-2b-instruct-openvino-int4 (INT4)

Run from the microservice root (``/app`` in the service image):

    python scripts/export_gme_ov.py --checkpoint ./gme-Qwen2-VL-2B-Instruct --output-dir ./gme-ov
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models.config import MODEL_CONFIGS, resolve_model_id  # noqa: E402
from src.models.gme_export import export_package  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--model",
        default="GME/gme-qwen2-vl-2b-instruct",
        help="registered GME model ID (default: %(default)s)",
    )
    parser.add_argument(
        "--checkpoint",
        help="local directory with the original Hugging Face checkpoint; "
        "if omitted, the checkpoint is downloaded from the Hugging Face Hub",
    )
    parser.add_argument("--output-dir", type=Path, required=True, help="directory to write the package into")
    args = parser.parse_args()

    try:
        model_type, model_name = resolve_model_id(args.model).split("/", 1)
    except ValueError as exc:
        parser.error(str(exc))
    if model_type != "GME":
        parser.error(f"{args.model} is not a GME model")
    if args.checkpoint and not Path(args.checkpoint).is_dir():
        parser.error(f"checkpoint directory not found: {args.checkpoint}")
    config = MODEL_CONFIGS[model_type][model_name]
    package = args.output_dir / config["package_dir"]
    if package.exists():
        parser.error(f"{package} already exists; remove it or choose another --output-dir")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    source = args.checkpoint or config["hf_model_id"]
    revision = None if args.checkpoint else config.get("revision")
    export_package(source, package, config["weight_format"], revision)
    print(f"GME OpenVINO package: {package}")


if __name__ == "__main__":
    main()
