import logging
import math
import os
import random

from PIL import Image, ImageSequence

# Configure logging (INFO for important steps, DEBUG for in-depth tracking)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def create_composite_frames(
    images_per_category,
    temp_dir,
    config,
    target_resolution,
    frame_count,
):
    """Create animated frames with an animated zooming background and grid-based movement."""
    frame_width, frame_height = target_resolution
    num_objects = sum(config.get("object_counts", {}).values())
    swap_percentage = config.get("swap_percentage", 25)
    frame_rate = config.get("frame_rate", 30)
    swap_rate = (
        config.get("swap_rate", 1) * frame_rate
    )  # Swaps every `swap_rate` frames

    # Load Background
    background_file = config.get("background_file", None)
    background_frames = []
    if background_file:
        with Image.open(background_file) as bg:
            if background_file.lower().endswith(".gif"):
                background_frames = [
                    frame.copy()
                    .convert("RGBA")
                    .resize(target_resolution, Image.Resampling.LANCZOS)
                    for frame in ImageSequence.Iterator(bg)
                ]
            else:
                static_bg = bg.convert("RGBA").resize(
                    target_resolution, Image.Resampling.LANCZOS
                )
                background_frames = [static_bg] * frame_count

    if not background_frames:
        background_frames = [
            Image.new("RGBA", target_resolution, (0, 0, 0, 0))
        ] * frame_count

    # Grid Setup
    grid_cols = math.ceil(math.sqrt(num_objects))
    grid_rows = math.ceil(num_objects / grid_cols)
    cell_width = frame_width // grid_cols
    cell_height = frame_height // grid_rows
    padding = int(min(cell_width, cell_height) * 0.1)

    logging.info(f"Generating frames with a {grid_cols}x{grid_rows} grid...")

    # Initialize Objects
    objects = []
    available_positions = [(r, c) for r in range(grid_rows) for c in range(grid_cols)]
    random.shuffle(available_positions)

    object_rotation_rate = config.get(
        "object_rotation_rate", 0
    )  # Default 0 rotations/sec
    object_scale_rate = config.get("object_scale_rate", 0.25)  # Default cycles/sec
    object_scale_range = config.get("object_scale_range", [0.5, 2])  # [min, max] scale

    for category, count in config.get("object_counts", {}).items():
        images = random.sample(
            images_per_category[category], count
        )  # Unique image selection
        for image_path in images:
            row, col = available_positions.pop()

            obj = {
                "image": image_path,
                "grid_row": row,
                "grid_col": col,
                "x": col * cell_width + padding,
                "y": row * cell_height + padding,
                "dx": random.uniform(-1.5, 1.5),  # Random movement speed
                "dy": random.uniform(-1.5, 1.5),
                "rotation": random.uniform(0, 360),
                "rotation_step": random.uniform(
                    -object_rotation_rate * 360 / frame_rate,
                    object_rotation_rate * 360 / frame_rate,
                ),  # Unique rotation speed & direction
                "scale": random.uniform(
                    object_scale_range[0], object_scale_range[1]
                ),  # Random start scale
                "scale_step": random.uniform(
                    -object_scale_rate / frame_rate, object_scale_rate / frame_rate
                ),  # Randomized scale speed
                "width": 0,
                "height": 0,
            }
            objects.append(obj)

    def swap_positions():
        """Swap a percentage of objects' positions and update their (x, y) coordinates accordingly."""
        num_to_swap = math.ceil((swap_percentage / 100) * len(objects))

        # Ensure unique swap pairs
        swap_indices = random.sample(range(len(objects)), num_to_swap * 2)
        swap_pairs = list(zip(swap_indices[:num_to_swap], swap_indices[num_to_swap:]))

        logging.debug(f"Swapping positions of {num_to_swap} objects...")

        for idx1, idx2 in swap_pairs:
            if idx1 == idx2:
                continue  # Skip if same object is chosen

            logging.debug(
                f"Before Swap: {idx1} -> (row={objects[idx1]['grid_row']}, col={objects[idx1]['grid_col']}, x={objects[idx1]['x']}, y={objects[idx1]['y']}) "
                f"<-> {idx2} -> (row={objects[idx2]['grid_row']}, col={objects[idx2]['grid_col']}, x={objects[idx2]['x']}, y={objects[idx2]['y']})"
            )

            # Swap grid positions
            objects[idx1]["grid_row"], objects[idx2]["grid_row"] = (
                objects[idx2]["grid_row"],
                objects[idx1]["grid_row"],
            )
            objects[idx1]["grid_col"], objects[idx2]["grid_col"] = (
                objects[idx2]["grid_col"],
                objects[idx1]["grid_col"],
            )

            # Update (x, y) coordinates based on new grid position
            objects[idx1]["x"] = objects[idx1]["grid_col"] * cell_width + padding
            objects[idx1]["y"] = objects[idx1]["grid_row"] * cell_height + padding
            objects[idx2]["x"] = objects[idx2]["grid_col"] * cell_width + padding
            objects[idx2]["y"] = objects[idx2]["grid_row"] * cell_height + padding

            logging.debug(
                f"After Swap: {idx1} -> (row={objects[idx1]['grid_row']}, col={objects[idx1]['grid_col']}, x={objects[idx1]['x']}, y={objects[idx1]['y']}) "
                f"<-> {idx2} -> (row={objects[idx2]['grid_row']}, col={objects[idx2]['grid_col']}, x={objects[idx2]['x']}, y={objects[idx2]['y']})"
            )

    for frame_idx in range(frame_count):
        if frame_idx % swap_rate == 0:
            swap_positions()

        # Apply zoom effect with restricted range
        zoom_factor = 1 + 0.05 * math.sin(frame_idx / 20)  # Reduced zoom intensity
        zoom_factor = max(
            0.9, min(zoom_factor, 1.1)
        )  # Restrict zoom between 0.9x to 1.1x

        new_width = max(int(frame_width * zoom_factor), frame_width)
        new_height = max(int(frame_height * zoom_factor), frame_height)

        zoomed_bg = (
            background_frames[frame_idx % len(background_frames)]
            .copy()
            .resize((new_width, new_height), Image.Resampling.LANCZOS)
        )

        # Crop to keep within the original frame boundaries
        left = (new_width - frame_width) // 2
        top = (new_height - frame_height) // 2
        background = zoomed_bg.crop((left, top, left + frame_width, top + frame_height))

        # Process and place each object

        for obj in objects:
            with Image.open(obj["image"]) as img:
                img = img.convert("RGBA")

                # Define original image dimensions
                original_width, original_height = img.size  #  Get the original size

                # Define max allowed size inside the grid cell (with padding)
                max_width = cell_width - 2 * padding  #  Define max width per grid cell
                max_height = (
                    cell_height - 2 * padding
                )  #  Define max height per grid cell

                # Random scaling updates for dynamic variation
                obj["scale"] += obj["scale_step"]
                if (
                    obj["scale"] > object_scale_range[1]
                    or obj["scale"] < object_scale_range[0]
                ):
                    obj[
                        "scale_step"
                    ] *= -1  # Reverse scaling direction when hitting limits

                # Introduce slight movement variation every few frames
                if frame_idx % 10 == 0:  # Adjust every 10 frames
                    obj["dx"] += random.uniform(-0.2, 0.2)
                    obj["dy"] += random.uniform(-0.2, 0.2)
                    obj["rotation_step"] += random.uniform(-0.1, 0.1)

                # Compute the scaling factor correctly
                scaling_factor = (
                    min(max_width / original_width, max_height / original_height)
                    * obj["scale"]
                )

                new_width = int(original_width * scaling_factor)
                new_height = int(original_height * scaling_factor)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

                obj["width"], obj["height"] = new_width, new_height

                # Apply Rotation AFTER Scaling
                img = img.rotate(obj["rotation"], expand=True)
                obj["rotation"] += obj["rotation_step"]

                # Move objects within their grid cell
                obj["x"] += obj["dx"]
                obj["y"] += obj["dy"]

                # Define the grid cell boundaries
                cell_x_min = obj["grid_col"] * cell_width + padding
                cell_x_max = (obj["grid_col"] + 1) * cell_width - obj["width"] - padding
                cell_y_min = obj["grid_row"] * cell_height + padding
                cell_y_max = (
                    (obj["grid_row"] + 1) * cell_height - obj["height"] - padding
                )

                # Ensure object stays within its grid cell
                if obj["x"] < cell_x_min:
                    obj["x"] = cell_x_min
                    obj["dx"] *= -1  # Reverse direction if it hits a boundary
                if obj["x"] > cell_x_max:
                    obj["x"] = cell_x_max
                    obj["dx"] *= -1

                if obj["y"] < cell_y_min:
                    obj["y"] = cell_y_min
                    obj["dy"] *= -1
                if obj["y"] > cell_y_max:
                    obj["y"] = cell_y_max
                    obj["dy"] *= -1

                obj["x"] = max(cell_x_min, min(cell_x_max, obj["x"]))
                obj["y"] = max(cell_y_min, min(cell_y_max, obj["y"]))

                background.paste(img, (int(obj["x"]), int(obj["y"])), mask=img)

        frame_path = os.path.join(temp_dir, f"frame_{frame_idx:05d}.jpeg")
        background = background.convert("RGB")
        background.save(frame_path, format="JPEG")

    logging.info(f"Composite frames saved in '{temp_dir}'.")
