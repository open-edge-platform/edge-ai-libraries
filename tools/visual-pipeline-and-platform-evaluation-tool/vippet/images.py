import logging
import os
import shutil
import tarfile
import threading
import zipfile
from dataclasses import dataclass
from typing import Dict, List, Optional

import cv2

logger = logging.getLogger("images")

# Default directory for input image sets
_INPUT_IMAGES_DIR = "shared/images/input"

# Read path from environment, falling back to default
INPUT_IMAGES_DIR: str = os.path.normpath(
    os.environ.get("INPUT_IMAGES_DIR", _INPUT_IMAGES_DIR)
)

# Supported archive extensions (lowercase, without leading dot).
# Multi-part extensions (e.g. "tar.gz") are matched against full filename.
ARCHIVE_EXTENSIONS = (
    "zip",
    "tar",
    "tar.gz",
    "tgz",
)

# Supported image file extensions (lowercase, without leading dot)
IMAGE_EXTENSIONS = (
    "jpg",
    "jpeg",
    "png",
    "bmp",
    "webp",
    "tif",
    "tiff",
)


@dataclass
class ImageSet:
    """
    Represents a directory of images under INPUT_IMAGES_DIR.
    """

    name: str
    image_count: int

    def to_dict(self) -> dict:
        return {"name": self.name, "image_count": self.image_count}


@dataclass
class ImageInfo:
    """
    Represents a single image file in an image set.
    """

    filename: str
    extension: str
    size_bytes: int
    width: Optional[int]
    height: Optional[int]

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "extension": self.extension,
            "size_bytes": self.size_bytes,
            "width": self.width,
            "height": self.height,
        }


class ImagesManager:
    """
    Thread-safe singleton that manages image sets stored as subdirectories of INPUT_IMAGES_DIR.

    Each image set is a directory containing image files. Archives uploaded via
    `extract_archive` are extracted into their own subdirectory.

    Create instances with ImagesManager() to get the shared singleton instance.
    """

    _instance: Optional["ImagesManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "ImagesManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        # Protect against multiple initialization
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        logger.debug(
            f"Initializing ImagesManager with INPUT_IMAGES_DIR={INPUT_IMAGES_DIR}"
        )
        os.makedirs(INPUT_IMAGES_DIR, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def get_all_image_sets(self) -> Dict[str, ImageSet]:
        """
        Returns a dict mapping set name to ImageSet for all subdirectories
        of INPUT_IMAGES_DIR.
        """
        result: Dict[str, ImageSet] = {}
        if not os.path.isdir(INPUT_IMAGES_DIR):
            return result

        for entry in sorted(os.listdir(INPUT_IMAGES_DIR)):
            full = os.path.join(INPUT_IMAGES_DIR, entry)
            if os.path.isdir(full):
                result[entry] = ImageSet(
                    name=entry, image_count=self._count_images(full)
                )
        return result

    def image_set_exists(self, name: str) -> bool:
        """
        Returns True if an image set with the given name exists as a directory
        under INPUT_IMAGES_DIR. Rejects names containing path separators.
        """
        if not self._is_safe_set_name(name):
            return False
        return os.path.isdir(os.path.join(INPUT_IMAGES_DIR, name))

    def get_image_set_path(self, name: str) -> Optional[str]:
        """
        Returns the full path to the image set directory, or None if not found.
        """
        if not self.image_set_exists(name):
            return None
        return os.path.join(INPUT_IMAGES_DIR, name)

    def get_images_in_set(self, name: str) -> Optional[List[ImageInfo]]:
        """
        Returns a list of ImageInfo objects describing every image file in the
        given image set directory. Returns None if the set does not exist.

        The set directory is walked recursively; only files with supported
        IMAGE_EXTENSIONS are included. The returned list is sorted by filename
        (as relative path from the set root).
        """
        set_path = self.get_image_set_path(name)
        if set_path is None:
            return None

        images: List[ImageInfo] = []
        for root, _dirs, files in os.walk(set_path):
            for fname in files:
                ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
                if ext not in IMAGE_EXTENSIONS:
                    continue

                full_path = os.path.join(root, fname)
                rel_path = os.path.relpath(full_path, set_path).replace(os.sep, "/")

                try:
                    size_bytes = os.path.getsize(full_path)
                except OSError as e:
                    logger.warning(f"Failed to stat image '{full_path}': {e}")
                    size_bytes = 0

                width, height = self._read_image_dimensions(full_path)

                images.append(
                    ImageInfo(
                        filename=rel_path,
                        extension=ext,
                        size_bytes=size_bytes,
                        width=width,
                        height=height,
                    )
                )

        images.sort(key=lambda i: i.filename)
        return images

    @staticmethod
    def derive_set_name(archive_filename: str) -> Optional[str]:
        """
        Derive the image-set directory name from an archive filename by
        stripping its supported extension. Returns None for unsupported
        extensions or empty basenames.
        """
        if not archive_filename:
            return None
        lower = archive_filename.lower()
        stripped: Optional[str] = None
        for ext in sorted(ARCHIVE_EXTENSIONS, key=len, reverse=True):
            if lower.endswith("." + ext):
                stripped = archive_filename[: -(len(ext) + 1)]
                break
        if stripped is None:
            return None

        # Drop any path components the client may have sent
        name = os.path.basename(stripped)
        if not name or name in (".", ".."):
            return None
        return name

    def extract_archive(self, archive_path: str, set_name: str) -> ImageSet:
        """
        Extracts the archive at `archive_path` into INPUT_IMAGES_DIR/<set_name>.

        Caller is responsible for validating `set_name` (via `derive_set_name`)
        and ensuring no existing set collides (via `image_set_exists`).

        Raises:
            FileExistsError: If the target directory already exists.
            ValueError: If the archive type is unsupported, the archive is
                corrupted, contains unsafe paths (zip-slip), or contains no
                supported images. On failure the target directory is cleaned up.
        """
        if not self._is_safe_set_name(set_name):
            raise ValueError(f"Invalid image set name: {set_name!r}")

        target_dir = os.path.join(INPUT_IMAGES_DIR, set_name)
        if os.path.exists(target_dir):
            raise FileExistsError(f"Image set '{set_name}' already exists")

        os.makedirs(INPUT_IMAGES_DIR, exist_ok=True)
        os.makedirs(target_dir, exist_ok=False)

        try:
            lower = archive_path.lower()
            if lower.endswith(".zip"):
                self._safe_extract_zip(archive_path, target_dir)
            else:
                # tar, tar.gz, tgz
                self._safe_extract_tar(archive_path, target_dir)

            image_count = self._count_images(target_dir)
            if image_count == 0:
                raise ValueError(
                    "Archive contains no supported images. Allowed extensions: "
                    + ", ".join(IMAGE_EXTENSIONS)
                )

            logger.info(f"Extracted image set '{set_name}' ({image_count} images)")
            return ImageSet(name=set_name, image_count=image_count)

        except (zipfile.BadZipFile, tarfile.TarError) as e:
            shutil.rmtree(target_dir, ignore_errors=True)
            raise ValueError(f"Corrupted archive: {e}") from e
        except Exception:
            shutil.rmtree(target_dir, ignore_errors=True)
            raise

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    @staticmethod
    def _is_safe_set_name(name: str) -> bool:
        if not name or name in (".", ".."):
            return False
        if os.sep in name:
            return False
        if os.altsep and os.altsep in name:
            return False
        return True

    @staticmethod
    def _count_images(directory: str) -> int:
        count = 0
        for _root, _dirs, files in os.walk(directory):
            for name in files:
                ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
                if ext in IMAGE_EXTENSIONS:
                    count += 1
        return count

    @staticmethod
    def _read_image_dimensions(
        file_path: str,
    ) -> tuple[Optional[int], Optional[int]]:
        """
        Reads (width, height) from an image file using OpenCV.
        Returns (None, None) if the image cannot be read.
        """
        try:
            img = cv2.imread(file_path, cv2.IMREAD_UNCHANGED)
        except Exception as e:
            logger.warning(f"Failed to read image '{file_path}': {e}")
            return None, None
        if img is None:
            return None, None
        h, w = img.shape[:2]
        return int(w), int(h)

    @staticmethod
    def _is_within_directory(base: str, target: str) -> bool:
        base_abs = os.path.abspath(base)
        target_abs = os.path.abspath(target)
        try:
            return os.path.commonpath([base_abs, target_abs]) == base_abs
        except ValueError:
            # Different drives on Windows
            return False

    @classmethod
    def _safe_extract_zip(cls, archive_path: str, dest_dir: str) -> None:
        with zipfile.ZipFile(archive_path) as zf:
            members = zf.namelist()
            for member in members:
                member_path = os.path.join(dest_dir, member)
                if not cls._is_within_directory(dest_dir, member_path):
                    raise ValueError("Archive contains unsafe paths (path traversal).")
            zf.extractall(dest_dir, members=members)

    @classmethod
    def _safe_extract_tar(cls, archive_path: str, dest_dir: str) -> None:
        with tarfile.open(archive_path) as tf:
            members = tf.getmembers()
            for member in members:
                member_path = os.path.join(dest_dir, member.name)
                if not cls._is_within_directory(dest_dir, member_path):
                    raise ValueError("Archive contains unsafe paths (path traversal).")
            tf.extractall(dest_dir, members=members)


def list_image_sets() -> List[ImageSet]:
    """Convenience helper mirroring videos-style module-level usage."""
    return list(ImagesManager().get_all_image_sets().values())
