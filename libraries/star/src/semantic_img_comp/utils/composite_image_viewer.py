# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: utils/composite_image_viewer.py
Version: 1.0
Authors: Omid Semiari
Date: 2026-05-20
Description: Creates 2x1 composite images comparing original and reconstructed images
             using mapping information from log files.

This script:
1. Reads a log JSON file containing frame/image mappings
2. Maps reconstruction images to their corresponding original images
3. Creates 2x1 composite images (original on top, reconstruction on bottom)
4. Saves composites to an output directory
"""

import argparse
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from PIL import Image
import yaml


# ============================================================================
# Logging Setup
# ============================================================================
def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """Configure logging for the script."""
    logger = logging.getLogger(__name__)
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


logger = setup_logging()


# ============================================================================
# Image Mapping and Discovery
# ============================================================================
def parse_log_file(log_path: Path) -> Dict[str, str]:
    """
    Parse a JSON log file to extract reconstruction-to-original filename mapping.

    Args:
        log_path: Path to the log JSON file (NDJSON format)

    Returns:
        Dictionary mapping reconstruction image name (e.g. "12.jpeg")
        to original image name (e.g. "dataset_img_12.jpg")
    """
    recon_to_original: Dict[str, str] = {}

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                stripped = line.strip()
                if not stripped:
                    continue

                try:
                    record = json.loads(stripped)
                except json.JSONDecodeError as e:
                    logger.warning(f"Skipping malformed JSON on line {line_num}: {e}")
                    continue

                # Preferred mapping from user-provided schema:
                # recon image name is "frame_id.jpeg" and original is "file_name".
                frame_id = record.get("frame_id")
                file_name = record.get("file_name")
                if frame_id is not None and file_name:
                    recon_name = f"{frame_id}.jpeg"
                    original_name = Path(str(file_name)).name
                    recon_to_original[recon_name] = original_name
                    logger.debug(f"Mapped recon {recon_name} to original {original_name}")

    except FileNotFoundError:
        logger.error(f"Log file not found: {log_path}")
        raise
    except Exception as e:
        logger.error(f"Error parsing log file: {e}")
        raise

    return recon_to_original


def _resolve_original_from_log_map(
    recon_file: str,
    recon_to_original: Dict[str, str],
    original_images: Dict[str, Path],
) -> Optional[Path]:
    """Resolve original image path for a reconstruction filename using log-derived mapping."""
    candidates = [recon_file]
    stem = Path(recon_file).stem
    if stem.isdigit():
        candidates.extend([f"{stem}.jpeg", f"{stem}.jpg", f"{stem}.png"])

    original_name: Optional[str] = None
    for candidate in candidates:
        mapped = recon_to_original.get(candidate)
        if mapped:
            original_name = mapped
            break

    if original_name is None:
        return None

    for key in (original_name, Path(original_name).stem):
        if key in original_images:
            return original_images[key]

    return None


def discover_images(directory: Path) -> Dict[str, Path]:
    """
    Discover all image files in a directory.

    Args:
        directory: Path to the directory containing images

    Returns:
        Dictionary mapping image filename (stem) to full path
    """
    images = {}
    image_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"}

    try:
        for image_file in directory.rglob("*"):
            if image_file.is_file() and image_file.suffix.lower() in image_extensions:
                # Map both full filename and stem for flexibility
                images[image_file.name] = image_file
                images[image_file.stem] = image_file

    except Exception as e:
        logger.error(f"Error discovering images in {directory}: {e}")
        raise

    return images


def load_catalog_dirs(catalog_path: Path) -> List[Path]:
    """Load and validate dataset directories listed in an input catalog YAML."""
    try:
        with open(catalog_path, "r", encoding="utf-8") as f:
            catalog_raw = yaml.safe_load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Original catalog YAML not found: {catalog_path}")

    if catalog_raw is None:
        raise ValueError(f"Original catalog YAML is empty: {catalog_path}")

    if isinstance(catalog_raw, list):
        entries = catalog_raw
    elif isinstance(catalog_raw, dict):
        entries = catalog_raw.get("input_dirs")
        if entries is None:
            entries = catalog_raw.get("directories")
    else:
        entries = None

    if not isinstance(entries, list) or not entries:
        raise ValueError(
            f"Catalog YAML must provide a non-empty list in either top-level list, "
            f"'input_dirs', or 'directories': {catalog_path}"
        )

    resolved_dirs: List[Path] = []
    base_dir = catalog_path.parent
    for entry in entries:
        if not isinstance(entry, (str, Path)):
            raise ValueError(f"Invalid catalog entry {entry!r}; expected a directory path string.")

        directory = Path(entry)
        if not directory.is_absolute():
            directory = (base_dir / directory).resolve()

        if not directory.exists() or not directory.is_dir():
            raise FileNotFoundError(f"Catalog directory does not exist: {directory}")

        resolved_dirs.append(directory)

    return resolved_dirs


def find_image_pair(
    recon_image_name: str,
    recon_images: Dict[str, Path],
    original_images: Dict[str, Path],
) -> Optional[Tuple[Path, Path]]:
    """
    Find matching original image for a reconstruction image.

    Args:
        recon_image_name: Name of the reconstruction image
        recon_images: Dict mapping names to reconstruction image paths
        original_images: Dict mapping names to original image paths

    Returns:
        Tuple of (original_path, recon_path) or None if not found
    """
    # Try direct lookup first
    if recon_image_name in recon_images:
        recon_path = recon_images[recon_image_name]

        # Try to find corresponding original image
        stem = Path(recon_image_name).stem

        # Try various naming conventions
        candidates = [
            recon_image_name,
            stem,
            recon_image_name.replace("_recon", ""),
            recon_image_name.replace("_reconstruction", ""),
            recon_image_name.replace("_dec", ""),
            recon_image_name.replace("_decoded", ""),
        ]

        for candidate in candidates:
            if candidate in original_images:
                return original_images[candidate], recon_path

    return None


# ============================================================================
# Image Composition
# ============================================================================
def load_image(image_path: Path) -> Optional[Image.Image]:
    """
    Load an image from disk.

    Args:
        image_path: Path to the image file

    Returns:
        PIL Image object or None if loading fails
    """
    try:
        img = Image.open(image_path)
        # Convert to RGB if necessary (handles RGBA, grayscale, etc.)
        if img.mode != "RGB":
            img = img.convert("RGB")
        return img
    except Exception as e:
        logger.warning(f"Failed to load image {image_path}: {e}")
        return None


def resize_to_match(img1: Image.Image, img2: Image.Image) -> Tuple[Image.Image, Image.Image]:
    """
    Resize images to have the same width for compositing.
    Preserves aspect ratio.

    Args:
        img1: First image
        img2: Second image

    Returns:
        Tuple of (resized_img1, resized_img2) with matching widths
    """
    w1, h1 = img1.size
    w2, h2 = img2.size

    # Use the smaller width to avoid upscaling
    target_width = min(w1, w2)

    # Resize both images to target width, preserving aspect ratio
    if w1 != target_width:
        new_height = int(h1 * target_width / w1)
        img1 = img1.resize((target_width, new_height), Image.Resampling.LANCZOS)

    if w2 != target_width:
        new_height = int(h2 * target_width / w2)
        img2 = img2.resize((target_width, new_height), Image.Resampling.LANCZOS)

    return img1, img2


def create_composite_image(
    original_img: Image.Image,
    recon_img: Image.Image,
    add_labels: bool = True,
    label_height: int = 30,
) -> Image.Image:
    """
    Create a 2x1 composite image (original on top, reconstruction on bottom).

    Args:
        original_img: Original image (PIL Image)
        recon_img: Reconstructed image (PIL Image)
        add_labels: Whether to add "Original" and "Reconstruction" labels
        label_height: Height in pixels to reserve for labels

    Returns:
        Composite PIL Image
    """
    # Resize images to match width
    img1, img2 = resize_to_match(original_img, recon_img)
    w = img1.width
    h1 = img1.height
    h2 = img2.height

    # Add label space if requested
    total_height = h1 + h2
    if add_labels:
        total_height += 2 * label_height

    # Create composite image
    composite = Image.new("RGB", (w, total_height), color="white")

    # Paste original image
    y_offset = label_height if add_labels else 0
    composite.paste(img1, (0, y_offset))

    # Paste reconstruction image
    y_offset_recon = h1 + (2 * label_height if add_labels else 0)
    composite.paste(img2, (0, y_offset_recon))

    # Add labels if requested
    if add_labels:
        from PIL import ImageDraw, ImageFont

        draw = ImageDraw.Draw(composite)
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", size=16)
        except OSError:
            font = ImageFont.load_default()

        # Draw "Original" label
        draw.text((10, 5), "Original", fill="black", font=font)

        # Draw "Reconstruction" label
        y_recon_label = h1 + label_height + 5
        draw.text((10, y_recon_label), "Reconstruction", fill="black", font=font)

    return composite


# ============================================================================
# Main Processing
# ============================================================================
def process_images(
    log_path: Path,
    recon_dir: Path,
    original_catalog_path: Path,
    output_dir: Path,
    add_labels: bool = True,
    max_images: Optional[int] = None,
) -> None:
    """
    Process all images and create composite outputs.

    Args:
        log_path: Path to log JSON file
        recon_dir: Directory containing reconstruction images
        original_catalog_path: YAML catalog path listing one or more original image directories
        output_dir: Output directory for composite images
        add_labels: Whether to add "Original" and "Reconstruction" labels
        max_images: Maximum number of images to process (None for all)
    """
    # Validate inputs
    log_path = Path(log_path)
    recon_dir = Path(recon_dir)
    original_catalog_path = Path(original_catalog_path)
    output_dir = Path(output_dir)

    if not log_path.exists():
        raise FileNotFoundError(f"Log file not found: {log_path}")
    if not recon_dir.exists():
        raise FileNotFoundError(f"Reconstruction directory not found: {recon_dir}")
    if not original_catalog_path.exists():
        raise FileNotFoundError(f"Original catalog YAML not found: {original_catalog_path}")
    if not original_catalog_path.is_file() or original_catalog_path.suffix.lower() not in {".yml", ".yaml"}:
        raise ValueError(f"Expected a YAML catalog file for originals: {original_catalog_path}")

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Output directory: {output_dir}")

    # Parse log file to get frame mappings
    logger.info("Parsing log file...")
    frame_to_image = parse_log_file(log_path)
    logger.info(f"Found {len(frame_to_image)} recon-to-original mappings in log file")

    if not frame_to_image:
        logger.warning("No image mappings found in log file")
        return

    # Discover images in both directories
    logger.info("Discovering images...")
    recon_images = discover_images(recon_dir)
    original_dirs = load_catalog_dirs(original_catalog_path)
    original_images: Dict[str, Path] = {}
    original_file_count = 0
    for directory in original_dirs:
        directory_images = discover_images(directory)
        original_images.update(directory_images)
        original_file_count += len(
            [name for name in directory_images.keys() if Path(name).suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"}]
        )

    logger.info(f"Found {len(recon_images)//2:.0f} reconstruction images")  # Divided by 2 because we store both name and stem
    logger.info(f"Found {original_file_count} original images from {len(original_dirs)} catalog directories")

    # Process each reconstruction image
    processed = 0
    successful = 0
    failed = 0

    # Get sorted reconstruction image names
    recon_files = sorted(
        set(f for f in recon_images.keys() if Path(f).suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"})
    )

    for recon_idx, recon_file in enumerate(recon_files, start=1):
        if max_images and processed >= max_images:
            logger.info(f"Reached maximum of {max_images} images")
            break

        # Prefer explicit mapping from logs (recon: frame_id.jpeg -> original: file_name).
        original_from_log = _resolve_original_from_log_map(recon_file, frame_to_image, original_images)
        if recon_file in recon_images and original_from_log is not None:
            pair = (original_from_log, recon_images[recon_file])
        else:
            # Fallback for non-standard/older logs.
            pair = find_image_pair(recon_file, recon_images, original_images)

        if pair is None:
            logger.warning(f"Could not find original image for: {recon_file}")
            failed += 1
            continue

        original_path, recon_path = pair

        # Load images
        original_img = load_image(original_path)
        recon_img = load_image(recon_path)

        if original_img is None or recon_img is None:
            logger.warning(f"Failed to load image pair: {original_path} / {recon_path}")
            failed += 1
            continue

        try:
            # Create composite image
            composite = create_composite_image(original_img, recon_img, add_labels=add_labels)

            # Generate output filename
            stem = Path(recon_file).stem
            output_filename = f"composite_{stem}.png"
            output_path = output_dir / output_filename

            # Save composite
            composite.save(output_path)
            logger.info(f"[{processed+1}/{len(recon_files)}] Saved: {output_path}")

            successful += 1
        except Exception as e:
            logger.error(f"Error creating composite for {recon_file}: {e}")
            failed += 1

        processed += 1

    # Summary
    logger.info("=" * 70)
    logger.info(f"Processing complete!")
    logger.info(f"  Total images processed: {processed}")
    logger.info(f"  Successful: {successful}")
    logger.info(f"  Failed: {failed}")
    logger.info(f"  Output directory: {output_dir}")
    logger.info("=" * 70)


# ============================================================================
# CLI
# ============================================================================
def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Create 2x1 composite images comparing original and reconstructed images.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python composite_image_viewer.py \\
    --log-file /path/to/log.json \\
    --recon-dir /path/to/reconstructed \\
    --original-dir /path/to/input_catalog.yaml \
    --output-dir /path/to/output
    
  # Limit processing to first 10 images
  python composite_image_viewer.py \\
    --log-file /path/to/log.json \\
    --recon-dir /path/to/reconstructed \\
    --original-dir /path/to/input_catalog.yaml \
    --output-dir /path/to/output \\
    --max-images 10
    
  # Without labels
  python composite_image_viewer.py \\
    --log-file /path/to/log.json \\
    --recon-dir /path/to/reconstructed \\
    --original-dir /path/to/input_catalog.yaml \
    --output-dir /path/to/output \\
    --no-labels
        """,
    )

    parser.add_argument(
        "--log-file",
        type=str,
        required=True,
        help="Path to log JSON file containing image mappings",
    )
    parser.add_argument(
        "--recon-dir",
        type=str,
        required=True,
        help="Path to directory containing reconstructed images",
    )
    parser.add_argument(
        "--original-dir",
        type=str,
        required=True,
        help="Path to input catalog YAML listing one or more original image directories",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        required=True,
        help="Path to output directory for composite images",
    )
    parser.add_argument(
        "--max-images",
        type=int,
        default=None,
        help="Maximum number of images to process (None for all)",
    )
    parser.add_argument(
        "--no-labels",
        action="store_true",
        help="Do not add 'Original' and 'Reconstruction' labels to composite images",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level",
    )

    args = parser.parse_args()

    # Reconfigure logging with specified level
    logger.setLevel(getattr(logging, args.log_level.upper()))

    try:
        process_images(
            log_path=args.log_file,
            recon_dir=args.recon_dir,
            original_catalog_path=args.original_dir,
            output_dir=args.output_dir,
            add_labels=not args.no_labels,
            max_images=args.max_images,
        )
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()



