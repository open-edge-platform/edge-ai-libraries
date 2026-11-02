#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import argparse
import csv
import hashlib
import json
import os
import platform
import subprocess
from pathlib import Path


PROFILES = {
    "baseline": {},
    "features500": {"nfeatures": 500},
    "layers5": {"nOctaveLayers": 5},
    "contrast_low": {"contrastThreshold": 0.02, "openclContrast": 0.5,
                     "syclContrast": 1.5},
    "edge5": {"edgeThreshold": 5.0},
    "sigma1.2": {"sigma": 1.2},
    "cpu4": {"cpuThreads": 4},
}


def dimensions(value):
    try:
        width, height = (int(part) for part in value.split("x"))
    except ValueError as error:
        raise argparse.ArgumentTypeError("Use WIDTHxHEIGHT") from error
    if not (32 <= width <= 3840 and 32 <= height <= 2160):
        raise argparse.ArgumentTypeError("Dimensions must fit 32x32 through 3840x2160")
    return width, height


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description="Diagnostic Intel CPU/GPU SIFT matrix")
    parser.add_argument("binary", type=Path)
    parser.add_argument("image", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--sizes", nargs="+", type=dimensions,
                        default=[(640, 480), (1280, 720), (1920, 1080)])
    parser.add_argument("--profiles", nargs="+", choices=PROFILES, default=list(PROFILES))
    parser.add_argument("--iterations", type=int, choices=range(1, 101), default=10,
                        metavar="1..100")
    parser.add_argument("--sycl-context", action="store_true",
                        help="Time the library context steady state; setup/release are reported separately")
    args = parser.parse_args()
    binary = args.binary.resolve(strict=True)
    image = args.image.resolve(strict=True)
    if not binary.is_file() or not os.access(binary, os.X_OK) or not image.is_file():
        parser.error("Require an executable binary and a regular image file")
    if len(set(args.sizes)) != len(args.sizes) or len(set(args.profiles)) != len(args.profiles):
        parser.error("Duplicate sizes or profiles are not allowed")
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = {
        "binary": str(binary), "binary_sha256": digest(binary),
        "image": str(image), "image_sha256": digest(image),
        "platform": platform.platform(), "python": platform.python_version(),
        "sizes": args.sizes, "profiles": {name: PROFILES[name] for name in args.profiles},
        "iterations": args.iterations, "warmups": 3,
        "sycl_lifecycle": "library_context_steady_state" if args.sycl_context else "per_call",
        "parameters_equivalent": False, "speedup_quality_qualified": False,
        "resizing_is_synthetic_workload_not_new_image_detail": True,
    }
    with (args.output / "manifest.json").open("x") as target:
        json.dump(manifest, target, indent=2)
    fields = ["case", "status", "width", "height", "cpu_ms", "opencl_ms", "sycl_ms",
              "cpu_over_opencl", "cpu_over_sycl", "cpu_inliers", "opencl_inliers",
              "sycl_inliers", "cpu_rmse", "opencl_rmse", "sycl_rmse", "error"]
    failures = 0
    environment = dict(os.environ, ONEAPI_DEVICE_SELECTOR="level_zero:gpu")
    with (args.output / "summary.csv").open("x", newline="") as summary:
        writer = csv.DictWriter(summary, fieldnames=fields)
        writer.writeheader()
        for width, height in args.sizes:
            for name in args.profiles:
                case = f"{width}x{height}-{name}"
                config = {"width": width, "height": height, "cpuThreads": 1, **PROFILES[name]}
                config_path = (args.output / f"{case}.config.json").resolve()
                report_path = (args.output / f"{case}.json").resolve()
                with config_path.open("x") as target:
                    json.dump(config, target, indent=2)
                row = {"case": case, "width": width, "height": height, "status": "failed"}
                try:
                    command = [str(binary), str(image), str(report_path),
                               str(args.iterations), str(config_path)]
                    if args.sycl_context:
                        command.append("all-context")
                    with (args.output / f"{case}.log").open("x") as log:
                        subprocess.run(command, env=environment, stdout=log,
                                       stderr=subprocess.STDOUT, check=True, timeout=300)
                    with report_path.open() as source:
                        report = json.load(source)
                    timing = report["timing"]
                    for column, backend in (("cpu", "opencv_cpu"), ("opencl", "opencl"),
                                            ("sycl", "sycl")):
                        quality = report[{"cpu": "opencv_cpu_default", "opencl": "opencl_prototype",
                                          "sycl": "sycl_reference"}[column]]
                        row[f"{column}_ms"] = timing[backend]["median_ms"]
                        row[f"{column}_inliers"] = quality["ground_truth_inliers_3px"]
                        row[f"{column}_rmse"] = quality["inlier_rmse_px"]
                    row.update(status="ok", cpu_over_opencl=timing["cpu_over_opencl_latency_ratio"],
                               cpu_over_sycl=timing["cpu_over_sycl_latency_ratio"])
                except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
                    row["error"] = str(error)
                    failures += 1
                writer.writerow(row)
                summary.flush()
                print(f"{case}: {row['status']}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())