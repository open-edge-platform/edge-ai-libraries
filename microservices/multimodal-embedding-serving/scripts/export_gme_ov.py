#!/usr/bin/env python3
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Export GME to the OpenVINO package the service loads.

This runs the same export the service performs on first start, so a package
can be prepared ahead of time, for example on a machine with Hugging Face
access. GME_PRECISION selects the precision, as it does for the service, and
the package is written to the directory the service looks for:

    GME_PRECISION=int8 (default)  -> <output-dir>/gme-qwen2-vl-2b-instruct-openvino
    GME_PRECISION=int4            -> <output-dir>/gme-qwen2-vl-2b-instruct-openvino-int4
    GME_PRECISION=fp32            -> <output-dir>/gme-qwen2-vl-2b-instruct-openvino-fp32

Run from the microservice root (``/app`` in the service image):

    GME_PRECISION=int4 python scripts/export_gme_ov.py \\
        --checkpoint ./gme-Qwen2-VL-2B-Instruct --output-dir ./gme-ov
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models.config import MODEL_CONFIGS  # noqa: E402
from src.models.gme_export import export_package, package_dir_name, resolve_precision  # noqa: E402

MODEL = MODEL_CONFIGS["GME"]["gme-qwen2-vl-2b-instruct"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--checkpoint",
        help="local directory with the original Hugging Face checkpoint; "
        "if omitted, the checkpoint is downloaded from the Hugging Face Hub",
    )
    parser.add_argument("--output-dir", type=Path, required=True, help="directory to write the package into")
    args = parser.parse_args()

    try:
        precision = resolve_precision()
    except ValueError as exc:
        parser.error(str(exc))
    if args.checkpoint and not Path(args.checkpoint).is_dir():
        parser.error(f"checkpoint directory not found: {args.checkpoint}")
    package = args.output_dir / package_dir_name(MODEL["package_dir"], precision)
    if package.exists():
        parser.error(f"{package} already exists; remove it or choose another --output-dir")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    source = args.checkpoint or MODEL["hf_model_id"]
    revision = None if args.checkpoint else MODEL.get("revision")
    export_package(source, package, precision, revision)
    print(f"GME OpenVINO package ({precision}): {package}")


if __name__ == "__main__":
    main()
