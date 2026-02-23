# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import argparse
import os
import sys
import tarfile
import urllib.request
from pathlib import Path
import shutil

import torch
import openvino as ov



CHECKPOINT_URL = os.getenv("HLS_3D_POSE_CHECKPOINT_URL")

def prepare_model(models_dir: Path) -> None:
    models_dir.mkdir(parents=True, exist_ok=True)

    if str(models_dir) not in sys.path:
        sys.path.insert(0, str(models_dir))

    tar_path = models_dir / "human-pose-estimation-3d.tar.gz"
    ckpt_file = models_dir / "human-pose-estimation-3d-0001.pth"
    ov_model_path = models_dir / "human-pose-estimation-3d-0001.xml"

    if not ckpt_file.exists():
        if not tar_path.exists():
            print(f"Downloading 3D pose checkpoint from {CHECKPOINT_URL}")
            urllib.request.urlretrieve(CHECKPOINT_URL, tar_path)
            print(f"Saved checkpoint archive to {tar_path}")

        print(f"Extracting checkpoint archive into {models_dir}")
        with tarfile.open(tar_path) as archive:
            archive.extractall(models_dir)
        print("Checkpoint extraction complete")

    if not ov_model_path.exists():
        from model.with_mobilenet import PoseEstimationWithMobileNet

        pose_estimation_model = PoseEstimationWithMobileNet(is_convertible_by_mo=True)
        pose_estimation_model.load_state_dict(
            torch.load(ckpt_file, map_location="cpu")
        )
        pose_estimation_model.eval()

        with torch.no_grad():
            ov_model = ov.convert_model(
                pose_estimation_model,
                example_input=torch.zeros([1, 3, 256, 448]),
                input=[1, 3, 256, 448],
            )
            ov.save_model(ov_model, ov_model_path)

    for item in models_dir.iterdir():
        if item.is_file() and item.suffix in {".xml", ".bin"}:
            continue
        if item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
        else:
            try:
                item.unlink()
            except FileNotFoundError:
                pass

    print("OpenVINO IR model saved:", ov_model_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare 3D pose demo assets")
    parser.add_argument(
        "--models-dir",
        type=Path,
        default=Path("/models/3d-pose"),
        help="Directory to store the OpenVINO IR files",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    prepare_model(args.models_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
