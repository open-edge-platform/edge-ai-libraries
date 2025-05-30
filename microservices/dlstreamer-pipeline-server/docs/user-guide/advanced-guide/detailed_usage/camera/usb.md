```{eval-rst}
:orphan:
```
# USB v4l2 Cameras

For information or configurations details on the USB cameras, refer to [docs/usb_doc.md](./docs/usb_doc.md).

- Refer the following pipeline for USB v4l2 camera and modify the appropriate config.json file in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs` directory.

```javascript
"pipeline": "v4l2src device=/dev/<DEVICE_VIDEO_NODE> name=source ! video/x-raw,format=YUY2 ! videoconvert ! video/x-raw,format=BGR ! appsink name=destination"
```

>**Note**:

- In case you want to enable resizing with USB camera use the
  `videoscale` element and specify the `height` and `width`  parameter in the pipeline.

    **Example pipeline to enable resizing with USB camera:**

    ```javascript
    "pipeline": "v4l2src device=/dev/<DEVICE_VIDEO_NODE> name=source ! videoscale ! video/x-raw,format=YUY2,height=600,width=600 ! videoconvert ! video/x-raw,format=BGR ! appsink name=destination"
    ```

- In case, multiple USB cameras are connected specify the
  camera using the `device` property in the configuration file.

    **Example pipeline to use the device property:**

    ```javascript
    "pipeline": "v4l2src device=/dev/video0 name=source ! video/x-raw,format=YUY2 ! videoconvert ! video/x-raw,format=BGR ! appsink name=destination"
    ```

    **Note**: Typically a device node gets created when a USB device is connected to the system. When multiple USB cameras are connected then one needs to identify which device node is mapped to the camera and use that with the `device` property. Device nodes for the cameras usually gets created in sequence of video0, video1, video2 etc.
