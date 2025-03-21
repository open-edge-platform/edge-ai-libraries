
# Build and Use Video Generator

ViPPET includes a video generator that creates composite videos from images stored in subdirectories.

This guide is ideal for developers who want to work directly with the source code.


**Build and Start the Tool**:
   - Follow the steps in [How to Build from Source](./how-to-build-source.md)
   - Run:
     ```bash
      docker compose exec videogenerator python3 imagetovideo.py
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

2. **Save Changes and Restart**:
   - Save the file and restart the application:
     ```bash
     docker compose restart
     ```

## Validation

1. **Verify Build Success**:
   - Check the logs. Look for confirmation messages indicating the microservice started successfully.

- Expected result: An MP4 file is created under the `videos` folder.



