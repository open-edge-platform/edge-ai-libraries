# Video Ingestion

Video ingestion supports reading video files from a directory.

- Volume mount the videos directory present on the host system. To do this, provide the absolute path of the directory in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/docker-compose.yml` as shown below.


  ```yaml
  dlstreamer-pipeline-server:
    ...
    volume:
      - "/tmp:/tmp"
      # volume mount the udev database with read-only permission,so the USB3 Vision interfaces can be enumerated correctly in the container
      - "/run/udev:/run/udev:ro"
      # Volume mount the directory in host system where the videos are stored onto the container directory system.
      # Eg: -"home/videos_dir:/home/pipeline-server/videos_dir"
      - "<relative or absolute path to videos directory>:/home/pipeline-server/videos_dir"
      ...
  ```

- Modify pipeline in appropriate config.json file in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs` directory.
  -  For reading videos, for example, `video_000.avi`, `video_001.avi`, `video_002.avi`, from a directory use the following pipeline.

    ```json
      "pipeline": "multifilesrc location=/home/pipeline-server/videos_dir/video_%03d.avi name=source ! h264parse ! decodebin ! videoconvert ! gvadetect name=detection ! queue ! gvawatermark ! appsink name=destination"
    ```

  -  For reading videos, for example, video01.mp4, video02.mp4, from a directory use the following pipeline.

    ```json
      "pipeline": "multifilesrc start-index=1 location=/home/pipeline-server/videos_dir/video%02d.mp4 name=source ! decodebin ! videoconvert ! gvadetect name=detection ! queue ! gvawatermark ! appsink name=destination"
    ```

  Refer this [doc](./multifilesrc_doc.md) for more details on naming convention for the video files and multifilesrc configuration.
