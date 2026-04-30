import logging
import os
import tempfile
from typing import List

from fastapi import APIRouter, File, UploadFile, HTTPException, Query, Path
from fastapi.responses import JSONResponse

import api.api_schemas as schemas
from images import ARCHIVE_EXTENSIONS, ImagesManager

router = APIRouter()
logger = logging.getLogger("api.routes.images")


@router.get(
    "",
    operation_id="get_image_sets",
    summary="List all available image sets",
    response_model=List[schemas.ImageSet],
)
def get_image_sets():
    """
    **List all discovered image sets (directories) in INPUT_IMAGES_DIR.**

    ## Operation

    1. ImagesManager scans INPUT_IMAGES_DIR for subdirectories
    2. Counts image files in each subdirectory
    3. Returns array of ImageSet objects

    ## Response Format

    | Code | Description |
    |------|-------------|
    | 200  | JSON array of ImageSet objects (empty if none found) |
    | 500  | Runtime error while listing image sets |

    ## Example Response

    ```json
    [
      {
        "name": "traffic_dataset",
        "image_count": 120
      }
    ]
    ```
    """
    logger.debug("Received request for all image sets.")
    try:
        sets = ImagesManager().get_all_image_sets()
        logger.debug(f"Found {len(sets)} image sets.")
        return [
            schemas.ImageSet(name=s.name, image_count=s.image_count)
            for s in sets.values()
        ]
    except Exception:
        logger.error("Failed to list image sets", exc_info=True)
        return JSONResponse(
            content=schemas.MessageResponse(
                message="Unexpected error while listing image sets"
            ).model_dump(),
            status_code=500,
        )


@router.get(
    "/check-image-set-exists",
    operation_id="check_image_set_exists",
    summary="Check if an image set directory already exists",
    response_model=schemas.ImageSetExistsResponse,
)
def check_image_set_exists(
    name: str = Query(..., description="Image set (directory) name to check"),
):
    """
    **Check if an image set directory with the given name exists in INPUT_IMAGES_DIR.**

    ## Parameters
    - `name` (query) - Name of the image set directory to check

    ## Response Format

    | Code | Description |
    |------|-------------|
    | 200  | Returns ImageSetExistsResponse with exists boolean |

    ## Example Response

    ```json
    {
      "exists": true,
      "name": "traffic_dataset"
    }
    ```
    """
    logger.debug(f"Checking existence of image set directory: {name}")
    exists = ImagesManager().image_set_exists(name)
    logger.debug(f"Image set '{name}' exists: {exists}")
    return schemas.ImageSetExistsResponse(exists=exists, name=name)


@router.post(
    "/upload",
    operation_id="upload_image_archive",
    summary="Upload a new image set as an archive",
    response_model=schemas.ImageSet,
    status_code=201,
)
async def upload_image_archive(file: UploadFile = File(...)):
    """
    **Upload an archive of images. The archive is extracted into its own directory under INPUT_IMAGES_DIR.**

    ## Operation

    1. Validate archive extension against supported formats
    2. Derive image set directory name from archive filename (without extension)
    3. Reject if a directory with that name already exists
    4. Save archive to a temp location, then extract safely into the target directory
    5. Return ImageSet object with the discovered image count

    ## Parameters
    - `file` (multipart/form-data) - Archive file to upload (zip, tar, tar.gz, tgz)

    ## Response Format

    | Code | Description |
    |------|-------------|
    | 201  | Archive uploaded and extracted, returns ImageSet object |
    | 400  | Invalid archive (unsupported extension, duplicate name, unsafe paths, no images) |
    | 500  | Error during upload or extraction |

    ## Example Response

    ```json
    {
      "name": "traffic_dataset",
      "image_count": 120
    }
    ```
    """
    logger.info(f"Received image archive upload request: {file.filename}")

    if not file.filename:
        logger.warning("Upload request without filename")
        raise HTTPException(status_code=400, detail="No filename provided")

    manager = ImagesManager()

    # Validate archive extension and derive set name
    set_name = manager.derive_set_name(file.filename)
    if not set_name:
        logger.warning(f"Unsupported archive extension: {file.filename}")
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported archive format. Allowed extensions: "
                + ", ".join(ARCHIVE_EXTENSIONS)
            ),
        )

    # Check for duplicate set name
    if manager.image_set_exists(set_name):
        logger.warning(f"Image set already exists: {set_name}")
        raise HTTPException(
            status_code=400, detail=f"Image set '{set_name}' already exists"
        )

    # Save archive to a temp file, then hand off to the manager for extraction
    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix="img_archive_", suffix="_" + file.filename
    )
    os.close(tmp_fd)

    try:
        chunk_size = 8192
        logger.debug(f"Saving archive to temp path {tmp_path}")
        with open(tmp_path, "wb") as f:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)

        archive_size = os.path.getsize(tmp_path)
        logger.info(
            f"Archive '{file.filename}' saved ({archive_size / (1024 * 1024):.2f} MB); extracting..."
        )

        image_set = manager.extract_archive(tmp_path, set_name)

        logger.info(
            f"Successfully extracted image set '{set_name}' ({image_set.image_count} images)"
        )
        return schemas.ImageSet(name=image_set.name, image_count=image_set.image_count)

    except FileExistsError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        # Unsupported archive type, corrupted archive, unsafe paths, or no images
        logger.warning(f"Rejected archive '{file.filename}': {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error uploading image archive '{file.filename}': {e}", exc_info=True
        )
        raise HTTPException(
            status_code=500, detail=f"Error uploading image archive: {str(e)}"
        )
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


@router.get(
    "/{name}",
    operation_id="list_images_in_set",
    summary="List all images inside a given image set",
    response_model=List[schemas.ImageInfo],
)
def list_images_in_set(
    name: str = Path(..., description="Name of the image set directory"),
):
    """
    **List all image files in the given image set with per-file metadata.**

    ## Operation

    1. Validate the image set name and ensure the directory exists
    2. Recursively walk the set directory for supported image extensions
    3. For each image, collect filename, extension, size, and dimensions
    4. Return the list sorted by filename

    ## Parameters
    - `name` (path) - Name of the image set directory

    ## Response Format

    | Code | Description |
    |------|-------------|
    | 200  | JSON array of ImageInfo objects (empty if the set has no images) |
    | 404  | Image set with the given name does not exist |
    | 500  | Runtime error while listing images |

    ## Example Response

    ```json
    [
      {
        "filename": "frame_0001.jpg",
        "extension": "jpg",
        "size_bytes": 204812,
        "width": 1920,
        "height": 1080
      }
    ]
    ```
    """
    logger.debug(f"Received request for images in set '{name}'.")
    try:
        images = ImagesManager().get_images_in_set(name)
        if images is None:
            logger.warning(f"Image set '{name}' not found.")
            raise HTTPException(status_code=404, detail=f"Image set '{name}' not found")

        logger.debug(f"Found {len(images)} images in set '{name}'.")
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
    except HTTPException:
        raise
    except Exception:
        logger.error(f"Failed to list images for set '{name}'", exc_info=True)
        return JSONResponse(
            content=schemas.MessageResponse(
                message="Unexpected error while listing images"
            ).model_dump(),
            status_code=500,
        )
