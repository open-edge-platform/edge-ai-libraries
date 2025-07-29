
# Build and Use Video Generator

ViPPET includes a video generator that creates composite videos from images stored in subdirectories.

This guide is ideal for developers who want to work directly with the source code.


**Build and Start the Tool**:
```bash
mkdir videos
chmod o+w videos
docker compose build videogenerator
docker compose run --rm videogenerator
```

**Make Changes**

1. **Change Input Images**:

   To use your own images instead of the default sample images, follow these steps:

   - Navigate to the `images` folder and create subfolders for your new image categories, placing the relevant images inside.

   - Open the `config.json` file located at `video_generator/config.json`.

   - Update the `object_counts` to reference your new image folders. Replace the existing categories (e.g., `cars` or `faces`) with the names of the new categories you added in the `images` folder:
      ```json
      {
         "background_file": "/usr/src/app/background.gif",
         "base_image_dir": "/usr/src/app/images",
         "output_file": "output_file",
         "target_resolution": [1920, 1080],
         "frame_count": 300,
         "frame_rate": 30,
         "swap_percentage" : 20,
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
      
2. **Configure Parameters**:

   The program uses a config.json file to customize the video generation process. Below is an example configuration:

      ```json
      {
         "background_file": "/usr/src/app/background.gif",
         "base_image_dir": "/usr/src/app/images",
         "output_file": "output_file",
         "target_resolution": [1920, 1080],
         "frame_count": 300,
         "frame_rate": 30,
         "swap_percentage" : 20,
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
      The parameters in the config.json file can be updated as follows:

      - **`background_file`**: Path to a background image (GIF, PNG, etc.) to be used in composite frames.

      - **`base_image_dir`**: Path to the root directory containing categorized image subdirectories.

      - **`output_file`**: Path to the final generated video file. Preference is not to give the file extension and no `.` in
      filename (e.g., output_file).

      - **`target_resolution`**: Resolution of the output video in `[width, height]` format.

      - **`duration`**: Total duration of the generated video (in seconds).

      - **`frame_count`**: Total number of frames in the generated video.

      - **`swap_percentage`**: Percentage of images that should be swapped between frames.

      - **`object_counts`**: Dictionary specifying the number of images per category in each frame.

      - **`object_rotation_rate`**: Rate at which objects rotate per frame (e.g., `0.25` means a quarter rotation per frame).

      - **`object_scale_rate`**: Rate at which the size of objects changes per frame (e.g., `0.25` means the object size
      changes by 25% per frame).

      - **`object_scale_range`**: List specifying the minimum and maximum scale factors for the objects (e.g., `[0.25, 1]`
      means the object can scale between 25% and 100% of its original size).

      - **`encoding`**: Video encoding format (e.g., `H264`).

      - **`bitrate`**: Bitrate for video encoding (measured in kbps).

      - **`swap_interval`**: Frequency of image swapping within frames (in seconds).

      - Supported Encodings and Video Formats

         | **Encoding**  | **Video Format** |
         |---------------|------------------|
         | **H264**      | .mp4             |
         | **HEVC**      | .mp4             |
         | **VP8**       | .webm            |
         | **VP9**       | .webm            |
         | **AV1**       | .mkv             |
         | **MPEG4**     | .avi             |
         | **ProRes**    | .mov             |
         | **Theora**    | .ogg             |

## Validation

1. **Verify Build Success**:
   - Check the logs. Look for confirmation messages indicating the microservice started successfully.

- Expected result: An MP4 file is created under the `videos` folder.



