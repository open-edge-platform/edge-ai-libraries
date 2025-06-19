```{eval-rst}
:orphan:
```
# GenICam GigE or USB3 Cameras

For more information or configuration details for the GenICam GigE or the USB3 camera support, refer to the [GenICam GigE/USB3.0 Camera Support](./generic_plugin_doc.md).

## Installation 
Follow the steps for camera setup and debug tools.

### Balluff Camera
Use Impact Acquire tool to view Balluff cameras, allied vision and other Genicam cameras such as GigE, usb basler. 

Install Impact Acquire tool:

#### install packages

```sh
sudo apt update
sudo apt install gcc-12
sudo apt-get install -y libwxbase3.0-0v5 \
                      libwxbase3.0-dev \
                      libwxgtk3.0-gtk3-0v5 \
                      libwxgtk3.0-gtk3-dev \
                      libwxgtk-webview3.0-gtk3-0v5 \
                      libwxgtk-webview3.0-gtk3-dev \
                      wx3.0-headers \
                      libgtk2.0-dev 
# download ImpactAcquire-x86_64-linux-3.1.0.sh: https://static.matrix-vision.com/mvIMPACT_Acquire/3.1.0/
cd ~/Downloads
chmod a+x ImpactAcquire-x86_64-linux-3.1.0.sh 
./ImpactAcquire-x86_64-linux-3.1.0.sh
```

#### to open Impact Acquire:
```sh
cd /opt/ImpactAcquire/apps/ImpactControlCenter/x86_64
./ImpactControlCenter 
```
#### GUI will display
click on Action -> Use Device --> choose mvBlueFOX3

### GigE/USB Basler Camera
Download and extract pylon package (minimum pylon-8.0.2) [here](https://www.baslerweb.com/en/downloads/software/1378313866/). Run setup_usb.sh.

```sh
  mkdir ./pylon_setup
  tar -C ./pylon_setup -xzf ./pylon-*_setup.tar.gz
  cd ./pylon_setup
  sudo tar -C /opt/pylon -xzf ./pylon-*.tar.gz
  sudo chmod 755 /opt/pylon
  sudo apt-get install libxcb-xinerama0
  sudo apt-get install libxkbcommon-x11-0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-xinerama0 libxcb-xfixes0 libegl1-mesa
  export QT_DEBUG_PLUGINS=1
  sudo apt install libxcb-cursor-dev
```

```sh
  stat /dev/bus/usb
  sudo usermod -a -G dialout $USER
  cd /opt/pylon/share/pylon 
  ./setup-usb.sh
  sudo reboot
  ```


## Prerequisites for Working with the GenICam Compliant GigE Cameras

> - Add `<HOST_IP>` to the `no_proxy` environment variable in the Multimodal Data Visualization Streaming visualizer's `docker-compose.yml` file.
> - Add `network_mode: host` in the `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/docker-compose.yml` file and comment/remove `networks` and `ports` sections. Refer the below snip for making the changes
> - Set `ETCD_HOST` to `<HOST_IP>`

```yaml
dlstreamer-pipeline-server:
  # Add network mode host
  network_mode: host
  ...
  environment:
  ...
    # Please make sure only environment variables are added under environment section in docker compose file.
    # Add HOST_IP to no_proxy and ETCD_HOST
    no_proxy: "<eii_no_proxy>,${RTSP_CAMERA_IP},<HOST_IP>"
    ETCD_HOST: ${ETCD_HOST}
  ...
  # Comment networks and ports section as there will be a conflict when network mode host is used.
  # networks:
    # - eii
  # ports:
    # - '65114:65114'
```

> - Refer the following configuration for configuring the `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/default/config.json` file for GenICam GigE/USB3.0 cameras.

  ```sh
  "pipeline": "gencamsrc serial=<DEVICE_SERIAL_NUMBER> pixel-format=<PIXEL_FORMAT> name=source ! videoconvert ! video/x-raw,format=BGR ! appsink name=destination"
  ```
> - For other cameras such as RSTP, and USB (v4l2 driver compliant) revert the changes that are mentioned in this section.

> - Refer [docs/basler_doc.md](./basler_doc.md) for more information/configuration on Basler camera.

  > **Note:**
  >
  > - Generic Plugin can work only with GenICam compliant cameras and only with gstreamer ingestor.
  > - The above gstreamer pipeline was tested with Basler and IDS GigE cameras.
  > - If `serial` is not provided, then the first connected camera in the device list will be used.
  > - If `pixel-format` is not provided then the default `mono8` pixel format will be used.
  > - If `width` and `height` properties are not set then gencamsrc plugin will set the maximum resolution supported by the camera.
  > - Camera field of view getting cropped is an expected behavior when a lower resolution is set using `height` or `width` parameter. Setting these parameters would create an Image ROI which will originate from the top left corner of the sensor. Refer https://docs.baslerweb.com/image-roi  for more details.
  > - Using a higher resolution might have other side effects like “lag issue in the pipeline” when the model is compute intensive.
  > - By default, `exposure-auto` property is set to on. If the camera is not placed under sufficient light then with auto exposure, `exposure-time` can be set to very large value which will increase the time taken to grab frame. This can lead to `No frame received error`. Hence it is recommended to manually set exposure as in the following sample pipeline when the camera is not placed under good lighting conditions.
  > - `throughput-limit` is the bandwidth limit for streaming out data from the camera(in bytes per second). Setting this property to a higher value might result in better FPS but make sure that the system and the application can handle the data load otherwise it might lead to memory bloat.
  > Refer the below example pipeline to use the above mentioned properties:
     ```javascript
     "pipeline": "gencamsrc serial=<DEVICE_SERIAL_NUMBER> pixel-format=ycbcr422_8 width=1920 height=1080 exposure-time=5000 exposure-mode=timed exposure-auto=off throughput-limit=300000000 name=source ! videoconvert ! video/x-raw,format=BGR ! appsink name=destination"
     ```
  > - By default, USB-FS on Linux system allows only 16MB buffer limit which might not be sufficient to work with high framerate, high resolution cameras and multiple camera setup. In such scenarios configure USB-FS to increase the buffer memory limit for USB3 vision camera. While using the basler USB3.0 camera, ensure that the USBFS limit is set to 1000MB. You can verify this value by using command `cat /sys/module/usbcore/parameters/usbfs_memory_mb`. If it is less than 256MB, then follow these [steps to increase the USBFS value](https://assets.balluff.com/documents/DRF_957345_AA_000/Troubleshooting_section_Checklist_USB3_Settings.html#Troubleshooting_Checklist_USB3_IncreasingTheKernelMemory).
  > - If the GenICam cameras do not get initialized during the runtime, then on the host system, run the `docker system prune` command. After that, remove the GenICam specific semaphore files from the `/dev/shm/` path of the host system. The `docker system prune` command will remove all the stopped containers, networks that are not used (by at least one container), any dangling images, and build cache which could prevent the plugin from accessing the device.


> **Known Limitation:**
>
> - If one observes `Feature not writable` message while working with the GenICam cameras, then reset the device using the camera software or using the reset property of the Generic Plugin. For more information, refer the [README](src-gst-gencamsrc/README.md).

```{toctree}
:maxdepth: 5
:hidden:
basler_doc.md
generic_plugin_doc.md
```
