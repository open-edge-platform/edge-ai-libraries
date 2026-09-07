# SPDX-License-Identifier: Apache-2.0

"""
API routes for timeseries pipeline data (wind turbine anomaly detection PoC).

- Reads ingestion data from a JSONL file on the shared /metadata volume
- Polls Kapacitor logs directly for analytics timing metrics
- No extra Docker service needed
"""

import asyncio
import json
import logging
import os
import re
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Annotated, BinaryIO

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

import api.api_schemas as schemas

router = APIRouter()
logger = logging.getLogger("api.routes.timeseries")

METADATA_DIR = os.getenv("METADATA_DIR", "/metadata")
INGESTION_FILE = os.path.join(METADATA_DIR, "timeseries-ingestion.jsonl")

RE_INFERENCE = re.compile(r"Inference time:\s*([\d.]+)\s*milliseconds")
RE_E2E = re.compile(r"End to end time:\s*([\d.]+)\s*milliseconds")
RE_POINT_TIME = re.compile(r"Processing point time:\s*(\d+)")


def _read_ingestion_snapshot(limit: int = 100) -> list[dict]:
    """Read last N records from the ingestion JSONL file."""
    if not os.path.exists(INGESTION_FILE):
        return []
    records: list[dict] = []
    try:
        with open(INGESTION_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except OSError:
        return []
    return records[-limit:]


DOCKER_SOCKET = "/var/run/docker.sock"
TSAM_CONTAINER = "ia-time-series-analytics-microservice"
TSAM_URL = os.getenv("TSAM_URL", "http://ia-time-series-analytics-microservice:5000")
MODEL_DOWNLOAD_URL = os.getenv("MODEL_DOWNLOAD_URL", "http://model-download:8000")
UDF_MAX_FILE_SIZE_BYTES = int(os.getenv("UDF_MAX_FILE_SIZE_MB", "100")) * 1024 * 1024
UDF_DOWNLOAD_TIMEOUT_S = float(os.getenv("UDF_DOWNLOAD_TIMEOUT_S", "600"))
UDF_PACKAGE_URL = (
    "https://github.com/open-edge-platform/edge-ai-resources/raw/main/"
    "timeseries-udf-deployment-packages/{name}.tar"
)
WIND_TURBINE_UDF_PACKAGE = "wind-turbine-anomaly-detection"
UDF_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


def _validate_tar_member(member: tarfile.TarInfo) -> None:
    member_path = Path(member.name)
    if member_path.is_absolute() or ".." in member_path.parts:
        raise ValueError("UDF archive contains an unsafe path")
    if member.issym() or member.islnk() or member.isdev():
        raise ValueError("UDF archive contains an unsupported link or device")


def _validate_udf_package(
    package_path: str,
    device: str | None = None,
) -> tuple[str, dict]:
    """Validate archive safety and UDF configuration before TSAM receives it."""
    try:
        with tarfile.open(package_path, "r:") as archive:
            members = archive.getmembers()
            if not members:
                raise ValueError("UDF archive is empty")
            for member in members:
                _validate_tar_member(member)

            config_members = [
                member
                for member in members
                if Path(member.name).name == "config.json" and member.isfile()
            ]
            if len(config_members) > 1:
                raise ValueError("UDF archive must contain at most one config.json")
            config = None
            if config_members:
                config_file = archive.extractfile(config_members[0])
                if config_file is None:
                    raise ValueError("Could not read config.json from UDF archive")
                config = json.load(config_file)
    except (tarfile.TarError, json.JSONDecodeError) as exc:
        raise ValueError(
            "UDF package must be a valid tar archive with config.json"
        ) from exc

    udf_files = [
        member
        for member in members
        if member.isfile()
        and Path(member.name).parent == Path("udfs")
        and Path(member.name).suffix == ".py"
    ]
    if len(udf_files) != 1:
        raise ValueError("UDF archive must contain exactly one Python file in udfs/")
    udf_name = Path(udf_files[0].name).stem

    model_files = [
        member
        for member in members
        if member.isfile() and Path(member.name).parent == Path("models")
    ]
    if len(model_files) != 1:
        raise ValueError("UDF archive must contain exactly one model file in models/")
    model_name = Path(model_files[0].name).name

    udfs = config.get("udfs") if config else {}
    if config is not None and not isinstance(udfs, dict):
        raise ValueError("config.json must contain an 'udfs' object")
    configured_udf_name = udfs.get("name")
    if configured_udf_name is not None and configured_udf_name != udf_name:
        raise ValueError("UDF name in config.json must match the UDF filename")
    configured_model_name = udfs.get("models")
    if configured_model_name is not None and configured_model_name != model_name:
        raise ValueError("UDF model in config.json must match the model filename")
    if not UDF_NAME_RE.fullmatch(udf_name):
        raise ValueError("UDF filename contains an invalid UDF name")
    if not isinstance(device, str) or not device:
        raise ValueError("A UDF device is required")
    return udf_name, {
        "udfs": {"name": udf_name, "models": model_name, "device": device}
    }


def _write_upload_to_tempfile(upload: BinaryIO, filename: str) -> str:
    if Path(filename).suffix.lower() != ".tar":
        raise ValueError("UDF package must have a .tar extension")
    fd, path = tempfile.mkstemp(prefix="vippet-udf-", suffix=".tar")
    size = 0
    try:
        with os.fdopen(fd, "wb") as output:
            while chunk := upload.read(1024 * 1024):
                size += len(chunk)
                if size > UDF_MAX_FILE_SIZE_BYTES:
                    raise ValueError(
                        f"UDF package exceeds the {UDF_MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB limit"
                    )
                output.write(chunk)
    except Exception:
        Path(path).unlink(missing_ok=True)
        raise
    return path


def _download_udf_package(package_name: str) -> str:
    if not UDF_NAME_RE.fullmatch(package_name):
        raise ValueError("Package name contains unsupported characters")
    download_path = f"udf-packages/{package_name}-{int(time.time())}"
    request = {
        "models": [
            {
                "name": package_name,
                "hub": "remote-url",
                "config": {"url": UDF_PACKAGE_URL},
            }
        ]
    }
    try:
        with httpx.Client(timeout=60) as client:
            response = client.post(
                f"{MODEL_DOWNLOAD_URL}/api/v1/models/download",
                params={"download_path": download_path},
                json=request,
            )
            response.raise_for_status()
            job_ids = response.json().get("job_ids", [])
            if len(job_ids) != 1:
                raise ValueError("model-download did not create a UDF download job")

            deadline = time.monotonic() + UDF_DOWNLOAD_TIMEOUT_S
            while time.monotonic() < deadline:
                status = client.get(f"{MODEL_DOWNLOAD_URL}/api/v1/jobs/{job_ids[0]}")
                status.raise_for_status()
                result = status.json()
                if result.get("status") == "completed":
                    break
                if result.get("status") == "failed":
                    raise ValueError(result.get("error") or "model-download failed")
                time.sleep(2)
            else:
                raise ValueError(
                    "model-download timed out while fetching the UDF package"
                )
    except httpx.HTTPError as exc:
        raise RuntimeError("model-download is unavailable") from exc

    source_dir = Path("/models/output") / download_path / "remote-url" / package_name
    if not source_dir.is_dir():
        raise ValueError("model-download did not produce the expected UDF package")
    fd, package_path = tempfile.mkstemp(prefix="vippet-udf-", suffix=".tar")
    os.close(fd)
    with tarfile.open(package_path, "w") as archive:
        for source in source_dir.rglob("*"):
            if source.is_file():
                archive.add(source, arcname=str(source.relative_to(source_dir)))
    return package_path


@router.post(
    "/udfs/deploy",
    operation_id="deploy_timeseries_udf",
    summary="Deploy a Time Series UDF",
    response_model=schemas.UdfDeploymentResponse,
    responses={
        400: {"description": "Invalid UDF package", "model": schemas.MessageResponse},
        413: {"description": "UDF package too large", "model": schemas.MessageResponse},
        502: {
            "description": "TSAM or model-download unavailable",
            "model": schemas.MessageResponse,
        },
    },
)
async def deploy_udf(
    source: Annotated[str, Form()] = "upload",
    device: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
):
    """Deploy a local UDF tarball or retrieve a known package through model-download.

    The archive is validated before it is sent to TSAM. Its ``config.json`` is
    then applied only after TSAM accepts the package.
    """
    package_path: str | None = None
    try:
        if source == "upload":
            if file is None:
                raise ValueError("A UDF package file is required")
            package_path = _write_upload_to_tempfile(file.file, file.filename or "")
        elif source == "model-download":
            package_path = _download_udf_package(WIND_TURBINE_UDF_PACKAGE)
        else:
            raise ValueError("Unsupported UDF package source")

        udf_name, config = _validate_udf_package(
            package_path,
            device=device,
        )
        with open(package_path, "rb") as package_file:
            files = {
                "file": (
                    os.path.basename(package_path),
                    package_file,
                    "application/x-tar",
                )
            }
            async with httpx.AsyncClient(timeout=UDF_DOWNLOAD_TIMEOUT_S) as client:
                package_response = await client.post(
                    f"{TSAM_URL}/udfs/package", files=files
                )
                if package_response.status_code >= 400:
                    logger.warning(
                        "TSAM rejected UDF package with status %s",
                        package_response.status_code,
                    )
                    raise HTTPException(
                        status_code=502, detail="TSAM rejected the UDF package"
                    )
                config_response = await client.post(f"{TSAM_URL}/config", json=config)
                if config_response.status_code >= 400:
                    logger.warning(
                        "TSAM rejected UDF configuration with status %s",
                        config_response.status_code,
                    )
                    raise HTTPException(
                        status_code=502, detail="TSAM rejected the UDF configuration"
                    )

        return schemas.UdfDeploymentResponse(
            udf_name=udf_name,
            message=f"UDF '{udf_name}' deployed successfully",
        )
    except HTTPException:
        raise
    except ValueError as exc:
        status_code = 413 if "exceeds" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    except (httpx.HTTPError, OSError, RuntimeError):
        logger.error("Failed to deploy Time Series UDF", exc_info=True)
        raise HTTPException(
            status_code=502,
            detail="The UDF deployment service is unavailable",
        ) from None
    finally:
        if package_path:
            Path(package_path).unlink(missing_ok=True)


def _fetch_kapacitor_analytics() -> list[dict]:
    """Read TSAM container logs via Docker Engine API and extract timing records."""
    if not os.path.exists(DOCKER_SOCKET):
        logger.debug("Docker socket not available at %s", DOCKER_SOCKET)
        return []

    url = f"http://docker/containers/{TSAM_CONTAINER}/logs"
    params = {"stdout": "1", "stderr": "1", "tail": "200", "timestamps": "1"}
    try:
        transport = httpx.HTTPTransport(uds=DOCKER_SOCKET)
        with httpx.Client(transport=transport, timeout=5) as client:
            resp = client.get(url, params=params)
            if resp.status_code != 200:
                logger.debug("Docker logs returned %d", resp.status_code)
                return []
            log_bytes = resp.content
    except Exception as e:
        logger.debug("Could not fetch TSAM container logs: %s", e)
        return []

    # Docker multiplexed stream: each frame has 8-byte header (stream type + size)
    # Parse frames to extract text
    lines: list[str] = []
    offset = 0
    while offset + 8 <= len(log_bytes):
        frame_size = int.from_bytes(log_bytes[offset + 4 : offset + 8], "big")
        if offset + 8 + frame_size > len(log_bytes):
            break
        frame_data = log_bytes[offset + 8 : offset + 8 + frame_size]
        lines.append(frame_data.decode("utf-8", errors="replace"))
        offset += 8 + frame_size

    records: list[dict] = []
    current_inf: float | None = None
    current_e2e: float | None = None
    current_pt: int | None = None

    for line in lines:
        m = RE_INFERENCE.search(line)
        if m:
            current_inf = float(m.group(1))
        m = RE_E2E.search(line)
        if m:
            current_e2e = float(m.group(1))
        m = RE_POINT_TIME.search(line)
        if m:
            current_pt = int(m.group(1))

        if (
            current_inf is not None
            and current_e2e is not None
            and current_pt is not None
        ):
            records.append(
                {
                    "inference_time_ms": current_inf,
                    "end_to_end_time_ms": current_e2e,
                    "processing_point_time": current_pt,
                }
            )
            current_inf = None
            current_e2e = None
            current_pt = None

    return records


@router.get("/data")
async def get_timeseries_data(limit: int = 100):
    """
    # Get Timeseries Pipeline Data

    Returns ingestion sensor values and analytics timing metrics in one call.
    """
    limit = min(limit, 1000)
    ingestion = _read_ingestion_snapshot(limit)
    analytics = _fetch_kapacitor_analytics()[-limit:]
    return JSONResponse(content={"ingestion": ingestion, "analytics": analytics})


async def _tail_ingestion():
    """SSE generator that tails the ingestion JSONL file."""
    waited = 0
    while not os.path.exists(INGESTION_FILE) and waited < 60:
        yield ": waiting\n\n"
        await asyncio.sleep(3)
        waited += 3

    if not os.path.exists(INGESTION_FILE):
        yield 'data: {"error": "No ingestion data yet"}\n\n'
        return

    with open(INGESTION_FILE, "r") as f:
        f.seek(0, 2)
        while True:
            line = f.readline()
            if line:
                line = line.strip()
                if line:
                    yield f"data: {line}\n\n"
            else:
                yield ": keepalive\n\n"
                await asyncio.sleep(2)


@router.get("/ingestion/stream")
async def stream_ingestion():
    """SSE stream of ingestion sensor data."""
    return StreamingResponse(
        _tail_ingestion(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
