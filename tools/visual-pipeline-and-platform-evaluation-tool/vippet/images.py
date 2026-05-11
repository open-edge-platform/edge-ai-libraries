"""
Image-set storage and validation.

This module owns the lifecycle of image sets uploaded via the API:
extracting archives into an isolated layout, validating their contents
against a strict set of rules, renaming images to a deterministic
sequence, and persisting a sidecar ``set.json`` with the canonical
metadata used by the rest of the application.

Public surface:
    - ImagesManager (singleton): scan / register / resolve image sets.
    - ImageSet (dataclass): canonical metadata for one image set.
    - ImageInfo (dataclass): per-image metadata (filename, size, dims).
    - ImageUploadError + ImageUploadErrorKind: structured validation
      errors consumed by the API layer.

Storage layout::

    <UPLOADED_IMAGES_DIR>/<trunk>/<trunk>_0001.<ext>
    <UPLOADED_IMAGES_DIR>/<trunk>/<trunk>_0002.<ext>
    ...
    <UPLOADED_IMAGES_DIR>/<trunk>/set.json

Every image inside one set has the same extension and the same
resolution; this is enforced at upload time and reflected by
``set.json``.
"""

import json
import logging
import os
import re
import shutil
import tarfile
import tempfile
import threading
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

import cv2

logger = logging.getLogger("images")


# --------------------------------------------------------------------------- #
# Configuration (module-level for ergonomics; resolved once at import time so
# tests and runtime share the same view of the environment).
# --------------------------------------------------------------------------- #

# Default location of the uploaded image sets on disk. Matches the shared
# volume layout declared in compose.yml.
_UPLOADED_IMAGES_DIR = "/images/input/uploaded"

UPLOADED_IMAGES_DIR: str = os.path.normpath(
    os.environ.get("UPLOADED_IMAGES_DIR", _UPLOADED_IMAGES_DIR)
)

# Supported archive extensions (lowercase, no leading dot). Multipart
# extensions like ``tar.gz`` are matched against the full filename.
ARCHIVE_EXTENSIONS: tuple[str, ...] = (
    "zip",
    "tar",
    "tar.gz",
    "tgz",
)

# Image extensions accepted by the validator. Each one must have a
# software GStreamer decoder available so that pipeline integration can
# always produce a working ``multifilesrc -> *dec`` chain.
IMAGE_EXTENSIONS: tuple[str, ...] = (
    "jpg",
    "jpeg",
    "png",
    "bmp",
    "tif",
    "tiff",
)

# Map every accepted image extension to its canonical family member.
# ``jpeg`` and ``jpg`` are normalized to ``jpg``; ``tiff`` is normalized
# to ``tif``. The canonical value is what ends up on disk and inside
# ``set.json``.
_EXTENSION_FAMILIES: dict[str, str] = {
    "jpg": "jpg",
    "jpeg": "jpg",
    "png": "png",
    "bmp": "bmp",
    "tif": "tif",
    "tiff": "tif",
}

# Hardcoded multiplier guarding against zip-bombs. The total uncompressed
# size must not exceed ``UPLOAD_MAX_SIZE_BYTES * _UNCOMPRESSED_RATIO``.
_UNCOMPRESSED_RATIO = 10

# Conservative pattern for the sanitized archive trunk that becomes the
# directory name and the prefix of every renamed image. Matches the
# scheme used for video uploads.
_SAFE_TRUNK_RE = re.compile(r"[^A-Za-z0-9_-]+")


def _resolve_max_size_bytes() -> int:
    """
    Resolve ``UPLOAD_MAX_SIZE_BYTES`` from the environment, falling back to
    2 GiB. Re-read on every call so tests can monkey-patch the env.
    """
    raw = os.environ.get("UPLOAD_MAX_SIZE_BYTES")
    if raw is None or raw.strip() == "":
        return 2 * 1024 * 1024 * 1024
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "Invalid integer for UPLOAD_MAX_SIZE_BYTES=%r, falling back to 2 GiB",
            raw,
        )
        return 2 * 1024 * 1024 * 1024


# --------------------------------------------------------------------------- #
# Validation result / exception types.
# --------------------------------------------------------------------------- #


# Machine-readable error kinds for image-archive uploads. Mirrors the
# ``VideoUploadErrorKind`` enum used for video uploads and is consumed by
# the API layer when building the structured 422 response body.
ImageUploadErrorKind = Literal[
    "missing_filename",
    "unsupported_archive_format",
    "archive_too_large",
    "archive_corrupted",
    "archive_contains_subdirectories",
    "archive_contains_no_images",
    "archive_mixed_image_extensions",
    "archive_disallowed_image_extension",
    "archive_mixed_image_resolutions",
    "archive_uncompressed_too_large",
    "image_set_already_exists",
    "invalid_archive_name",
    "unsafe_archive_path",
]


class ImageUploadError(Exception):
    """
    Validation error raised while preparing or extracting an image archive.

    Carries the structured fields the API needs to build a uniform 422
    response: machine-readable ``kind``, human-readable ``detail``, and
    the optional ``found`` / ``allowed`` triple.
    """

    def __init__(
        self,
        kind: ImageUploadErrorKind,
        detail: str,
        *,
        found: object | None = None,
        allowed: list[object] | None = None,
    ) -> None:
        super().__init__(detail)
        self.kind: ImageUploadErrorKind = kind
        self.detail = detail
        self.found = found
        self.allowed = allowed


# --------------------------------------------------------------------------- #
# Data classes.
# --------------------------------------------------------------------------- #


@dataclass
class ImageSet:
    """
    Canonical metadata for one image set, mirroring ``set.json`` on disk.

    Attributes:
        name: Sanitised trunk - matches the directory name and the
            common prefix of every image file inside it.
        source_archive: Original uploaded archive filename (untouched).
        image_count: Number of images in the set.
        extension: Canonical lowercase extension shared by every image
            (``jpg``, ``png``, ``bmp`` or ``tif``).
        width: Common image width in pixels.
        height: Common image height in pixels.
        uploaded_at: ISO-8601 UTC timestamp of when the set was created.
    """

    name: str
    source_archive: str
    image_count: int
    extension: str
    width: int
    height: int
    uploaded_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "source_archive": self.source_archive,
            "image_count": self.image_count,
            "extension": self.extension,
            "width": self.width,
            "height": self.height,
            "uploaded_at": self.uploaded_at,
        }

    @staticmethod
    def from_dict(data: dict) -> "ImageSet":
        """
        Build an ``ImageSet`` from a dictionary loaded from ``set.json``.

        Missing fields fall back to safe defaults so that minor schema
        drift between writes and reads does not break loading.
        """
        return ImageSet(
            name=str(data.get("name", "")),
            source_archive=str(data.get("source_archive", "")),
            image_count=int(data.get("image_count") or 0),
            extension=str(data.get("extension", "")),
            width=int(data.get("width") or 0),
            height=int(data.get("height") or 0),
            uploaded_at=str(data.get("uploaded_at", "")),
        )


@dataclass
class ImageInfo:
    """
    Per-image metadata returned by ``ImagesManager.get_images_in_set``.

    All fields are derived from ``set.json`` (no per-call OpenCV probing)
    except ``size_bytes``, which is stat()-ed on demand because file size
    is not part of the canonical metadata.
    """

    filename: str
    extension: str
    size_bytes: int
    width: int
    height: int

    def to_dict(self) -> dict[str, object]:
        return {
            "filename": self.filename,
            "extension": self.extension,
            "size_bytes": self.size_bytes,
            "width": self.width,
            "height": self.height,
        }


# --------------------------------------------------------------------------- #
# Internal helpers.
# --------------------------------------------------------------------------- #


def _canonical_extension(ext: str) -> str | None:
    """
    Map a raw lowercase extension to its canonical family member, or
    ``None`` if the extension is not in ``IMAGE_EXTENSIONS``.
    """
    return _EXTENSION_FAMILIES.get(ext.lower())


def _is_within_directory(base: str, target: str) -> bool:
    """
    Return True when ``target`` resolves to a path inside ``base``. Used
    to defeat zip-slip / tar-slip attacks before extraction.
    """
    base_abs = os.path.abspath(base)
    target_abs = os.path.abspath(target)
    try:
        return os.path.commonpath([base_abs, target_abs]) == base_abs
    except ValueError:
        # Different drives on Windows.
        return False


def _strip_archive_extension(filename: str) -> str | None:
    """
    Return the filename with its supported archive extension removed, or
    ``None`` if the filename does not end with one. Multipart extensions
    are tested first (longest match wins).
    """
    lower = filename.lower()
    for ext in sorted(ARCHIVE_EXTENSIONS, key=len, reverse=True):
        if lower.endswith("." + ext):
            return filename[: -(len(ext) + 1)]
    return None


def sanitise_trunk(raw: str) -> str | None:
    """
    Sanitize the archive trunk into a value safe for use as a directory
    name and filename prefix.

    Lower-cases the input, replaces every run of disallowed characters
    with a single underscore, then strips leading/trailing underscores.
    Returns ``None`` if the result is empty or made of dots only.
    """
    if not raw:
        return None
    lowered = raw.strip().lower()
    cleaned = _SAFE_TRUNK_RE.sub("_", lowered).strip("_")
    if not cleaned or cleaned in (".", ".."):
        return None
    return cleaned


def _now_iso() -> str:
    """Return the current UTC time formatted as an ISO-8601 string."""
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


# --------------------------------------------------------------------------- #
# Manager.
# --------------------------------------------------------------------------- #


class ImagesManager:
    """
    Thread-safe singleton that owns the on-disk image sets directory.

    All file-system operations go through this class so cross-cutting
    concerns - directory creation with the right permissions, atomic
    commit of the final image-set directory, race protection between
    concurrent uploads - live in exactly one place.
    """

    _instance: "ImagesManager | None" = None
    _lock = threading.Lock()
    # Serializes the commit phase of ``register_uploaded_archive`` so
    # two concurrent uploads cannot race past the "directory does not
    # yet exist" check.
    _upload_lock = threading.Lock()

    def __new__(cls) -> "ImagesManager":
        if cls._instance is None:
            with cls._lock:
                # Double-checked locking.
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        # Protect against re-initialization - the singleton constructor
        # may be called multiple times by callers that don't realize it
        # is shared.
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        logger.debug(
            "Initializing ImagesManager with UPLOADED_IMAGES_DIR=%s",
            UPLOADED_IMAGES_DIR,
        )
        self.ensure_root_dir()

    # ------------------------------------------------------------------ #
    # Directory bootstrap.
    # ------------------------------------------------------------------ #

    @staticmethod
    def ensure_root_dir() -> None:
        """
        Create ``UPLOADED_IMAGES_DIR`` with mode 0o755 if missing.

        ``os.makedirs`` is subject to the process umask and leaves an
        existing directory's permissions untouched, so we follow up with
        an explicit ``os.chmod`` to guarantee the mode in every case.
        """
        try:
            os.makedirs(UPLOADED_IMAGES_DIR, mode=0o755, exist_ok=True)
            os.chmod(UPLOADED_IMAGES_DIR, 0o755)
        except OSError as exc:
            raise RuntimeError(
                f"Failed to create image set root '{UPLOADED_IMAGES_DIR}': {exc}"
            ) from exc

    # ------------------------------------------------------------------ #
    # Discovery / lookup.
    # ------------------------------------------------------------------ #

    def get_all_image_sets(self) -> dict[str, ImageSet]:
        """
        Return all image sets currently on disk, keyed by name.

        Sets without a readable ``set.json`` are skipped with a warning -
        the sidecar is the source of truth and a missing one means the
        directory was not produced by this manager.
        """
        result: dict[str, ImageSet] = {}
        if not os.path.isdir(UPLOADED_IMAGES_DIR):
            return result

        for entry in sorted(os.listdir(UPLOADED_IMAGES_DIR)):
            full = os.path.join(UPLOADED_IMAGES_DIR, entry)
            if not os.path.isdir(full):
                continue
            # Skip in-flight staging directories created by
            # ``register_uploaded_archive``.
            if entry.startswith(".staging-"):
                continue
            image_set = self._load_set_json(full)
            if image_set is None:
                logger.warning(
                    "Skipping image set directory '%s' without a readable set.json",
                    entry,
                )
                continue
            # The directory name is the source of truth for the set name -
            # override whatever was persisted in case it drifted.
            image_set.name = entry
            result[entry] = image_set
        return result

    def image_set_exists(self, name: str) -> bool:
        """
        Return True if a directory with the given name exists under
        ``UPLOADED_IMAGES_DIR``. Names containing path separators are
        rejected to defend against path traversal.
        """
        if not self._is_safe_set_name(name):
            return False
        return os.path.isdir(os.path.join(UPLOADED_IMAGES_DIR, name))

    def get_image_set(self, name: str) -> ImageSet | None:
        """
        Return the canonical metadata for one image set, or ``None`` if
        either the directory or its ``set.json`` is missing.
        """
        if not self._is_safe_set_name(name):
            return None
        full = os.path.join(UPLOADED_IMAGES_DIR, name)
        if not os.path.isdir(full):
            return None
        image_set = self._load_set_json(full)
        if image_set is None:
            return None
        image_set.name = name
        return image_set

    def get_image_set_path(self, name: str) -> str | None:
        """
        Return the absolute path to the image set directory, or ``None``
        if the set does not exist.
        """
        if not self.image_set_exists(name):
            return None
        return os.path.join(UPLOADED_IMAGES_DIR, name)

    def get_images_in_set(self, name: str) -> list[ImageInfo] | None:
        """
        Return a sorted list of images in the given set, or ``None`` if
        the set does not exist.

        Width / height come from ``set.json`` (every image in a set
        shares the same resolution by construction); only the per-file
        size is stat()-ed on demand. The ``set.json`` sidecar itself is
        not included in the listing.
        """
        image_set = self.get_image_set(name)
        if image_set is None:
            return None

        set_dir = os.path.join(UPLOADED_IMAGES_DIR, name)
        result: list[ImageInfo] = []
        for entry in sorted(os.listdir(set_dir)):
            full = os.path.join(set_dir, entry)
            if not os.path.isfile(full):
                continue
            ext = entry.rsplit(".", 1)[-1].lower() if "." in entry else ""
            if ext != image_set.extension:
                # Skip set.json and any stray files of a different type.
                continue
            try:
                size_bytes = os.path.getsize(full)
            except OSError as exc:
                logger.warning("Failed to stat image '%s': %s", full, exc)
                size_bytes = 0
            result.append(
                ImageInfo(
                    filename=entry,
                    extension=ext,
                    size_bytes=size_bytes,
                    width=image_set.width,
                    height=image_set.height,
                )
            )
        return result

    def get_location_pattern(self, name: str) -> str | None:
        """
        Return the absolute ``multifilesrc`` location pattern for the
        given image set, or ``None`` if the set is missing.

        Example::

            /images/input/uploaded/dataset/dataset_%04d.png

        The ``%0Nd`` width matches the zero-padding used at upload time
        (``len(str(image_count))``).
        """
        image_set = self.get_image_set(name)
        if image_set is None:
            return None
        width = max(1, len(str(image_set.image_count)))
        filename = f"{image_set.name}_%0{width}d.{image_set.extension}"
        return os.path.join(UPLOADED_IMAGES_DIR, image_set.name, filename)

    # ------------------------------------------------------------------ #
    # Upload pipeline.
    # ------------------------------------------------------------------ #

    @staticmethod
    def derive_trunk(archive_filename: str) -> str | None:
        """
        Derive the sanitized trunk from an uploaded archive filename.

        Returns ``None`` if the filename does not carry a supported
        archive extension or if sanitization collapses to an empty
        string.
        """
        if not archive_filename:
            return None
        # Defend against client-supplied path components.
        basename = os.path.basename(archive_filename)
        stripped = _strip_archive_extension(basename)
        if stripped is None:
            return None
        return sanitise_trunk(stripped)

    def register_uploaded_archive(
        self,
        temp_archive_path: str,
        original_filename: str,
    ) -> ImageSet:
        """
        Validate an already-uploaded archive and commit it as a new
        image set under ``UPLOADED_IMAGES_DIR``.

        The caller is responsible for streaming the bytes to
        ``temp_archive_path`` and enforcing the request-body size cap;
        this method takes over from there:

        1. Derive and validate the sanitized trunk.
        2. Reject the upload if a set with that name already exists.
        3. Extract the archive into a temporary staging directory and
           run all content validations (flat layout, allowed image
           extensions, single image extension family, single resolution,
           uncompressed-size guard).
        4. Rename every image to ``<trunk>_<NNNN>.<ext>`` (deterministic
           alphabetical order, zero-padded width derived from the count).
        5. Write ``set.json`` and atomically move the staging directory
           into its final location.

        Raises:
            ImageUploadError: For any user-facing validation failure.
            RuntimeError: For unexpected I/O failures during commit.
        """
        trunk = self.derive_trunk(original_filename)
        if trunk is None:
            raise ImageUploadError(
                "invalid_archive_name",
                (
                    f"Archive filename '{original_filename}' is not a supported "
                    f"archive or sanitises to an empty name. Allowed extensions: "
                    f"{', '.join(ARCHIVE_EXTENSIONS)}."
                ),
                found=original_filename,
                allowed=list(ARCHIVE_EXTENSIONS),
            )

        # Cheap pre-check before extraction. The atomic reservation
        # below catches the race when two uploads with the same trunk
        # arrive concurrently.
        if self.image_set_exists(trunk):
            raise ImageUploadError(
                "image_set_already_exists",
                f"An image set named '{trunk}' already exists.",
                found=trunk,
            )

        max_uncompressed = _resolve_max_size_bytes() * _UNCOMPRESSED_RATIO

        # Stage the extraction inside a sibling temp directory so the
        # final move is a same-filesystem rename instead of a copy.
        self.ensure_root_dir()
        staging_dir = tempfile.mkdtemp(
            prefix=".staging-",
            dir=UPLOADED_IMAGES_DIR,
        )
        try:
            self._safe_extract(temp_archive_path, staging_dir, max_uncompressed)
            image_files = self._validate_extracted_contents(staging_dir)
            canonical_ext = self._enforce_single_extension(image_files)
            width, height = self._enforce_single_resolution(staging_dir, image_files)
            renamed = self._rename_images(
                staging_dir, image_files, trunk, canonical_ext
            )

            image_set = ImageSet(
                name=trunk,
                source_archive=os.path.basename(original_filename),
                image_count=len(renamed),
                extension=canonical_ext,
                width=width,
                height=height,
                uploaded_at=_now_iso(),
            )
            self._write_set_json(staging_dir, image_set)

            self._commit_staging(staging_dir, trunk)
            logger.info(
                "Registered image set '%s' (%d images, %s, %dx%d)",
                trunk,
                image_set.image_count,
                canonical_ext,
                width,
                height,
            )
            return image_set
        except ImageUploadError:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise
        except Exception:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise

    # ------------------------------------------------------------------ #
    # Extraction and validation.
    # ------------------------------------------------------------------ #

    def _safe_extract(
        self,
        archive_path: str,
        dest_dir: str,
        max_uncompressed_bytes: int,
    ) -> None:
        """
        Extract ``archive_path`` into ``dest_dir`` after sanitizing every
        member.

        Performs three checks before writing any byte to disk:

        - Path safety: every member must resolve inside ``dest_dir``.
        - Flat layout: members may not contain any path separator.
        - Uncompressed-size cap: the sum of declared member sizes must
          not exceed ``max_uncompressed_bytes``.
        """
        lower = archive_path.lower()
        try:
            if lower.endswith(".zip"):
                self._safe_extract_zip(archive_path, dest_dir, max_uncompressed_bytes)
            else:
                self._safe_extract_tar(archive_path, dest_dir, max_uncompressed_bytes)
        except (zipfile.BadZipFile, tarfile.TarError) as exc:
            raise ImageUploadError(
                "archive_corrupted",
                f"Archive could not be opened or read: {exc}",
            ) from exc

    @staticmethod
    def _check_member_layout(name: str, dest_dir: str) -> None:
        """
        Reject archive members that escape ``dest_dir`` (zip-slip) or
        live inside a subdirectory (we mandate a flat layout).
        """
        if "/" in name or "\\" in name:
            raise ImageUploadError(
                "archive_contains_subdirectories",
                (
                    "Archive must contain only files at the top level. "
                    f"Found nested entry '{name}'."
                ),
                found=name,
            )
        if not _is_within_directory(dest_dir, os.path.join(dest_dir, name)):
            raise ImageUploadError(
                "unsafe_archive_path",
                f"Archive contains an unsafe path: '{name}'.",
                found=name,
            )

    @classmethod
    def _safe_extract_zip(
        cls,
        archive_path: str,
        dest_dir: str,
        max_uncompressed_bytes: int,
    ) -> None:
        """
        Validate and extract a ``.zip`` archive.
        """
        with zipfile.ZipFile(archive_path) as zf:
            members = zf.infolist()
            total = 0
            for member in members:
                if member.is_dir():
                    # An explicit directory entry violates the flat-only
                    # rule even if no file lives in it.
                    cls._check_member_layout(member.filename, dest_dir)
                    continue
                cls._check_member_layout(member.filename, dest_dir)
                total += int(member.file_size)
                if total > max_uncompressed_bytes:
                    raise ImageUploadError(
                        "archive_uncompressed_too_large",
                        (
                            "Archive uncompressed size exceeds the allowed "
                            f"maximum of {max_uncompressed_bytes} bytes."
                        ),
                        found=total,
                        allowed=[max_uncompressed_bytes],
                    )

            for member in members:
                if member.is_dir():
                    continue
                zf.extract(member, dest_dir)

    @classmethod
    def _safe_extract_tar(
        cls,
        archive_path: str,
        dest_dir: str,
        max_uncompressed_bytes: int,
    ) -> None:
        """
        Validate and extract a ``.tar`` / ``.tar.gz`` / ``.tgz`` archive.
        """
        with tarfile.open(archive_path) as tf:
            members = tf.getmembers()
            total = 0
            for member in members:
                if member.isdir():
                    cls._check_member_layout(member.name, dest_dir)
                    continue
                if not member.isfile():
                    # Reject symlinks, devices, fifos - anything that
                    # isn't a regular file has no business in an image
                    # archive.
                    raise ImageUploadError(
                        "unsafe_archive_path",
                        f"Archive contains a non-regular entry: '{member.name}'.",
                        found=member.name,
                    )
                cls._check_member_layout(member.name, dest_dir)
                total += int(member.size)
                if total > max_uncompressed_bytes:
                    raise ImageUploadError(
                        "archive_uncompressed_too_large",
                        (
                            "Archive uncompressed size exceeds the allowed "
                            f"maximum of {max_uncompressed_bytes} bytes."
                        ),
                        found=total,
                        allowed=[max_uncompressed_bytes],
                    )

            # ``filter="data"`` is the Python 3.12+ default-safe filter
            # that strips ownership and dangerous attributes.
            tf.extractall(dest_dir, members=members, filter="data")

    @staticmethod
    def _validate_extracted_contents(staging_dir: str) -> list[str]:
        """
        Return the sorted list of image filenames in ``staging_dir``.

        Raises an ``ImageUploadError`` if no images are found or if any
        file uses an extension outside the allow-list.
        """
        all_entries = sorted(os.listdir(staging_dir))
        image_files: list[str] = []
        for entry in all_entries:
            full = os.path.join(staging_dir, entry)
            if not os.path.isfile(full):
                # Subdirectories are already rejected during extraction;
                # this guard catches anything else (sockets, broken
                # symlinks).
                continue
            ext = entry.rsplit(".", 1)[-1].lower() if "." in entry else ""
            if ext not in IMAGE_EXTENSIONS:
                raise ImageUploadError(
                    "archive_disallowed_image_extension",
                    (
                        f"Archive contains a file with an unsupported extension: "
                        f"'{entry}'. Allowed image extensions: "
                        f"{', '.join(IMAGE_EXTENSIONS)}."
                    ),
                    found=ext,
                    allowed=list(IMAGE_EXTENSIONS),
                )
            image_files.append(entry)

        if not image_files:
            raise ImageUploadError(
                "archive_contains_no_images",
                "Archive does not contain any supported image files.",
                allowed=list(IMAGE_EXTENSIONS),
            )
        return image_files

    @staticmethod
    def _enforce_single_extension(image_files: list[str]) -> str:
        """
        Verify that every image in the archive belongs to the same
        extension family (``jpg`` and ``jpeg`` count as one) and return
        the canonical family member.
        """
        families: set[str] = set()
        for filename in image_files:
            ext = filename.rsplit(".", 1)[-1].lower()
            canonical = _canonical_extension(ext)
            if canonical is None:
                # Should not happen - already filtered upstream.
                raise ImageUploadError(
                    "archive_disallowed_image_extension",
                    f"Unsupported image extension '.{ext}'.",
                    found=ext,
                    allowed=list(IMAGE_EXTENSIONS),
                )
            families.add(canonical)

        if len(families) > 1:
            raise ImageUploadError(
                "archive_mixed_image_extensions",
                (
                    "Archive must contain images of exactly one type. "
                    f"Found multiple: {sorted(families)}."
                ),
                found=sorted(families),
            )
        return next(iter(families))

    @staticmethod
    def _enforce_single_resolution(
        staging_dir: str, image_files: list[str]
    ) -> tuple[int, int]:
        """
        Open every image with OpenCV and verify they all share the same
        resolution. Return the common ``(width, height)``. Any file that
        cannot be decoded is treated as a corrupted archive.
        """
        common: tuple[int, int] | None = None
        for filename in image_files:
            full = os.path.join(staging_dir, filename)
            try:
                img = cv2.imread(full, cv2.IMREAD_UNCHANGED)
            except Exception as exc:  # pragma: no cover - defensive
                raise ImageUploadError(
                    "archive_corrupted",
                    f"Image '{filename}' could not be decoded: {exc}.",
                    found=filename,
                ) from exc
            if img is None:
                raise ImageUploadError(
                    "archive_corrupted",
                    f"Image '{filename}' could not be decoded.",
                    found=filename,
                )
            height, width = img.shape[:2]
            dims = (int(width), int(height))
            if common is None:
                common = dims
            elif common != dims:
                raise ImageUploadError(
                    "archive_mixed_image_resolutions",
                    (
                        "Archive must contain images that all share the same "
                        f"resolution. Found {dims} after {common}."
                    ),
                    found=[list(common), list(dims)],
                )
        # ``common`` is non-None because ``image_files`` is non-empty.
        assert common is not None
        return common

    @staticmethod
    def _rename_images(
        staging_dir: str,
        image_files: list[str],
        trunk: str,
        canonical_ext: str,
    ) -> list[str]:
        """
        Rename every image inside ``staging_dir`` to
        ``<trunk>_<NNNN>.<canonical_ext>`` using a width derived from
        the number of images (``len(str(N))``). Returns the new
        filenames in numeric order.

        The rename happens via a ``.tmp`` intermediate to avoid clashes
        when an original name already matches the target pattern.
        """
        count = len(image_files)
        width = max(1, len(str(count)))
        tmp_names: list[str] = []

        # First pass: move everything to a temporary name so source and
        # target can never collide during the second pass.
        for index, original in enumerate(sorted(image_files), start=1):
            tmp_name = f".rename-{index:0{width}d}.tmp"
            os.replace(
                os.path.join(staging_dir, original),
                os.path.join(staging_dir, tmp_name),
            )
            tmp_names.append(tmp_name)

        # Second pass: move the ``.tmp`` files to their final canonical
        # names, lower-casing the extension regardless of the original.
        final_names: list[str] = []
        for index, tmp_name in enumerate(tmp_names, start=1):
            final = f"{trunk}_{index:0{width}d}.{canonical_ext}"
            os.replace(
                os.path.join(staging_dir, tmp_name),
                os.path.join(staging_dir, final),
            )
            final_names.append(final)
        return final_names

    @staticmethod
    def _write_set_json(staging_dir: str, image_set: ImageSet) -> None:
        """
        Persist the canonical ``set.json`` sidecar inside ``staging_dir``.
        Written before the staging dir is moved into its final location
        so the commit is atomic from the consumer's point of view.
        """
        path = os.path.join(staging_dir, "set.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(image_set.to_dict(), fh, indent=2)
        try:
            os.chmod(path, 0o644)
        except OSError as exc:
            logger.warning("Could not chmod '%s': %s", path, exc)

    def _commit_staging(self, staging_dir: str, trunk: str) -> None:
        """
        Atomically move the staging directory into its final location
        ``UPLOADED_IMAGES_DIR/<trunk>``.

        The lock + ``os.makedirs(..., exist_ok=False)`` reservation
        turns the conflict check into a single critical section so two
        concurrent uploads cannot both win.
        """
        target_dir = os.path.join(UPLOADED_IMAGES_DIR, trunk)
        with self._upload_lock:
            try:
                # Reserve the target name atomically. ``exist_ok=False``
                # raises if the directory already exists, which is the
                # signal that another concurrent upload won the race.
                os.makedirs(target_dir, exist_ok=False)
            except FileExistsError as exc:
                raise ImageUploadError(
                    "image_set_already_exists",
                    f"An image set named '{trunk}' already exists.",
                    found=trunk,
                ) from exc

            # Replace the empty placeholder with the staging directory.
            # ``os.rename`` succeeds over an empty target directory on
            # POSIX, which is what we just guaranteed.
            try:
                os.rmdir(target_dir)
                os.rename(staging_dir, target_dir)
            except OSError as exc:
                # Clean up our placeholder so a retry can succeed.
                try:
                    if os.path.isdir(target_dir):
                        os.rmdir(target_dir)
                except OSError:
                    pass
                raise RuntimeError(
                    f"Failed to commit image set '{trunk}': {exc}"
                ) from exc

            try:
                os.chmod(target_dir, 0o755)
            except OSError as exc:
                logger.warning("Could not chmod '%s': %s", target_dir, exc)

    # ------------------------------------------------------------------ #
    # Misc helpers.
    # ------------------------------------------------------------------ #

    @staticmethod
    def _is_safe_set_name(name: str) -> bool:
        """
        Return True when ``name`` is a single safe path component.
        """
        if not name or name in (".", ".."):
            return False
        if "/" in name or "\\" in name:
            return False
        if os.sep in name or (os.altsep and os.altsep in name):
            return False
        return True

    @staticmethod
    def _load_set_json(set_dir: str) -> ImageSet | None:
        """
        Load and parse the ``set.json`` sidecar from ``set_dir``. Returns
        ``None`` on any error so a corrupted sidecar does not crash the
        listing endpoint.
        """
        path = os.path.join(set_dir, "set.json")
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to read '%s': %s", path, exc)
            return None
        if not isinstance(data, dict):
            logger.warning("set.json at '%s' is not an object", path)
            return None
        return ImageSet.from_dict(data)
