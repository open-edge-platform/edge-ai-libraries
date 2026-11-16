# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Fetch checksum-pinned userspace accelerator packages for the extended image."""

import argparse
import hashlib
import re
import shutil
import tarfile
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen

MAX_ARTIFACT_BYTES = 512 * 1024 * 1024
VERSION_PATTERNS = {
    "INTEL_COMPUTE_RUNTIME_VERSION": r"\d+\.\d+\.\d+\.\d+",
    "INTEL_IGC_VERSION": r"\d+\.\d+\.\d+",
    "INTEL_IGC_BUILD": r"\d+",
    "INTEL_GMMLIB_VERSION": r"\d+\.\d+\.\d+",
    "INTEL_NPU_DRIVER_VERSION": r"\d+\.\d+\.\d+",
    "INTEL_NPU_DRIVER_BUILD": r"\d+-\d+",
}
DIGEST_KEYS = (
    "INTEL_OPENCL_SHA256",
    "INTEL_OCLOC_SHA256",
    "INTEL_LEVEL_ZERO_GPU_SHA256",
    "INTEL_GMMLIB_SHA256",
    "INTEL_IGC_CORE_SHA256",
    "INTEL_IGC_OPENCL_SHA256",
    "INTEL_NPU_DRIVER_SHA256",
)


def load_pins(path: Path) -> dict[str, str]:
    pins = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Z][A-Z0-9_]*)=(\S+)", line)
        if match is None or match[1] in pins:
            raise ValueError(f"Invalid or duplicate version assignment at line {number}")
        pins[match[1]] = match[2]
    patterns = {**VERSION_PATTERNS, **dict.fromkeys(DIGEST_KEYS, r"[0-9a-f]{64}")}
    for key, pattern in patterns.items():
        if not re.fullmatch(pattern, pins.get(key, "")):
            raise ValueError(f"Missing or invalid accelerator pin: {key}")
    return pins


def download(url: str, digest: str, destination: Path) -> None:
    if urlsplit(url).scheme != "https" or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("Downloads require HTTPS and a SHA256 digest")
    if destination.exists():
        raise FileExistsError(destination)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        pending = Path(temporary) / "download"
        checksum = hashlib.sha256()
        size = 0
        with urlopen(url, timeout=60) as response, pending.open("wb") as output:
            if urlsplit(response.geturl()).scheme != "https":
                raise ValueError("Download redirected away from HTTPS")
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_ARTIFACT_BYTES:
                    raise ValueError("Accelerator artifact exceeds the size limit")
                checksum.update(chunk)
                output.write(chunk)
        if checksum.hexdigest() != digest:
            raise ValueError(f"SHA256 mismatch for {destination.name}")
        destination.hardlink_to(pending)


def extract_npu_packages(archive: Path, output: Path, package_version: str) -> None:
    names = {
        f"./{package}_{package_version}~ubuntu24.04_amd64.deb"
        for package in ("intel-level-zero-npu", "intel-driver-compiler-npu")
    }
    with tarfile.open(archive, "r:gz") as bundle:
        members = [member for member in bundle.getmembers() if member.name in names]
        if len(members) != 2 or {member.name for member in members} != names:
            raise ValueError("NPU archive must contain exactly the two userspace packages")
        for member in members:
            if not member.isfile() or not 0 < member.size <= MAX_ARTIFACT_BYTES:
                raise ValueError(f"Invalid NPU archive member: {member.name}")
        # Copy only allowlisted regular files, never firmware, links or tar paths.
        for member in members:
            source = bundle.extractfile(member)
            if source is None:
                raise ValueError(f"Cannot read NPU package: {member.name}")
            with source, (output / Path(member.name).name).open("xb") as destination:
                shutil.copyfileobj(source, destination)


def fetch_accelerators(pins: dict[str, str], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    gpu = pins["INTEL_COMPUTE_RUNTIME_VERSION"]
    igc = pins["INTEL_IGC_VERSION"]
    igc_package = f"{igc}+{pins['INTEL_IGC_BUILD']}"
    gmm = pins["INTEL_GMMLIB_VERSION"]
    artifacts = (
        ("compute-runtime", gpu, f"intel-opencl-icd_{gpu}-0_amd64.deb", "INTEL_OPENCL_SHA256"),
        ("compute-runtime", gpu, f"intel-ocloc_{gpu}-0_amd64.deb", "INTEL_OCLOC_SHA256"),
        (
            "compute-runtime",
            gpu,
            f"libze-intel-gpu1_{gpu}-0_amd64.deb",
            "INTEL_LEVEL_ZERO_GPU_SHA256",
        ),
        ("compute-runtime", gpu, f"libigdgmm12_{gmm}_amd64.deb", "INTEL_GMMLIB_SHA256"),
        (
            "intel-graphics-compiler",
            f"v{igc}",
            f"intel-igc-core-2_{igc_package}_amd64.deb",
            "INTEL_IGC_CORE_SHA256",
        ),
        (
            "intel-graphics-compiler",
            f"v{igc}",
            f"intel-igc-opencl-2_{igc_package}_amd64.deb",
            "INTEL_IGC_OPENCL_SHA256",
        ),
    )
    for repository, version, filename, digest_key in artifacts:
        url = f"https://github.com/intel/{repository}/releases/download/{version}/{filename}"
        download(url, pins[digest_key], output / filename)
        print(f"Verified {filename}", flush=True)
    npu = pins["INTEL_NPU_DRIVER_VERSION"]
    build = pins["INTEL_NPU_DRIVER_BUILD"]
    filename = f"linux-npu-driver-v{npu}.{build}-ubuntu2404.tar.gz"
    with tempfile.TemporaryDirectory() as temporary:
        archive = Path(temporary) / filename
        download(
            f"https://github.com/intel/linux-npu-driver/releases/download/v{npu}/{filename}",
            pins["INTEL_NPU_DRIVER_SHA256"],
            archive,
        )
        extract_npu_packages(archive, output, f"{npu}.{build}")
    print("Verified NPU userspace packages; firmware and debug packages excluded", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--versions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fetch_accelerators(load_pins(args.versions), args.output)


if __name__ == "__main__":
    main()
