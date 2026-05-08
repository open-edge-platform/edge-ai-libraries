"""
HTTP routes for the image-set feature.
Mirrors the patterns used by the videos router:
- Streaming upload with a per-chunk size cap (no Content-Length header
  in the public schema; size is enforced mid-stream).
- Hybrid 422 error envelope with both a human-readable ``detail`` and a
  machine-readable ``error`` / ``found`` / ``allowed`` triple.
- All filesystem mutations are delegated to ``ImagesManager`` so the
  router stays thin.
"""

import logging
import os
import tempfile
from fastapi import APIRouter, File, Path, Query, UploadFile
from fastapi.responses import JSONResponse
import api.api_schemas as schemas
from images import (
    ARCHIVE_EXTENSIONS,
    UPLOADED_IMAGES_DIR,
    ImageSet as DomainImageSet,
    ImageUploadError,
    ImageUploadErrorKind,
    ImagesManager,
)

router = APIRouter()
logger = logging.getLogger("api.routes.images")


# --------------------------------------------------------------------------- #
# Configuration (resolved at import time so the router stays stateless).
# --------------------------------------------------------------------------- #
def _parse_int_env(name: str, default: int) -> int:
    """
    Parse an integer environment variable; fall back to ``default`` on
    any parsing error and log a warning.
    """
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "Invalid integer for env var %s=%r, falling back to %d",
            name,
            raw,
            default,
        )
        return default


# Default 2 GiB; matches the videos endpoint and nginx
# ``client_max_body_size 2G;`` in ui/nginx.conf.
_DEFAULT_UPLOAD_MAX_SIZE_BYTES = 2 * 1024 * 1024 * 1024
UPLOAD_MAX_SIZE_BYTES: int = _parse_int_env(
    "UPLOAD_MAX_SIZE_BYTES",
    _DEFAULT_UPLOAD_MAX_SIZE_BYTES,
)
# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #
# Mapping from the manager's literal error-kind strings to the API enum
# values. Centralised so the manager (which has no FastAPI dependency)
# stays decoupled from the schema layer.
_ERROR_KIND_MAP: dict[str, schemas.ImageUploadErrorKind] = {
    "missing_filename": schemas.ImageUploadErrorKind.MISSING_FILENAME,
    "unsupported_archive_format": (
        schemas.ImageUploadErrorKind.UNSUPPORTED_ARCHIVE_FORMAT
    ),
    "invalid_archive_name": schemas.ImageUploadErrorKind.INVALID_ARCHIVE_NAME,
    "archive_too_large": schemas.ImageUploadErrorKind.ARCHIVE_TOO_LARGE,
    "archive_corrupted": schemas.ImageUploadErrorKind.ARCHIVE_CORRUPTED,
    "archive_contains_subdirectories": (
        schemas.ImageUploadErrorKind.ARCHIVE_CONTAINS_SUBDIRECTORIES
    ),
    "archive_contains_no_images": (
        schemas.ImageUploadErrorKind.ARCHIVE_CONTAINS_NO_IMAGES
    ),
    "archive_mixed_image_extensions": (
        schemas.ImageUploadErrorKind.ARCHIVE_MIXED_IMAGE_EXTENSIONS
    ),
    "archive_disallowed_image_extension": (
        schemas.ImageUploadErrorKind.ARCHIVE_DISALLOWED_IMAGE_EXTENSION
    ),
    "archive_mixed_image_resolutions": (
        schemas.ImageUploadErrorKind.ARCHIVE_MIXED_IMAGE_RESOLUTIONS
    ),
    "archive_uncompressed_too_large": (
        schemas.ImageUploadErrorKind.ARCHIVE_UNCOMPRESSED_TOO_LARGE
    ),
    "image_set_already_exists": schemas.ImageUploadErrorKind.IMAGE_SET_ALREADY_EXISTS,
    "unsafe_archive_path": schemas.ImageUploadErrorKind.UNSAFE_ARCHIVE_PATH,
}


def _upload_error_response(
    kind: ImageUploadErrorKind,
    detail: str,
    *,
    found: object | None = None,
    allowed: list[object] | None = None,
) -> JSONResponse:
    """
    Build a uniform HTTP 422 response body for upload rejections.
    Using a single helper guarantees every rejection path returns the
    same shape and the same status code.
    """
    schema_kind = _ERROR_KIND_MAP.get(kind)
    if schema_kind is None:
        # Should never happen - guards against future drift between the
        # manager's literal strings and the API enum.
        logger.error("Unknown image upload error kind: %r", kind)
        schema_kind = schemas.ImageUploadErrorKind.ARCHIVE_CORRUPTED
    payload = schemas.ImageUploadError(
        detail=detail,
        error=schema_kind,
        found=found,
        allowed=allowed,
    )
    return JSONResponse(status_code=422, content=payload.model_dump())


def _to_schema(image_set: DomainImageSet) -> schemas.ImageSet:
    """
    Convert an internal ``images.ImageSet`` into the public schema
    response shape. Centralised so the conversion lives in one place.
    """
    return schemas.ImageSet(
        name=image_set.name,
        source_archive=image_set.source_archive,
        image_count=image_set.image_count,
        extension=image_set.extension,
        width=image_set.width,
        height=image_set.height,
        uploaded_at=image_set.uploaded_at,
    )


# --------------------------------------------------------------------------- #
# Routes.
# --------------------------------------------------------------------------- #
@router.get(
    "",
    operation_id="get_image_sets",
    summary="List all available image sets",
    response_model=list[schemas.ImageSet],
)
async def get_image_sets() -> list[schemas.ImageSet] | JSONResponse:
    """
    **List all discovered image sets with their canonical metadata.**

    ## Operation

    1. `ImagesManager` scans `UPLOADED_IMAGES_DIR` for subdirectories.
    2. For each directory, the canonical metadata is loaded from the
       sidecar `set.json`. Directories without a readable `set.json`
       are skipped (with a warning) so the endpoint never fails because
       of a partially populated shared volume.
    3. Returns an array of `ImageSet` objects.

    ## Parameters

    None

    ## Response Format

    | Code | Description |
    |------|-------------|
    | 200  | JSON array of `ImageSet` objects (empty if none found) |
    | 500  | Runtime error while listing image sets |

    ## Conditions

    ### ✅ Success
    - `ImagesManager` successfully initialized at startup
    - `UPLOADED_IMAGES_DIR` exists and is readable

    ### ❌ Failure
    - `ImagesManager` initialization fails → application exits at startup
    - Runtime errors → 500

    ## Example Response

    ```json
    [
      {
        "name": "traffic_dataset",
        "source_archive": "traffic_dataset.zip",
        "image_count": 120,
        "extension": "png",
        "width": 1920,
        "height": 1080,
        "uploaded_at": "2026-04-27T10:00:00Z"
      }
    ]
    ```
    """
    logger.debug("Received request for all image sets.")
    try:
        sets = ImagesManager().get_all_image_sets()
        logger.debug("Found %d image sets.", len(sets))
        return [_to_schema(s) for s in sets.values()]
    except Exception:
        logger.error("Failed to list image sets", exc_info=True)
        return JSONResponse(
            status_code=500,
            content=schemas.MessageResponse(
                message="Unexpected error while listing image sets"
            ).model_dump(),
        )


@router.get(
    "/check-image-set-exists",
    operation_id="check_image_set_exists",
    summary="Check if an image set directory already exists",
    response_model=schemas.ImageSetExistsResponse,
)
async def check_image_set_exists(
    name: str = Query(..., description="Image set (directory) name to check"),
) -> schemas.ImageSetExistsResponse:
    """
    **Check if an image set directory with the given name already exists.**

    Used by the UI to skip uploading a duplicate archive and to warn the
    user early. Always succeeds with a boolean response.

    ## Parameters

    - `name` (query) - Name of the image set directory to check.

    ## Response Format

    | Code | Description |
    |------|-------------|
    | 200  | Returns `ImageSetExistsResponse` with `exists` boolean |

    ## Conditions

    ### ✅ Success
    - Always succeeds with a boolean response

    ### ❌ Failure
    - None (this endpoint has no failure modes)

    ## Example Response

    ```json
    {
      "exists": true,
      "name": "traffic_dataset"
    }
    ```
    """
    logger.debug("Checking existence of image set directory: %s", name)
    exists = ImagesManager().image_set_exists(name)
    logger.debug("Image set '%s' exists: %s", name, exists)
    return schemas.ImageSetExistsResponse(exists=exists, name=name)


@router.post(
    "/upload",
    operation_id="upload_image_archive",
    summary="Upload a new image set as an archive",
    response_model=schemas.ImageSet,
    status_code=201,
    responses={
        422: {
            "model": schemas.ImageUploadError,
            "description": "Upload rejected by server-side validation.",
        },
        500: {
            "model": schemas.MessageResponse,
            "description": "Unexpected server error during upload or processing.",
        },
    },
)
async def upload_image_archive(
    file: UploadFile = File(...),
) -> JSONResponse | schemas.ImageSet:
    """
    **Upload an archive of images and commit it as a new image set
    under `UPLOADED_IMAGES_DIR`.**

    ## Operation

    1. **Pre-write validation** (before any bytes touch disk):
       - Filename is present.
       - The filename carries a supported archive extension and the
         sanitized trunk is not empty.
       - No image set with the derived name already exists.
    2. **Stream upload to a temporary file** under `UPLOADED_IMAGES_DIR`,
       enforcing `UPLOAD_MAX_SIZE_BYTES` per chunk. Aborts and deletes
       the temp file the moment the accumulated byte count exceeds the
       limit.
    3. **Validate + commit via `ImagesManager.register_uploaded_archive`**:
       - Safe extraction (zip-slip guard, sub-directories rejected,
         non-regular tar entries rejected).
       - Uncompressed-size cap to defuse zip-bombs
         (`UPLOAD_MAX_SIZE_BYTES × 10`).
       - All extracted files must be of one allowed image extension
         family and share the same resolution.
       - Every image is renamed to `<trunk>_<NNNN>.<ext>`.
       - `set.json` is written with the canonical metadata.
       - The staging directory is atomically renamed into its final
         location under a per-target lock so two concurrent uploads
         cannot both win the same name.

    Every validation rejection returns HTTP 422 with an
    `ImageUploadError` body containing both a human-readable `detail`
    field and a structured `error` / `found` / `allowed` triple.

    ## Parameters

    - `file` (multipart/form-data) - Archive file to upload (zip, tar,
      tar.gz, tgz).

    ## Response Format

    | Code | Description |
    |------|-------------|
    | 201  | Archive accepted; returns the new `ImageSet` metadata |
    | 422  | Upload rejected (`ImageUploadError` body with `error`, `found`, `allowed`, `detail`) |
    | 500  | Unexpected server error (for example disk full during the commit) |

    ## Conditions

    ### ✅ Success
    - Filename is present and carries a supported archive extension
    - Sanitised trunk is non-empty
    - Archive size is within `UPLOAD_MAX_SIZE_BYTES`
    - Total uncompressed size is within
      `UPLOAD_MAX_SIZE_BYTES × 10` (zip-bomb guard)
    - Archive is a flat collection of images, all of the same extension
      family and the same resolution
    - No image set with the derived name already exists
    - `set.json` is written successfully and the staging directory is
      moved into its final location

    ### ❌ Failure
    - Missing filename → 422 (`missing_filename`)
    - Unsupported archive extension → 422 (`unsupported_archive_format`)
    - Filename sanitizes to an empty trunk → 422 (`invalid_archive_name`)
    - Image set with the derived name already exists → 422 (`image_set_already_exists`)
    - Archive too large → 422 (`archive_too_large`)
    - Archive corrupted or contains an undecodable image → 422 (`archive_corrupted`)
    - Archive contains sub-directories → 422 (`archive_contains_subdirectories`)
    - Archive contains no supported images → 422 (`archive_contains_no_images`)
    - Archive mixes image extensions → 422 (`archive_mixed_image_extensions`)
    - Archive contains a disallowed file extension → 422 (`archive_disallowed_image_extension`)
    - Archive contains images of different resolutions → 422 (`archive_mixed_image_resolutions`)
    - Total uncompressed size exceeds the zip-bomb guard → 422 (`archive_uncompressed_too_large`)
    - Archive contains an unsafe path or non-regular entry → 422 (`unsafe_archive_path`)
    - Disk move or other I/O failure during commit → 500
    - Any other unexpected runtime error → 500

    ## Example success response (HTTP 201)

    ```json
    {
      "name": "traffic_dataset",
      "source_archive": "Traffic Dataset.zip",
      "image_count": 120,
      "extension": "png",
      "width": 1920,
      "height": 1080,
      "uploaded_at": "2026-04-27T10:00:00Z"
    }
    ```

    ## Example error response (HTTP 422, mixed image extensions)

    ```json
    {
      "detail": "Archive must contain images of exactly one type. Found multiple: ['jpg', 'png'].",
      "error": "archive_mixed_image_extensions",
      "found": ["jpg", "png"],
      "allowed": null
    }
    ```

    ## Example error response (HTTP 422, archive too large)

    ```json
    {
      "detail": "Archive is too large (over 2147483648 bytes). Maximum allowed size is 2147483648 bytes.",
      "error": "archive_too_large",
      "found": 3221225472,
      "allowed": [2147483648]
    }
    ```
    """
    raw_filename = file.filename
    logger.info("Received image archive upload request: %s", raw_filename)

    # ---- Stage 1: pre-write validation ----------------------------------

    if not raw_filename:
        logger.warning("Upload rejected: missing filename")
        return _upload_error_response(
            "missing_filename",
            "Upload is missing a valid filename.",
            found=raw_filename,
        )

    manager = ImagesManager()

    # Validate extension explicitly before touching disk so the request
    # is rejected as cheaply as possible. The manager re-checks during
    # ``register_uploaded_archive`` for callers that bypass the API.
    trunk = manager.derive_trunk(raw_filename)
    if trunk is None:
        # Two distinct sub-cases: unsupported extension vs sanitization
        # collapsed to empty. Surface both as ``unsupported_archive_format``
        # if the extension is missing, otherwise as ``invalid_archive_name``.
        lower = raw_filename.lower()
        has_supported_ext = any(lower.endswith("." + ext) for ext in ARCHIVE_EXTENSIONS)
        if not has_supported_ext:
            logger.warning(
                "Upload rejected: unsupported archive extension for %r",
                raw_filename,
            )
            return _upload_error_response(
                "unsupported_archive_format",
                (
                    f"Unsupported archive format for '{raw_filename}'. "
                    f"Allowed extensions: {', '.join(ARCHIVE_EXTENSIONS)}."
                ),
                found=raw_filename,
                allowed=list(ARCHIVE_EXTENSIONS),
            )
        logger.warning(
            "Upload rejected: archive name %r sanitises to empty trunk",
            raw_filename,
        )
        return _upload_error_response(
            "invalid_archive_name",
            f"Archive filename '{raw_filename}' sanitises to an empty name.",
            found=raw_filename,
        )

    if manager.image_set_exists(trunk):
        logger.warning("Upload rejected: image set '%s' already exists", trunk)
        return _upload_error_response(
            "image_set_already_exists",
            f"An image set named '{trunk}' already exists.",
            found=trunk,
        )

    # ---- Stage 2: stream to temp file under the uploads root ------------

    # Ensure the uploads root exists before mkstemp - the manager's
    # constructor takes care of this on its first call, but a freshly
    # cleaned shared volume might still need it.
    ImagesManager.ensure_root_dir()

    temp_fd, temp_path = tempfile.mkstemp(
        prefix=".upload-",
        suffix=os.path.splitext(raw_filename)[1] or ".bin",
        dir=UPLOADED_IMAGES_DIR,
    )
    os.close(temp_fd)

    bytes_written = 0
    chunk_size = 1024 * 1024  # 1 MiB

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
                        "archive_too_large",
                        (
                            f"Archive is too large (over {UPLOAD_MAX_SIZE_BYTES} bytes). "
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
            raw_filename,
        )

        # ---- Stage 3: validate + commit via the manager -----------------

        try:
            image_set = manager.register_uploaded_archive(temp_path, raw_filename)
        except ImageUploadError as exc:
            logger.warning(
                "Upload rejected by validator: kind=%s detail=%s",
                exc.kind,
                exc.detail,
            )
            return _upload_error_response(
                exc.kind,
                exc.detail,
                found=exc.found,
                allowed=exc.allowed,
            )
        except RuntimeError as exc:
            logger.error(
                "Failed to register uploaded archive '%s': %s",
                raw_filename,
                exc,
                exc_info=True,
            )
            return JSONResponse(
                status_code=500,
                content=schemas.MessageResponse(
                    message=f"Failed to finalise upload: {exc}"
                ).model_dump(),
            )

        logger.info(
            "Uploaded image set '%s' (%.2f MB) registered successfully",
            image_set.name,
            bytes_written / (1024 * 1024),
        )
        return _to_schema(image_set)

    except Exception as exc:
        logger.error(
            "Unexpected error while uploading '%s': %s",
            raw_filename,
            exc,
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content=schemas.MessageResponse(
                message=f"Unexpected error during upload: {exc}"
            ).model_dump(),
        )
    finally:
        # Always remove the temp archive once the manager has either
        # consumed it or rejected it.
        if os.path.isfile(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                logger.debug("Best-effort cleanup failed for temp file %s", temp_path)


@router.get(
    "/{name}",
    operation_id="list_images_in_set",
    summary="List all images inside a given image set",
    response_model=list[schemas.ImageInfo],
)
async def list_images_in_set(
    name: str = Path(..., description="Name of the image set directory"),
) -> list[schemas.ImageInfo] | JSONResponse:
    """
    **List all image files in the given image set with per-file metadata.**

    ## Operation

    1. Resolve the image set by name and load its canonical metadata
       from `set.json`. If either the directory or the sidecar is
       missing the request is treated as 404.
    2. Iterate over the (flat) directory in alphabetical order and
       collect every file whose extension matches the canonical
       extension recorded in `set.json`. The sidecar itself is excluded
       from the listing.
    3. For each entry, stat the file for its size; width and height
       come straight from `set.json` because every image in a set
       shares the same resolution by construction (no per-call OpenCV
       probing).

    ## Parameters

    - `name` (path) - Name of the image set directory.

    ## Response Format

    | Code | Description |
    |------|-------------|
    | 200  | JSON array of `ImageInfo` objects (empty if the set has no images) |
    | 404  | Image set with the given name does not exist or has no readable `set.json` |
    | 500  | Runtime error while listing images |

    ## Conditions

    ### ✅ Success
    - Image set directory exists under `UPLOADED_IMAGES_DIR`
    - Sidecar `set.json` is readable

    ### ❌ Failure
    - Image set name unknown or missing → 404
    - Unhandled runtime error → 500

    ## Example Response

    ```json
    [
      {
        "filename": "traffic_dataset_001.png",
        "extension": "png",
        "size_bytes": 204812,
        "width": 1920,
        "height": 1080
      }
    ]
    ```
    """
    logger.debug("Received request for images in set '%s'.", name)
    try:
        images = ImagesManager().get_images_in_set(name)
        if images is None:
            logger.warning("Image set '%s' not found.", name)
            return JSONResponse(
                status_code=404,
                content=schemas.MessageResponse(
                    message=f"Image set '{name}' not found"
                ).model_dump(),
            )

        logger.debug("Found %d images in set '%s'.", len(images), name)
        return [
            schemas.ImageInfo(
                filename=img.filename,
                extension=img.extension,
                size_bytes=img.size_bytes,
                width=img.width,
                height=img.height,
            )
            for img in images
        ]

    except Exception:
        logger.error("Failed to list images for set '%s'", name, exc_info=True)
        return JSONResponse(
            status_code=500,
            content=schemas.MessageResponse(
                message="Unexpected error while listing images"
            ).model_dump(),
        )
