import json
import logging
import math
import os
import random
import shutil
import subprocess
import tempfile

from PIL import Image, ImageOps

from composite_generator import create_composite_frames

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def get_temp_folder():
    """Create and return a temporary directory path with debug logging."""
    temp_dir = tempfile.mkdtemp(prefix="poc_videogen_")
    logging.debug(f"Temporary directory created at: {temp_dir}")
    return temp_dir


def recreate_temp_folder(temp_dir):
    """Recreate the temporary folder (used if we manually handle it)."""
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)
    logging.info(f"Temporary folder '{temp_dir}' recreated.")


def cleanup_temp_folder(temp_dir):
    """Remove temporary directory with debug logging."""
    shutil.rmtree(temp_dir)
    logging.debug(f"Temporary directory '{temp_dir}' removed.")


def load_config(config_file):
    """Load configuration from a JSON file."""
    try:
        with open(config_file, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        logging.warning(
            f"Warning: Configuration file '{config_file}' not found. Using an empty configuration."
        )
        return {}
    except json.JSONDecodeError as e:
        logging.warning(
            f"Warning: Error parsing JSON configuration: {e}. Using an empty configuration."
        )
        return {}


def fetch_images_per_category(base_dir, config):
    """Fetch images for each category based on the configuration, reusing images only if necessary."""
    images_per_category = {}

    for category, count in config.get("object_counts", {}).items():
        category_path = os.path.join(base_dir, category)

        if os.path.exists(category_path) and os.path.isdir(category_path):
            available_images = [
                os.path.join(category_path, f)
                for f in os.listdir(category_path)
                if f.lower().endswith((".png", ".jpg", ".jpeg"))
            ]

            if not available_images:
                logging.warning(
                    f"Warning: No images found in category '{category}'. Skipping category."
                )
                continue

            # If enough unique images exist, use them
            if len(available_images) >= count:
                selected_images = random.sample(available_images, count)
            else:
                logging.warning(
                    f"Category '{category}' only has {len(available_images)} images, but {count} were requested. Reusing images as needed."
                )

                # Start with all available images
                selected_images = available_images.copy()
                remaining_needed = count - len(selected_images)

                # If more images are required, randomly duplicate existing ones
                selected_images += random.choices(available_images, k=remaining_needed)

            images_per_category[category] = selected_images

        else:
            logging.warning(
                f"Warning: Category folder '{category_path}' does not exist."
            )

    if not images_per_category:
        raise ValueError("No valid images found in the specified categories.")

    return images_per_category


def generate_video(temp_dir, output_file, frame_rate, encoding, bitrate=2000):
    """Generate a video from images with multiple encoders (x264, x265, vp8, vp9, av1, mpeg4, prores, mpeg2, theora)."""
    caps = f"image/jpeg,framerate={frame_rate}/1"
    decoding = "jpegdec"

    # Parser and muxer mappings for each encoder (all lowercase keys)
    parser_muxer_map = {
        "h264": ("h264parse", "mp4mux"),
        "hevc": ("h265parse", "mp4mux"),
        "vp8": ("", "webmmux"),
        "vp9": ("", "webmmux"),
        "av1": ("", "matroskamux"),
        "mpeg4": ("", "avimux"),
        "prores": ("", "qtmux"),
        "theora": ("", "oggmux"),
    }

    # Convert the encoding to lowercase for case-insensitive comparison
    encoding_lower = encoding.lower()

    if encoding_lower not in parser_muxer_map:
        raise ValueError(f"Unsupported encoding type: {encoding}")

    parser, muxer = parser_muxer_map[encoding_lower]

    # Encoder settings with dynamic bitrate
    encoder_settings = {
        "h264": ["x264enc", f"bitrate={bitrate}", "speed-preset=fast", "tune=zerolatency"],
        "hevc": ["x265enc", f"bitrate={bitrate}", "speed-preset=fast", "tune=zerolatency", "!", "h265parse"],
        "vp8": ["vp8enc", f"target-bitrate={bitrate}", "deadline=1000000"],
        "vp9": ["vp9enc", f"target-bitrate={bitrate}", "deadline=1000000"],
        "av1": ["av1enc", f"target-bitrate={bitrate}"],
        "mpeg4": ["avenc_mpeg4", f"bitrate={bitrate}"],
        "prores": ["avenc_prores", f"bitrate={bitrate}"],
        "theora": ["theoraenc", f"bitrate={bitrate}"],
    }

    # Automatically append the extension based on encoding if not provided
    if "." not in output_file:
        extension_map = {
            "h264": ".mp4",
            "hevc": ".mp4",
            "vp8": ".webm",
            "vp9": ".webm",
            "av1": ".mkv",
            "mpeg4": ".avi",
            "prores": ".mov",
            "theora": ".ogg",
        }
        output_file += extension_map.get(encoding_lower, ".mp4")

    # Construct the GStreamer pipeline command
    gst_command = [
        "gst-launch-1.0", "-e",
        "multifilesrc", f"location={temp_dir}/frame_%05d.jpeg", "index=0", f"caps={caps}", "!",
        decoding, "!", "videoconvert", "!",
        *encoder_settings[encoding_lower], "!", muxer, "!",
        "filesink", f"location={output_file}"
    ]

    logging.debug(f"Running GStreamer Command:\n{' '.join(gst_command)}")

    try:
        subprocess.run(gst_command, check=True)
        logging.info(f"✅ Video generated with {encoding}: {output_file}")
    except subprocess.CalledProcessError as e:
        logging.error(f"❌ Error generating video with {encoding}: {e}")


def main():
    try:
        config = load_config("config.json")

        base_image_dir = config.get("base_image_dir", "images")
        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, "output_file")

        # output_file = config.get("output_file", "output_file.mp4")
        target_resolution = tuple(config.get("target_resolution", [1920, 1080]))

        frame_rate = config.get("frame_rate", 30)

        temp_dir = get_temp_folder()

        images_per_category = fetch_images_per_category(base_image_dir, config)

        frame_count = config.get("frame_count", 300)  # Default 300 frames
        create_composite_frames(
            images_per_category,
            temp_dir,
            config,
            target_resolution,
            frame_count,
        )

        generate_video(
            temp_dir,
            output_file,
            frame_rate,
            encoding=config["encoding"],
            bitrate=config["bitrate"],
        )
        cleanup_temp_folder(temp_dir)

        logging.info("Process completed successfully!")
    except Exception as e:
        logging.error(f"Error: {e}")


if __name__ == "__main__":
    main()
