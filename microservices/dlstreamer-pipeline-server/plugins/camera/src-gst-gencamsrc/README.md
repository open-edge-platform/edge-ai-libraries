# Generic Camera Plugin

1. [Overview](#overview)

2. [Versioning](#versioning)

2. [Build](#build)

3. [Clean](#clean)

4. [Usage](#usage)

5. [Troubleshooting](#troubleshooting)

## Overview

This is the Gstreamer source plugin for camera devices compliant to GenICam. The design is scalable to other machine vision standards. The plugin uses interface technology driver - Gig E Vision driver or USB 3 Vision driver - by the camera device vendor wrapped under GenICam standard as GenTL producer. The plugin has a library that acts as a GenTL consumer. GenTL consumer interprets the GenICam compliant camera capabilities via camera description file in XML format and configures as desired via GenAPI.

## Versioning

The source code is versioned with the format of 3 numbers separated by points. The first number is major version, which in this case is 1. The second number is minor version, which increments for every release like engineering releases, alpha or PV etc., The third number is the revision number, which increments when a feature gets merged from a feature branch. It resets when the minor version number increments for a release.
First engineering release version is v1.0.0
Second engineering release version is v1.1.0
Alpha release version is v1.2.0
PV release version is v1.3.0

## Build and Install

Following is the command to build the plugin.

```
./setup.sh
```

This script does the following

1. Downloads the GenICam runtime binaries (verision 3.1) from EMVA website
2. Unzips the binary and except Linux64 for x86_64 tar ball, deletes all other files
3. Untars Linux64 for x86_64 tar ball and copies to standard library path in Ubuntu, i.e., /usr/lib/x86_64-linux-gnu/
4. Runs configure command to configure the project generating Makefile
5. Calls make to build
6. Installs the generated gencamsrc shared library to /usr/local/lib/gstreamer-1.0
7. Sets the environment variable GST_PLUGIN_PATH to /usr/local/lib/gstreamer-1.0

If plugin is installed successsfully, should be able to inspect it.

```
gst-inspect-1.0 gencamsrc
```

If it returns information about the plugin, then it's installed successfully
and can be used like any other gstreamer source.

## Clean

To remove the program binaries and object files from the source code directory

```
make clean
```

To also remove the files project Makefile that 'configure' created

```
make distclean
```

## Usage

A few example pipelines with this plugin below. The serial number of the Basler camera in PMCE BA lab is 22034422.

```
gst-launch-1.0 gencamsrc serial=22034422 ! videoconvert ! ximagesink
gst-launch-1.0 gencamsrc serial=22034422 pixel-format=bayerbggr ! bayer2rgb ! ximagesink
```

## Troubleshooting

### GenICam runtime binaries error

If the pipeline returns error similar below, then GenICam runtime dependency is not resolved.

```
module_open failed: libGenApi_gcc42_v3_1.so: cannot open shared object file: No such file or directory
```

In that case, download and copy the GenICam runtime binaries to standard path. The copied files are stored in the system after reboot.

1. Download this file - <https://www.emva.org/wp-content/uploads/GenICam_V3_1_0_public_data.zip>
2. Unzip to get runtime binaries and SDK files for multiple platforms
3. Untar GenICam_Runtime_gcc42_Linux32_i86_v3_1_0.tgz file
4. Under bin/Linux64_x64 directory, there will be shared libraries, copy all of them to usr/lib/x86_64-linux-gnu path

### GenTL producer error

If the pipeline returns error similar below, then GenTL producer is not found.

```
No transport layers found in path
```

In that case, set GENICAM_GENTL64_PATH environment variable to the GenTL producer installation path. Please install the compatible GenTL producer for the camera if not already done.

For Basler camera, the GenTL producer can be downloaded from <https://www.baslerweb.com/en/sales-support/downloads/software-downloads/pylon-5-0-12-linux-x86-64-bit-debian/>

Upon installation of this software, GenTL will be present in “/opt/pylon5/lib64/gentlproducer/gtl”, accordingly set the environment variable.

```
export GENICAM_GENTL64_PATH=/opt/pylon5/lib64/gentlproducer/gtl/
```

This variable may be set variable in .bashrc file so that it is one-time and need not be set every time when the terminal is opened.

### Generic Plugin Element Properties

The following are the list of properties supported by the `gencamsrc` gstreamer element.

1. acquisition-mode    : Sets the acquisition mode of the device. It defines mainly the number of frames to capture during an acquisition and the way the acquisition stops. Possible values (continuous/multiframe/singleframe)
2. balance-ratio       : Controls ratio of the selected color component to a reference color component
3. balance-ratio-selector: Selects which Balance ratio to control. Possible values(All,Red,Green,Blue,Y,U,V,Tap1,Tap2...)
4. balance-white-auto  : Controls the mode for automatic white balancing between the color channels. The white balancing ratios are automatically adjusted. Possible values(Off,Once,Continuous)
5. binning-horizontal  : Number of horizontal photo-sensitive cells to combine together. This reduces the horizontal resolution (width) of the image. A value of 1 indicates that no horizontal binning is performed by the camera.
6. binning-horizontal-mode: Sets the mode to use to combine horizontal photo-sensitive cells together when BinningHorizontal is used. Possible values (sum/average)
7. binning-selector    : Selects which binning engine is controlled by the BinningHorizontal and BinningVertical features. Possible values (sensor/region0/region1/region2)
8. binning-vertical    : Number of vertical photo-sensitive cells to combine together. This reduces the vertical resolution (height) of the image. A value of 1 indicates that no vertical binning is performed by the camera.
9. binning-vertical-mode: Sets the mode to use to combine vertical photo-sensitive cells together when BinningHorizontal is used. Possible values (sum/average)
10. black-level         : Controls the analog black level as an absolute physical value.
11. black-level-auto    : Controls the mode for automatic black level adjustment. The exact algorithm used to implement this adjustment is device-specific. Possible values(Off/Once/Continuous)
12. black-level-selector: Selects which Black Level is controlled by the various Black Level features. Possible values(All,Red,Green,Blue,Y,U,V,Tap1,Tap2...)
13. blocksize           : Size in bytes to read per buffer (-1 = default)
14. decimation-horizontal: Horizontal sub-sampling of the image.
15. decimation-vertical : Number of vertical photo-sensitive cells to combine together.
16. device-clock-selector: Selects the clock frequency to access from the device. Possible values (Sensor/SensorDigitization/CameraLink/Device-specific)
17. do-timestamp        : Apply current stream time to buffers
18. exposure-auto       : Sets the automatic exposure mode when ExposureMode is Timed. Possible values(off/once/continuous)
19. exposure-mode       : Sets the operation mode of the Exposure. Possible values (off/timed/trigger-width/trigger-controlled)
20. exposure-time       : Sets the Exposure time (in us) when ExposureMode is Timed and ExposureAuto is Off. This controls the duration where the photosensitive cells are exposed to light.
21.  exposure-time-selector: Selects which exposure time is controlled by the ExposureTime feature. This allows for independent control over the exposure components. Possible values(common/red/green/stage1/...)
22. frame-rate          : Controls the acquisition rate (in Hertz) at which the frames are captured.
23. gain                : Controls the selected gain as an absolute value. This is an amplification factor applied to video signal. Values are device specific.
24. gain-auto           : Sets the automatic gain control (AGC) mode. Possible values (off/once/continuous)
25. gain-auto-balance   : Sets the mode for automatic gain balancing between the sensor color channels or taps. Possible values (off/once/continuous)
26. gain-selector       : Selects which gain is controlled by the various Gain features. It's device specific. Possible values (All/Red/Green/Blue/Y/U/V...)
27. gamma               : Controls the gamma correction of pixel intensity.
28. gamma-selector      : Select the gamma correction mode. Possible values (sRGB/User)
29. height              : Height of the image provided by the device (in pixels).
30. hw-trigger-timeout  : Wait timeout (in multiples of 5 secs) to receive frames before terminating the application.
31. name                : The name of the object
32. num-buffers         : Number of buffers to output before sending EOS (-1 = unlimited)
33. offset-x            : Horizontal offset from the origin to the region of interest (in pixels).
34. offset-y            : Vertical offset from the origin to the region of interest (in pixels).
35. packet-delay        : Controls the delay (in GEV timestamp counter unit) to insert between each packet for this stream channel. This can be used as a crude flow-control mechanism if the application or the network infrastructure cannot keep up with the packets coming from the device.
36. packet-size         : Specifies the stream packet size, in bytes, to send on the selected channel for a Transmitter or specifies the maximum packet size supported by a receiver.
37.  parent              : The parent of the object
                        Object of type "GstObject"
38. pixel-format        : Format of the pixels provided by the device. It represents all the information provided by PixelSize, PixelColorFilter combined in a single feature. Possible values (mono8/ycbcr411_8/ycbcr422_8/rgb8/bgr8/bayerbggr/bayerrggb/bayergrbg/bayergbrg)
39. reset               : Resets the device to its power up state. After reset, the device must be rediscovered. Do not use unless absolutely required.
40. serial              : Device's serial number. This string is a unique identifier of the device.
41. throughput-limit    : Limits the maximum bandwidth (in Bps) of the data that will be streamed out by the device on the selected Link. If necessary, delays will be uniformly inserted between transport layer packets in order to control the peak bandwidth.
42. trigger-activation  : Specifies the activation mode of the trigger. Possible values (RisingEdge/FallingEdge/AnyEdge/LevelHigh/LevelLow)
43. trigger-delay       : Specifies the delay in microseconds (us) to apply after the trigger reception before activating it.
44. trigger-divider     : Specifies a division factor for the incoming trigger pulses
45. trigger-multiplier  : Specifies a multiplication factor for the incoming trigger pulses.
46. trigger-overlap     : Specifies the type trigger overlap permitted with the previous frame or line. Possible values (Off/ReadOut/PreviousFrame/PreviousLine)
47. trigger-selector    : Selects the type of trigger to configure. Possible values (AcquisitionStart/AcquisitionEnd/AcquisitionActive/FrameStart/FrameEnd/FrameActive/FrameBurstStart/FrameBurstEnd/FrameBurstActive/LineStart/ExposureStart/ExposureEnd/ExposureActive/MultiSlopeExposureLimit1)
48. trigger-source      : Specifies the internal signal or physical input Line to use as the trigger source. Possible values (Software/SoftwareSignal<n>/Line<n>/UserOutput<n>/Counter<n>Start/Counter<n>End/Timer<n>Start/Timer<n>End/Encoder<n>/<LogicBlock<n>>/Action<n>/LinkTrigger<n>/CC<n>/...)
49. typefind            : Run typefind before negotiating (deprecated, non-functional)
50. width               : Width of the image provided by the device (in pixels).
51. use-default-properties: If `true`, resets the gencamsrc properties that are not provided in the gstreamer pipeline, to the default values decided by gencamsrc

**Notes:**

* `serial` property is not mandatory to use if only a single camera is connected to the system. In case multiple cameras are connected to the system and the `serial` property is not used then the plugin will connect to the camera which is connected first in the device index list.

* If `width` and `height` properties are not specified then the plugin will set to the maximum resolution supported by the camera.

* `hw-trigger-timeout` is the time for which the plugin waits for the H/W trigger. The reason this time-out value is in multiple of 5 sec is because the maximum grab timeout for each frame is 5 secs. Hence even if `hw-trigger-timeout=1` is set, the plugin will wait for 5 secs.

* In case frame capture is failing when multiple basler cameras are used, use the `packet-delay` property to increase the delay between the transmission of each packet for the selected stream channel. Depending on the number of cameras appropriate delay can be set. Increasing the `packet-delay` will decrease the frame rate.

* The default values for `exposure-auto` and `exposure-mode` properties are `once` and `timed` respectively. To set the Exposure Time using `exposure-time` property, the values for `exposure-auto` and `exposure-mode` must be set to `off` and `timed` respectively. Refer the below example pipeline to set Exposure time (in us).

  $ gst-launch-1.0 gencamsrc exposure-time=1000 exposure-mode=timed exposure-auto=off ! videoconvert ! ximagesink

* If `pixel-format` is set to any of the Bayer formats(bayerbggr/bayerrggb/bayergrbg/bayergbrg) then `bayer2rgb` gstreamer plugin must be used to convert raw Bayer to RGB. Refer below example for usage of `bayer2rgb` plugin.

  $ gst-launch-1.0 gencamsrc pixel-format=bayerrggb ! bayer2rgb ! videoconvert ! ximagesink

  Typically bayerbggr/bayerrggb/bayergrbg/bayergbrg pixel-formats are used with cameras that support BayerBG8/BayerRG8/BayerGR8/BayerGB8 respectively.

* The maximum grab delay is set to 5 seconds after which the plugin would timeout and throw "No frame received from the camera" exception. This error be caused by performance problems of the network hardware used, i.e. network adapter, switch, or ethernet cable. Make sure the camera is and the system are connected to the same gigabit switch or try increasing the camera's interpacket delay using `packet-delay` property.

> The sample pipelines mentioned in this readme were tested using gst-launch-1.0 tool. For working with DLStreamer Pipeline Server service refer [DLStreamer Pipeline Server-README](../README.md#genicam-gige-or-usb3-cameras) for the ingestor configurations.
