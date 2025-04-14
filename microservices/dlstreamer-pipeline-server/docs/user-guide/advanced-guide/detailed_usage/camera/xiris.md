```{eval-rst}
:orphan:
```
# Xiris Cameras

## Prerequisites for Working with Xiris Camera

The following are the prerequisites for working with Xiris cameras.

> **Note:**
>
> - For other cameras such as RSTP, and USB (v4l2 driver compliant) revert the changes that are mentioned in this section. Refer to the following snip of the `dlstreamer-pipeline-server` service, to add the required changes in the `[WORKDIR]/IEdgeInsights/DLStreamerPipelineServer/docker/docker-compose-eis.yml` file. After making the changes, before you build and run the services, ensure to run the `[WORKDIR]/IEdgeInsights/build/builder.py`.

- For Xiris Camera:

Update the `ETCD_HOST` key with the current system's IP in the `[WORKDIR]/IEdgeInsights/build/.env` file.

```sh
ETCD_HOST=<HOST_IP>
```

Add `network_mode: host` in the `[WORKDIR]/IEdgeInsights/DLStreamerPipelineServer/docker/docker-compose-eis.yml` file and comment/remove `networks` and `ports` sections.
Make the following changes in the `[WORKDIR]/IEdgeInsights/DLStreamerPipelineServer/docker/docker-compose-eis.yml` file.

```yaml
dlstreamer-pipeline-server:
  # Add network mode host
  network_mode: host
  # Please make sure that the above commands are not added under the environment section and also take care about the indentations in the compose file.
  ...
  environment:
  ...
    # Add HOST_IP to no_proxy and ETCD_HOST
    no_proxy: "<eii_no_proxy>,${RTSP_CAMERA_IP},<HOST_IP>"
    ETCD_HOST: ${ETCD_HOST}
  ...
  # Comment networks section will throw an error when network mode host is used.
  # networks:
    # - eii
  # Comment ports section as following
  # ports:
  #   - '65114:65114'
```

**Note:** There is a sample configuration file `[WORKDIR]/IEdgeInsights/DLStreamerPipelineServer/configs/eii/sample_xiris/config.json` that has all the Xiris camera related configuration that are talked about in the below bullet points. These settings must be done in `[WORKDIR]/IEdgeInsights/DLStreamerPipelineServer/configs/eii/default/config.json` for achieving the desired behavior.

- The ip_address parameter must be set to IP address of the camera.
- The shutter_mode parameter configures the camera in either rolling or global shutter mode. Can take one of two values: `Rolling` or `Global`.
- The frame_rate parameter must be set to the desired ingestion frame rate from the camera.
- The pixel_depth parameter must be set to the required pixel depth (in bits). It controls the data output of the camera. It can take one of the following four values: 8, 12, 14 or 16. Note that the pixel_depth parameter has no bearing on the monochrome camera XVC-1000 that has been tested.
- The flip_mode parameter must be set accordingly. It describes how an image is flipped. It can take one of the following four values: "None", "FlipVertical", "FlipHorizontal" or "FlipBoth".
  - None: No flip performed.
  - FlipVertical: Flip the image vertically.
  - FlipHorizontal: Flip the image horizontally.
  - FlipBoth: Flip both horizontally and vertically. Equivalent to 180 degree rotation.
- The set_sharpen parameter sets a value which controls if a sharpening filter is applied to the image or not. This parameter can take either "true" or "false" values.
- The focus parameter sets a value indicating the commanded position of the focus adjustment.
- The tone_map_curve_type parameter sets the shape of the tonemapping curve. Tone mapping is the process of building a displayable image from an HDR image. The type of curve specified controls the distribution of the contrast in the displayable image, and in some cases can be used to adjust the color balance of the image. The different values this parameter can take are:
  - linear: means that the contrast is mapped evenly.
  - gamma: accentuates the contrast in the darker areas using a y = pow(x, gamma) type of relationship.
  - scurve (unsupported at the moment): uses a curve in the general form of y = 1 / (1 + pow((alpha * x) / (1 - x), -beta).
- The tone_map_curve_value parameter sets a value to the above mentioned curve type.
  - For linear curve, set this parameter value to 1
  - For gamma curve, it can take values in the range [-5, 5]. This is to reflect the WeldStudio's gamma slider range. Note: WeldStudio is the camera GUI software from Xiris
  - For scurve: unsupported at the moment
- The exposure_time parameter sets the exposure time in micro-seconds. The XVC cameras can adjust exposure in increments of 0.0125 micro-seconds. In theory exposure can be adjusted from 0.0125 to 53 seconds, but operation below 1 micro-second is not recommended. This parameter is only configurable when shutter_mode parameter is set to `Global`
- The auto_exposure_mode parameter sets the Auto Exposure Mode value. This parameter is only configurable when shutter_mode parameter is set to `Global`. It can take one of the 3 values:
  - Off: Automatic gain is off.
  - Once: Gain is calculated once, then the mode is automatically switched back to Off.
  - Continuous: Gain is calculated continuously.
- The pilot_light_on parameter sets the master control for integrated lighting, can be turned on or off. Can take one of two values: `true` or `false`.
- The pilot_light_power parameter sets the power of the illumination.

Refer to the following code snippet:

  ```javascript
     "config": {
         "xiris": {
            "ip_address": "<set-xiris-camera-IP-here>",
            "shutter_mode": "Global",
            "frame_rate": 10,
            "pixel_depth": 8,
            "flip_mode": "FlipHorizontal",
            "set_sharpen": "false",
            "focus": 0,
            "tone_map_curve_type": "gamma",
            "tone_map_curve_value": "0"
            "tone_map_curve_value": "0",
            "exposure_time": 16331.27,
            "auto_exposure_mode": "Off",
            "pilot_light_on": "true",
            "pilot_light_power": 255
         }
     }
  ```

- The source parameter in the `[WORKDIR]/IEdgeInsights/DLStreamerPipelineServer/configs/eii/default/config.json` file must be set to `ingestor`. Refer to the following code snippet:

  ```javascript
     "config": {
         "source": "ingestor"
     }
  ```

- The pipeline is set to `appsrc` as source and `rawvideoparse` element should be updated with the `height`, `width` and `format` of the Xiris frame. Refer to the following code snippet:

  ```javascript
      {
          "pipeline": "appsrc name=source ! rawvideoparse height=1024 width=1280 format=gray8 ! videoconvert ! video/x-raw,format=BGR ! appsink name=destination"
      }
  ```

**Note:**

- Xiris Camera model tested is XVC-1000(monochrome)
- Only PixelDepth=8 (camera outputs 8 bits per pixel) is supported. In case of any frame rendering issues please check PixelDepth value from the logs and make sure it is set to 8.
- In case a wrong or an invalid IP is provided for connecting to Xiris camera using `XirisCameraIP` env variable, ingestion will not work and there will be no error logs printed. Make sure correct IP is provided for ingestion to work.
- To find the IP address of the camera please use the GUI tool provided by the Xiris (currently available on windows) or run the LinuxSample app under weldsdk installation directory on the host system to find the available cameras.
