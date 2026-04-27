import logging
import os
import re
import tempfile
from typing import List, Optional, Tuple

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import JSONResponse

import api.api_schemas as schemas
from videos import (
    VIDEO_EXTENSIONS,
    UPLOADED_VIDEO_DIR,
    Video as DomainVideo,
    VideosManager,
)

router = APIRouter()
logger = logging.getLogger("api.routes.videos")


# --------------------------------------------------------------------------- #
# Configuration (read once at import time so the router stays stateless).
# --------------------------------------------------------------------------- #

# Maximum accepted request body size in bytes. Default: 2 GiB. Kept in sync
# with nginx `client_max_body_size 2G;` in ui/nginx.conf.
_DEFAULT_UPLOAD_MAX_SIZE_BYTES = 2 * 1024 * 1024 * 1024


def _parse_csv_env(name: str, default: str) -> list[str]:
    """
    Parse a comma-separated environment variable into a list of lower-cased
    tokens, ignoring empty entries. Used for configurable allow-lists.
    """
    raw = os.environ.get(name, default)
    return [token.strip().lower() for token in raw.split(",") if token.strip()]


def _parse_int_env(name: str, default: int) -> int:
    """
    Parse an integer environment variable; fall back to ``default`` on any
    parsing error and log a warning.
    """
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "Invalid integer for env var %s=%r, falling back to %d", name, raw, default
        )
        return default


UPLOAD_ALLOWED_EXTENSIONS: list[str] = _parse_csv_env(
    "UPLOAD_ALLOWED_EXTENSIONS",
    ",".join(VIDEO_EXTENSIONS),
)
UPLOAD_ALLOWED_CONTAINERS: list[str] = _parse_csv_env(
    "UPLOAD_ALLOWED_CONTAINERS",
    # "raw" covers H.264/H.265 elementary streams (.264, .avc, .h265, .hevc),
    # which map to container="raw" in _EXTENSION_TO_CONTAINER. Keeping it in
    # the default allow-list matches the default UPLOAD_ALLOWED_EXTENSIONS,
    # which also accepts those extensions.
    "mp4,mov,mkv,avi,mpegts,raw",
)
UPLOAD_ALLOWED_CODECS: list[str] = _parse_csv_env(
    "UPLOAD_ALLOWED_CODECS",
    "h264,h265",
)
UPLOAD_MAX_SIZE_BYTES: int = _parse_int_env(
    "UPLOAD_MAX_SIZE_BYTES",
    _DEFAULT_UPLOAD_MAX_SIZE_BYTES,
)

# File-extension -> container name map. Used to translate the user's file
# extension into the container identifier checked against
# UPLOAD_ALLOWED_CONTAINERS. Raw elementary streams have no container, so we
# normalise them to an empty value and reject unless "raw" is explicitly
# added to the allow-list by the operator.
_EXTENSION_TO_CONTAINER: dict[str, str] = {
    "mp4": "mp4",
    "mov": "mov",
    "mkv": "mkv",
    "avi": "avi",
    "ts": "mpegts",
    "m2ts": "mpegts",
    # Raw elementary streams: no container.
    "264": "raw",
    "avc": "raw",
    "h265": "raw",
    "hevc": "raw",
}


# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #

# Conservative pattern for filenames we are willing to write to disk.
# Allows letters, digits, dot, underscore, hyphen and space. Any other
# character (including path separators) triggers rejection.
_SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9 ._-]+$")


def _sanitise_filename(raw: Optional[str]) -> Optional[str]:
    """
    Return a safe basename or None when the input is missing or unsafe.

    Strips any directory components, rejects empty / dot-only names and
    anything containing characters outside the conservative allow-list.
    This protects the shared folder from path-traversal attempts.
    """
    if not raw:
        return None
    basename = os.path.basename(raw).strip()
    if not basename or basename in (".", ".."):
        return None
    if not _SAFE_FILENAME_RE.match(basename):
        return None
    return basename


def _upload_error_response(
    error: schemas.VideoUploadErrorKind,
    detail: str,
    found: Optional[object] = None,
    allowed: Optional[list[object]] = None,
) -> JSONResponse:
    """
    Build a uniform HTTP 422 response body for upload rejections.

    The body carries both a structured ``error`` / ``found`` / ``allowed``
    triple and a human-readable ``detail`` message. Using a single helper
    guarantees every rejection path returns the same shape.
    """
    payload = schemas.VideoUploadError(
        detail=detail,
        error=error,
        found=found,  # type: ignore[arg-type]
        allowed=allowed,  # type: ignore[arg-type]
    )
    return JSONResponse(status_code=422, content=payload.model_dump())


def _probe_container_and_codec(file_path: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Open the file with OpenCV to derive (container, codec).

    The container is inferred from the file extension; OpenCV does not
    expose the actual container tag in a portable way, and our allow-list
    is intentionally extension-based. The codec is derived from the FOURCC
    reported by `cv2.VideoCapture`.

    Returns:
        Tuple ``(container, codec)``. Either entry is ``None`` when the
        value cannot be determined (for example a corrupted file).
    """
    file_info = VideosManager._extract_video_file_info(file_path)
    if file_info is None:
        return None, None

    ext = os.path.splitext(file_path)[1].lstrip(".").lower()
    container = _EXTENSION_TO_CONTAINER.get(ext)

    codec = file_info.codec if file_info.codec else None
    return container, codec


# --------------------------------------------------------------------------- #
# Routes.
# --------------------------------------------------------------------------- #


@router.get(
    "",
    operation_id="get_videos",
    summary="List all available input videos",
    response_model=List[schemas.Video],
)
async def get_videos():
    """
    **List all discovered input videos with metadata.**

    ## Operation

    1. VideosManager scans `AUTO_VIDEO_DIR` and `UPLOADED_VIDEO_DIR` for
       supported video files (h264/h265 codecs only)
    2. Metadata is loaded or extracted for each file (resolution, fps,
       duration, codec, source, path)
    3. Returns array of `Video` objects

    ## Parameters

    None

    ## Response Format

    | Code | Description |
    |------|-------------|
    | 200  | JSON array of `Video` objects (empty if no videos found) |
    | 500  | Runtime error during video listing |

    ## Conditions

    ### ✅ Success
    - VideosManager successfully initialized at startup
    - `AUTO_VIDEO_DIR` and `UPLOADED_VIDEO_DIR` exist and are readable

    ### ❌ Failure
    - VideosManager initialization fails → application exits at startup
    - Runtime errors → 500

    ## Example Response

    ```json
    [
      {
        "filename": "traffic_1080p_h264.mp4",
        "width": 1920,
        "height": 1080,
        "fps": 30.0,
        "frame_count": 900,
        "codec": "h264",
        "duration": 30.0,
        "source": "auto",
        "path": "auto/traffic_1080p_h264.mp4"
      }
    ]
    ```
    """
    logger.debug("Received request for all videos.")
    try:
        videos_dict = VideosManager().get_all_videos()
        logger.debug(f"Found {len(videos_dict)} videos.")
        return [
            schemas.Video(
                filename=v.filename,
                width=v.width,
                height=v.height,
                fps=v.fps,
                frame_count=v.frame_count,
                codec=v.codec,
                duration=v.duration,
                source=schemas.VideoSource(v.source),
                path=v.path,
            )
            for v in videos_dict.values()
        ]
    except Exception:
        logger.error("Failed to list videos", exc_info=True)
        return JSONResponse(
            content=schemas.MessageResponse(
                message="Unexpected error while listing videos"
            ).model_dump(),
            status_code=500,
        )


@router.get(
    "/check-video-input-exists",
    operation_id="check_video_input_exists",
    summary="Check if a video file already exists",
    response_model=schemas.VideoExistsResponse,
)
async def check_video_input_exists(
    filename: str = Query(..., description="Video filename to check"),
):
    """
    **Check if a video file with the given filename already exists under
    either `AUTO_VIDEO_DIR` or `UPLOADED_VIDEO_DIR`.**

    Used by the UI to skip uploading a duplicate file and to warn the user
    early. Always succeeds with a boolean response.

    ## Parameters

    - `filename` (query) - Base name of the video file to check.

    ## Response Format

    | Code | Description |
    |------|-------------|
    | 200  | Returns `VideoExistsResponse` with `exists` boolean |

    ## Conditions

    ### ✅ Success
    - Always succeeds with a boolean response

    ### ❌ Failure
    - None (this endpoint has no failure modes)

    ## Example Response

    ```json
    {
      "exists": true,
      "filename": "traffic_1080p_h264.mp4"
    }
    ```
    """
    logger.debug(f"Checking existence of video file: {filename}")

    exists = VideosManager().filename_exists(filename)

    logger.debug(f"Video '{filename}' exists: {exists}")

    return schemas.VideoExistsResponse(
        exists=exists,
        filename=filename,
    )


@router.post(
    "/upload",
    operation_id="upload_video",
    summary="Upload a new video file",
    response_model=schemas.Video,
    status_code=201,
    responses={
        422: {
            "model": schemas.VideoUploadError,
            "description": "Upload rejected by server-side validation.",
        },
        500: {
            "model": schemas.MessageResponse,
            "description": "Unexpected server error during upload or processing.",
        },
    },
)
async def upload_video(
    file: UploadFile = File(...),
):
    """
    **Upload a new video file into `UPLOADED_VIDEO_DIR`.**

    ## Operation

    1. **Pre-write validation** (before any bytes touch disk):
       - Filename is present and safe (no path traversal)
       - File extension is in `UPLOAD_ALLOWED_EXTENSIONS`
       - A video with the same basename does not already exist in
         `AUTO_VIDEO_DIR` or `UPLOADED_VIDEO_DIR`
    2. **Stream upload to a temporary file**, enforcing
       `UPLOAD_MAX_SIZE_BYTES` per chunk. Aborts and deletes the temp file
       the moment the accumulated byte count exceeds the limit.
    3. **Post-write validation** via `cv2.VideoCapture`:
       - Container format is in `UPLOAD_ALLOWED_CONTAINERS`
       - Codec is in `UPLOAD_ALLOWED_CODECS`
    4. On success: move the temp file into `UPLOADED_VIDEO_DIR`, create
       metadata JSON, convert to TS, create TS metadata JSON, register both
       in the in-memory VideosManager cache.

    Every validation rejection returns HTTP 422 with a `VideoUploadError`
    body containing both a human-readable `detail` field and structured
    `error` / `found` / `allowed` fields.

    ## Parameters

    - `file` (multipart/form-data) - Video file to upload

    ## Response Format

    | Code | Description |
    |------|-------------|
    | 201  | Video uploaded successfully, returns the `Video` metadata |
    | 422  | Upload rejected (`VideoUploadError` body with `error`, `found`, `allowed`, `detail`) |
    | 500  | Unexpected server error (for example disk full during move) |

    ## Conditions

    ### ✅ Success
    - File has a filename that contains only safe characters
    - File extension is in `UPLOAD_ALLOWED_EXTENSIONS`
    - File size is within `UPLOAD_MAX_SIZE_BYTES`
    - Container is in `UPLOAD_ALLOWED_CONTAINERS`
    - Codec is in `UPLOAD_ALLOWED_CODECS`
    - No file with the same name exists in `AUTO_VIDEO_DIR` or `UPLOADED_VIDEO_DIR`
    - Metadata extraction and TS conversion both succeed

    ### ❌ Failure
    - Missing or unsafe filename → 422 (`missing_filename`)
    - Unsupported extension → 422 (`unsupported_extension`)
    - File exceeds the size limit → 422 (`file_too_large`)
    - Duplicate filename → 422 (`file_exists`)
    - Unsupported container → 422 (`unsupported_container`)
    - Unsupported codec → 422 (`unsupported_codec`)
    - `cv2.VideoCapture` cannot open the file → 422 (`invalid_video`)
    - Metadata extraction, TS conversion or disk move fails → 500
    - Any other unexpected runtime error → 500

    ## Example success response (HTTP 201)

    ```json
    {
      "filename": "myclip.mp4",
      "width": 1920,
      "height": 1080,
      "fps": 30.0,
      "frame_count": 1800,
      "codec": "h264",
      "duration": 60.0,
      "source": "uploaded",
      "path": "uploaded/myclip.mp4"
    }
    ```

    ## Example error response (HTTP 422, unsupported codec)

    ```json
    {
      "detail": "Unsupported codec 'vp9'. Allowed codecs: h264, h265.",
      "error": "unsupported_codec",
      "found": "vp9",
      "allowed": ["h264", "h265"]
    }
    ```
    """
    raw_filename = file.filename
    logger.info(f"Received video upload request: {raw_filename}")

    # ---- Stage 1: pre-write validation -------------------------------------

    safe_filename = _sanitise_filename(raw_filename)
    if safe_filename is None:
        logger.warning("Upload rejected: missing or unsafe filename %r", raw_filename)
        return _upload_error_response(
            schemas.VideoUploadErrorKind.MISSING_FILENAME,
            "Upload is missing a valid filename.",
            found=raw_filename,
        )

    ext = safe_filename.rsplit(".", 1)[-1].lower() if "." in safe_filename else ""
    if ext not in UPLOAD_ALLOWED_EXTENSIONS:
        logger.warning("Upload rejected: unsupported extension '.%s'", ext)
        return _upload_error_response(
            schemas.VideoUploadErrorKind.UNSUPPORTED_EXTENSION,
            (
                f"Unsupported file extension '.{ext}'. "
                f"Allowed extensions: {', '.join(UPLOAD_ALLOWED_EXTENSIONS)}."
            ),
            found=ext,
            allowed=list(UPLOAD_ALLOWED_EXTENSIONS),
        )

    # Reject duplicates early; the UI also calls /check-video-input-exists
    # but we must defend against direct API clients and races.
    videos_manager = VideosManager()
    if videos_manager.filename_exists(safe_filename):
        logger.warning("Upload rejected: filename '%s' already exists", safe_filename)
        return _upload_error_response(
            schemas.VideoUploadErrorKind.FILE_EXISTS,
            f"A video with filename '{safe_filename}' already exists.",
            found=safe_filename,
        )

    # ---- Stage 2: stream to a temp file, enforcing the size limit ----------

    # Store the temp file inside UPLOADED_VIDEO_DIR so the final shutil.move
    # is a same-filesystem rename instead of a slow copy across volumes.
    temp_fd, temp_path = tempfile.mkstemp(
        prefix=".upload-",
        suffix=f".{ext}",
        dir=UPLOADED_VIDEO_DIR,
    )
    os.close(temp_fd)  # re-open as a Python file object below.

    bytes_written = 0
    chunk_size = 1024 * 1024  # 1 MiB - balances memory and syscall overhead.

    try:
        with open(temp_path, "wb") as out:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > UPLOAD_MAX_SIZE_BYTES:
                    logger.warning(
                        "Upload rejected mid-stream: bytes_written=%d exceeds limit=%d",
                        bytes_written,
                        UPLOAD_MAX_SIZE_BYTES,
                    )
                    return _upload_error_response(
                        schemas.VideoUploadErrorKind.FILE_TOO_LARGE,
                        (
                            f"File is too large (over {UPLOAD_MAX_SIZE_BYTES} bytes). "
                            f"Maximum allowed size is {UPLOAD_MAX_SIZE_BYTES} bytes."
                        ),
                        found=bytes_written,
                        allowed=[UPLOAD_MAX_SIZE_BYTES],
                    )
                out.write(chunk)

        logger.debug(
            "Wrote %d bytes to temp file %s for '%s'",
            bytes_written,
            temp_path,
            safe_filename,
        )

        # ---- Stage 3: post-write validation via cv2 ------------------------

        container, codec = _probe_container_and_codec(temp_path)

        if container is None or codec is None:
            logger.warning(
                "Upload rejected: cv2 could not open '%s' (container=%s, codec=%s)",
                safe_filename,
                container,
                codec,
            )
            return _upload_error_response(
                schemas.VideoUploadErrorKind.INVALID_VIDEO,
                "The uploaded file cannot be opened as a video.",
                found=safe_filename,
            )

        if container not in UPLOAD_ALLOWED_CONTAINERS:
            logger.warning(
                "Upload rejected: unsupported container '%s' for '%s'",
                container,
                safe_filename,
            )
            return _upload_error_response(
                schemas.VideoUploadErrorKind.UNSUPPORTED_CONTAINER,
                (
                    f"Unsupported container '{container}'. "
                    f"Allowed containers: {', '.join(UPLOAD_ALLOWED_CONTAINERS)}."
                ),
                found=container,
                allowed=list(UPLOAD_ALLOWED_CONTAINERS),
            )

        if codec not in UPLOAD_ALLOWED_CODECS:
            logger.warning(
                "Upload rejected: unsupported codec '%s' for '%s'",
                codec,
                safe_filename,
            )
            return _upload_error_response(
                schemas.VideoUploadErrorKind.UNSUPPORTED_CODEC,
                (
                    f"Unsupported codec '{codec}'. "
                    f"Allowed codecs: {', '.join(UPLOAD_ALLOWED_CODECS)}."
                ),
                found=codec,
                allowed=list(UPLOAD_ALLOWED_CODECS),
            )

        # ---- Stage 4: commit to VideosManager ------------------------------

        try:
            original_video, _ts_video = videos_manager.register_uploaded_video(
                temp_path, safe_filename
            )
        except RuntimeError as e:
            # register_uploaded_video already cleans up partial artifacts.
            logger.error(
                "Failed to register uploaded video '%s': %s",
                safe_filename,
                e,
                exc_info=True,
            )
            return JSONResponse(
                status_code=500,
                content=schemas.MessageResponse(
                    message=f"Failed to finalise upload: {e}"
                ).model_dump(),
            )

        # `temp_path` has been moved by register_uploaded_video; clear the
        # reference so the finally block below does not try to delete it.
        temp_path = ""

        logger.info(
            "Uploaded video '%s' (%.2f MB) registered successfully",
            safe_filename,
            bytes_written / (1024 * 1024),
        )

        return _domain_to_schema_video(original_video)

    except Exception as e:
        logger.error(
            "Unexpected error while uploading '%s': %s",
            safe_filename,
            e,
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content=schemas.MessageResponse(
                message=f"Unexpected error during upload: {e}"
            ).model_dump(),
        )
    finally:
        # Always remove the temp file if it is still around (validation
        # rejected the upload, or an exception was raised before we moved
        # the file).
        if temp_path and os.path.isfile(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                logger.debug("Best-effort cleanup failed for temp file %s", temp_path)


def _domain_to_schema_video(video: DomainVideo) -> schemas.Video:
    """
    Convert an internal ``videos.Video`` into the public ``schemas.Video``
    response shape. Kept as a small helper so the conversion logic stays in
    exactly one place.
    """
    return schemas.Video(
        filename=video.filename,
        width=video.width,
        height=video.height,
        fps=video.fps,
        frame_count=video.frame_count,
        codec=video.codec,
        duration=video.duration,
        source=schemas.VideoSource(video.source),
        path=video.path,
    )
