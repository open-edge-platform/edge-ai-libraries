# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import hashlib
import io
import re
import tarfile
from pathlib import Path

import pytest

import docker_accelerators as accelerators

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_VERSION = "1.38.0.20260910-34487311128"
NPU_NAMES = [
    f"./{name}_{PACKAGE_VERSION}~ubuntu24.04_amd64.deb"
    for name in ("intel-level-zero-npu", "intel-driver-compiler-npu")
]


def make_archive(path, names, *, symlink=False):
    with tarfile.open(path, "w:gz") as archive:
        for name in names:
            member = tarfile.TarInfo(name)
            content = b"package fixture"
            if symlink and name == NPU_NAMES[0]:
                member.type = tarfile.SYMTYPE
                member.linkname = "/etc/passwd"
                archive.addfile(member)
            else:
                member.size = len(content)
                archive.addfile(member, io.BytesIO(content))


def test_current_pins():
    pins = accelerators.load_pins(ROOT / "versions.env")
    assert all(key in pins for key in accelerators.DIGEST_KEYS)


@pytest.mark.parametrize(
    "change",
    [
        lambda text: text + "\nINTEL_IGC_VERSION=2.42.6\n",
        lambda text: re.sub(r"(?m)^INTEL_IGC_VERSION=.*$", "INTEL_IGC_VERSION=../escape", text),
        lambda text: re.sub(r"(?m)^INTEL_IGC_VERSION=.*$", "", text),
        lambda text: re.sub(r"(?m)^INTEL_IGC_VERSION=.*$", "INTEL_IGC_VERSION =invalid", text),
        lambda text: text.replace("INTEL_OPENCL_SHA256=", "OTHER_DIGEST="),
    ],
)
def test_invalid_pins_fail(tmp_path, change):
    path = tmp_path / "versions.env"
    path.write_text(change((ROOT / "versions.env").read_text()))
    with pytest.raises(ValueError):
        accelerators.load_pins(path)


class Response(io.BytesIO):
    def __init__(self, body, url="https://example.test/package"):
        super().__init__(body)
        self.url = url

    def geturl(self):
        return self.url


def test_download_verified_and_closed(tmp_path, monkeypatch):
    response = Response(b"verified bytes")
    monkeypatch.setattr(accelerators, "urlopen", lambda url, timeout: response)
    output = tmp_path / "package.deb"
    accelerators.download(
        "https://example.test/package", hashlib.sha256(b"verified bytes").hexdigest(), output
    )
    assert output.read_bytes() == b"verified bytes"
    assert response.closed
    assert list(tmp_path.iterdir()) == [output]


@pytest.mark.parametrize("failure", ["checksum", "size", "redirect", "network"])
def test_download_failures_leave_no_package(tmp_path, monkeypatch, failure):
    response = Response(b"unverified bytes")
    if failure == "size":
        monkeypatch.setattr(accelerators, "MAX_ARTIFACT_BYTES", 1)
    if failure == "redirect":
        response.url = "http://example.test/package"
    if failure == "network":

        def failed_read(size):
            raise OSError("Network read failed")

        monkeypatch.setattr(response, "read", failed_read)
    monkeypatch.setattr(accelerators, "urlopen", lambda url, timeout: response)
    with pytest.raises((ValueError, OSError)):
        accelerators.download("https://example.test/package", "0" * 64, tmp_path / "package.deb")
    assert list(tmp_path.iterdir()) == []
    assert response.closed


@pytest.mark.parametrize(
    "url,digest",
    [
        ("http://example.test/package", "0" * 64),
        ("file:///etc/passwd", "0" * 64),
        ("https://example.test/package", "not-a-digest"),
    ],
)
def test_download_rejects_invalid_inputs(tmp_path, url, digest):
    with pytest.raises(ValueError):
        accelerators.download(url, digest, tmp_path / "package.deb")


def test_download_preserves_existing_file(tmp_path):
    output = tmp_path / "package.deb"
    output.write_bytes(b"existing")
    with pytest.raises(FileExistsError):
        accelerators.download("https://example.test/package", "0" * 64, output)
    assert output.read_bytes() == b"existing"


def test_download_does_not_replace_concurrently_created_file(tmp_path, monkeypatch):
    output = tmp_path / "package.deb"

    def raced_response(url, timeout):
        output.write_bytes(b"created concurrently")
        return Response(b"verified bytes")

    monkeypatch.setattr(accelerators, "urlopen", raced_response)
    with pytest.raises(FileExistsError):
        accelerators.download(
            "https://example.test/package", hashlib.sha256(b"verified bytes").hexdigest(), output
        )
    assert output.read_bytes() == b"created concurrently"
    assert list(tmp_path.iterdir()) == [output]


def test_only_npu_userspace_is_extracted(tmp_path):
    archive = tmp_path / "npu.tar.gz"
    make_archive(archive, [*NPU_NAMES, "./intel-fw-npu.deb", "../escape.deb", "/absolute.deb"])
    output = tmp_path / "packages"
    output.mkdir()
    accelerators.extract_npu_packages(archive, output, PACKAGE_VERSION)
    assert {path.name for path in output.iterdir()} == {Path(name).name for name in NPU_NAMES}
    assert not (tmp_path / "escape.deb").exists()


@pytest.mark.parametrize("failure", ["missing", "duplicate", "symlink"])
def test_invalid_npu_archive_fails_before_extraction(tmp_path, failure):
    archive = tmp_path / "npu.tar.gz"
    names = NPU_NAMES[:1] if failure == "missing" else list(NPU_NAMES)
    if failure == "duplicate":
        names.append(NPU_NAMES[0])
    make_archive(archive, names, symlink=failure == "symlink")
    output = tmp_path / "packages"
    output.mkdir()
    with pytest.raises(ValueError):
        accelerators.extract_npu_packages(archive, output, PACKAGE_VERSION)
    assert list(output.iterdir()) == []


def test_fetch_outputs_exactly_eight_packages(tmp_path, monkeypatch):
    pins = accelerators.load_pins(ROOT / "versions.env")
    calls = []

    def fake_download(url, digest, destination):
        assert url.startswith("https://github.com/intel/")
        assert digest in {pins[key] for key in accelerators.DIGEST_KEYS}
        calls.append(url)
        if destination.name.endswith(".tar.gz"):
            version = f"{pins['INTEL_NPU_DRIVER_VERSION']}.{pins['INTEL_NPU_DRIVER_BUILD']}"
            names = [
                f"./{name}_{version}~ubuntu24.04_amd64.deb"
                for name in ("intel-level-zero-npu", "intel-driver-compiler-npu")
            ]
            make_archive(destination, names)
        else:
            destination.write_bytes(b"verified fixture")

    monkeypatch.setattr(accelerators, "download", fake_download)
    accelerators.fetch_accelerators(pins, tmp_path)
    assert len(calls) == 7
    packages = list(tmp_path.iterdir())
    assert len(packages) == 8 and all(path.suffix == ".deb" for path in packages)
    assert not any("fw-npu" in path.name or "dbgsym" in path.name for path in packages)


def test_docker_build_wiring():
    dockerfile = (ROOT / "Dockerfile").read_text()
    builder = dockerfile.split(" AS accelerator-builder\n", 1)[1].split("\nFROM ", 1)[0]
    production = dockerfile.split(" AS production\n", 1)[1]
    assert 'if [ "$INSTALL_OPENVINO" = "true" ]' in builder
    assert "--versions /build/versions.env --output /runtime-debs" in builder
    assert "from=accelerator-builder,source=/runtime-debs,target=/runtime-debs" in production
    assert "ocl-icd-libopencl1 libze1 libtbb12 /runtime-debs/*.deb" in production
    assert "COPY docker_accelerators.py ./" in dockerfile.split(" AS test\n", 1)[1]
