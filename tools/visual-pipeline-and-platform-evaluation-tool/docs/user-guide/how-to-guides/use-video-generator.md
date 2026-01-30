# Use Video Generator

The Visual Pipeline and Platform Evaluation Tool includes a video generator that creates composite videos from images
stored in subdirectories. This guide is intended for developers working directly with the source code.

> **Important:**
> Intel provides six images for demo purposes only. You must provide your own
> images to run the video generator or to create videos.

**Build and start the tool**:

```bash
make run-videogenerator
```

## Make Changes

1. **Change input images**:

   Custom images can be used instead of the default sample images as follows:

   - Navigate to the `images` folder and create subfolders for new image categories, then place the relevant
     images inside those subfolders.

   - Open the `config.json` file located at `video_generator/config.json`.

   - Update the `object_counts` section to reference the new image folders. Existing categories (for example, `cars`
     or `persons`) should be replaced with the names of the new categories defined in the `images` folder:

     ```json
     {
        "background_file": "/usr/src/app/background.gif",
        "base_image_dir": "/usr/src/app/images",
        "output_file": "output_file",
        "target_resolution": [1920, 1080],
        "frame_count": 300,
        "frame_rate": 30,
        "swap_percentage": 20,
        "object_counts": {
           "cars": 3,
           "persons": 3
        },
        "object_rotation_rate": 0.25,
        "object_scale_rate": 0.25,
        "object_scale_range": [0.25, 1],
        "encoding": "H264",
        "bitrate": 20000,
        "swap_rate": 1
     }
     ```

2. **Configure parameters**:

   The program uses a `config.json` file to customize the video generation process. Below is an example configuration:

   ```json
   {
      "background_file": "/usr/src/app/background.gif",
      "base_image_dir": "/usr/src/app/images",
      "output_file": "output_file",
      "target_resolution": [1920, 1080],
      "frame_count": 300,
      "frame_rate": 30,
      "swap_percentage": 20,
      "object_counts": {
         "cars": 3,
         "persons": 3
      },
      "object_rotation_rate": 0.25,
      "object_scale_rate": 0.25,
      "object_scale_range": [0.25, 1],
      "encoding": "H264",
      "bitrate": 20000,
      "swap_rate": 1
   }
   ```

   Parameters in the `config.json` file can be configured as follows:

   - **`background_file`**: Path to a background image (GIF, PNG, and so on) used in composite frames.

   - **`base_image_dir`**: Path to the root directory containing categorized image subdirectories.

   - **`output_file`**: Base name for the generated video file. It is recommended not to provide a file extension and
     not to include `.` in the filename (for example, `output_file`).

   - **`target_resolution`**: Resolution of the output video in `[width, height]` format.

   - **`duration`**: Total duration of the generated video in seconds.

   - **`frame_count`**: Total number of frames in the generated video.

   - **`swap_percentage`**: Percentage of images that are swapped between frames.

   - **`object_counts`**: Dictionary specifying the number of images per category in each frame.

   - **`object_rotation_rate`**: Rate at which objects rotate per frame
     (for example, `0.25` means a quarter rotation per frame).

   - **`object_scale_rate`**: Rate at which the size of objects changes per frame (for example, `0.25` means the
     object size changes by 25% per frame).

   - **`object_scale_range`**: List specifying the minimum and maximum scale factors for the objects (for example,
     `[0.25, 1]` means objects can scale between 25% and 100% of their original size).

   - **`encoding`**: Video encoding format (for example, `H264`).

   - **`bitrate`**: Bitrate for video encoding, measured in kbps.

   - **`swap_interval`**: Frequency of image swapping within frames, in seconds.

   - **Supported encodings and video formats**:

      | **Encoding** | **Video Format** |
      |--------------|------------------|
      | **H264**     | .mp4             |
      | **HEVC**     | .mp4             |
      | **VP8**      | .webm            |
      | **VP9**      | .webm            |
      | **AV1**      | .mkv             |
      | **MPEG4**    | .avi             |
      | **ProRes**   | .mov             |
      | **Theora**   | .ogg             |

## Validation

1. **Verify build success**:
   - Logs should be checked for confirmation messages indicating that the microservice started successfully:

        ```bash
        docker compose logs videogenerator -f
        ```

- Expected result: An MP4 file is created under the `shared/videos/video-generator` folder.
