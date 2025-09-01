# Image Ingestion

The Image ingestion feature is responsible for ingesting the images coming from a directory into DL Streamer Pipeline Server for further processing.
Image ingestion supports the following image formats:

- Jpg
- Jpeg
- Jpe
- Bmp
- Png

Volume mount the image directory present on the host system. To do this, provide the absolute path of the images directory in the `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/docker-compose.yml`.
Refer the following snippet of the `dlstreamer-pipeline-server` service to add the required changes. 

```yaml
dlstreamer-pipeline-server:
  ...
  volume:
    - "/tmp:/tmp"
    # volume mount the udev database with read-only permission,so the USB3 Vision interfaces can be enumerated correctly in the container
    - "/run/udev:/run/udev:ro"
    # Volume mount the directory in host system where the images are stored onto the container directory system.
    # e.g. -"home/directory_1/images_directory:/home/pipeline-server/img_dir"
    - "<relative or absolute path to images directory>:/home/pipeline-server/img_dir"
    ...
```

Refer the following snippet for enabling the image ingestion feature for Jpg images and and modify the appropriate config.json file in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs` directory.

  ```javascript
    "pipeline": "multifilesrc location=\"/home/pipeline-server/img_dir/<image_filename>%02d.jpg\" index=1 name=source ! decodebin ! videoconvert ! gvadetect name=detection ! queue ! gvametaconvert add-empty-results=true name=metaconvert ! gvametapublish name=destination ! appsink name=appsink",

  ```

  For example: If the images are named in the format `frame_01`, `frame_02` and so on, then use the following pipeline.

  ```javascript
  "pipeline": "multifilesrc location=\"/home/pipeline-server/img_dir/frame_%02d.jpg\" index=1 name=source ! decodebin ! videoconvert ! gvadetect name=detection ! queue ! gvametaconvert add-empty-results=true name=metaconvert ! gvametapublish name=destination ! appsink name=appsink",

  ```

>**Note:**
>
> - The images should follow a naming convention and should be named in the format characters followed by digits in the sequential order. For e.g. `frame_001`, `frame_002`, `frame_003` and so on.
> - Make use of the `%d` format specifier to specify the total digits present in the image filename.
>  For e.g. If the images are named in the format `frame_0001`, `frame_0002`, then it has total 4 digits in the filename. Use `%04d` while providing the image name `<image_filename>%04d.jpg` in the pipeline.
> - The ingestion will stop if it does not find the required image name.
> For e.g. If directory contains images `frame_01`, `frame_02` and `frame_04`, then the ingestion will stop after reading `frame_02` since `frame_03` is not present in the directory.
> - Make use of images having resolution - `720×480`, `1280×720`, `1920×1080`, `3840×2160` and `1920×1200`. If a different resolution image is used then the DL Streamer Pipeline Server service might fail with `reshape` error  as gstreamer does zero padding to that image.
> - Make sure that the images directory is having the required read and execute permission. If not use the following command to add the permissions.
> `sudo chmod -R 755 <path to images directory>`

- For PNG Images

  Refer to the following pipeline while using png images.

  ```javascript
  "pipeline": "multifilesrc location=\"/home/pipeline-server/img_dir/<image_filename>%03d.png\" index=1 name=source ! decodebin ! videoconvert ! gvadetect name=detection ! queue ! gvametaconvert add-empty-results=true name=metaconvert ! gvametapublish name=destination ! appsink name=appsink",

  ```

> **Note:** It is recommended to set the `loop` property of the `multifilesrc` element to false `loop=FALSE` to avoid memory leak issues.

- For BMP Images

Refer to the following snippet for enabling the image ingestion feature for bmp image and modify the appropriate config.json file in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs` directory.

```javascript
    "pipeline": "multifilesrc location=\"/home/pipeline-server/img_dir/<image_filename>%03d.bmp\" start-index=1 framerate=1/1 ! decodebin ! videoconvert ! gvadetect name=detection ! queue ! gvametaconvert add-empty-results=true name=metaconvert ! gvametapublish name=destination ! appsink name=appsink",

```

**Path Specification for images:**

Considering folder name as 'images' where the images are stored.

**Relative Path**: `"./images:/home/pipeline-server/img_dir"`  (or) `"${PWD}/images:/home/pipeline-server/img_dir"`

**Absolute Path**: `"/home/ubuntu/images:/home/pipeline-server/img_dir"`
