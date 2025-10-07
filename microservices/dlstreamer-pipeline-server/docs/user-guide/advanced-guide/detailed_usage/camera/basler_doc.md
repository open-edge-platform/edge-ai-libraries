<!--hide_directive```{eval-rst}
:orphan:
```hide_directive-->

# Basler Camera

**NOTE**:

- `Pixel Formats`

| Camera Model | Tested Pixel Formats |
| ------------ | -------------------- |
| Basler acA1920-40gc | mono8<br>ycbcr422_8<br>bayerrggb |
| Basler acA1920-150uc | mono8<br>rgb8<br>bgr8<br>bayerbggr |

- In case one wants to use any of the bayer pixel-format then `bayer2rgb` element needs to be used to covert raw bayer data to RGB. Refer the below example pipeline.

    ```javascript
       "pipeline": "gencamsrc serial=<DEVICE_SERIAL_NUMBER> pixel-format=bayerrggb name=source ! bayer2rgb ! videoconvert ! video/x-raw,format=BGR ! appsink name=destination"
    ```

- In case one wants to use `mono8` image format or wants to work with monochrome camera then change the `pixel-format` to `mono8` in the pipeline. Since `gstreamer` ingestor expects a `BGR` image format, a single channel `GRAY8` format would be converted to 3 channel BGR format.

    **Example pipeline to use `mono8` imageformat or work with monochrome basler camera:**

    ```javascript
       "pipeline": "gencamsrc serial=<DEVICE_SERIAL_NUMBER> pixel-format=mono8 name=source ! videoconvert ! video/x-raw,format=BGR ! appsink name=destination"
    ```

- In case one wants to enable resizing with basler camera `vaapipostproc` element can be used to specify the height and width parameter in the gstreamer pipeline.

    **Example pipeline to enable resizing  the frame to `600x600` with basler camera:**

    ```javascript
       "pipeline": "gencamsrc serial=<DEVICE_SERIAL_NUMBER> pixel-format=<PIXEL_FORMAT> name=source ! vaapipostproc height=600 width=600 ! videoconvert ! video/x-raw,format=BGR ! appsink name=destination"
    ```

- In case one wants to divert the color space conversion to `GPU` for basler camera `vaapipostproc` can be used. This can be useful when the CPU% is maxing out due to the input ingestion stream.

    **Example pipeline to perform color space conversion from `YUY2 to BGRx` in GPU with `vaapipostproc` with basler camera:**

    ```javascript
      "pipeline": "gencamsrc serial=<DEVICE_SERIAL_NUMBER> pixel-format=<PIXEL_FORMAT> name=source ! vaapipostproc format=bgrx ! videoconvert ! video/x-raw,format=BGR ! appsink name=destination"
    ```

  `Basler camera hardware triggering`

- If the camera is configured for triggered image acquisition, one can trigger image captures at particular points in time.

- With respect to hardware triggering if the camera supports it then an electrical signal can be applied to one of the camera's input lines which can act as a trigger signal.

- In order to configure the camera for hardware triggering, during our tests we set the following properties of Generic Plugin.

  - `trigger-selector=FrameStart` - the camera initializes the acquisition of only image
  - `acquisition-mode=singleframe` - the camera will acquire exactly one image
  - `trigger-source=Line1` - the appropriate H/W trigger source needs to be selected
  - `trigger-activation=RisingEdge` - the appropriate trigger activation parameter need to be selected
  - `hw-trigger-timeout=100` - the H/W trigger timeout value in seconds in multiples of 5

    For more information on the properties related to hardware triggering refer [Generic-Plugin-readme](../src-gst-gencamsrc/README)

  `Validated test setup for basler camera hardware triggering`

- In our test setup a python script was used to control a ModBus I/O module to generate a digital output to Opto-insulated input line(Line1) of the basler camera.

- For testing the hardware trigger functionality Basler `acA1920-40gc` camera model had been used.

  >**Note**: Other triggering capabilities with different camera models are not tested.
