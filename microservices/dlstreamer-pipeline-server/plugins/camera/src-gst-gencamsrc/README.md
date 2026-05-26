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

### Linux

Build and install the plugin using CMake:

```bash
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j$(nproc)
sudo cmake --install build
sudo ldconfig
```

This will:

1. Configure the build using the bundled GenICam SDK in `plugins/genicam-core/genicam/`
2. Compile the plugin
3. Install `libgstgencamsrc.so` to `/usr/local/lib/gstreamer-1.0` and the GenICam `.so` files to `/usr/local/lib`
4. Update the shared-library cache so the runtime linker finds the GenICam libraries

Verify the installation:

```bash
gst-inspect-1.0 gencamsrc
```

If it returns information about the plugin it is installed successfully and can be used like any other GStreamer source.

### Windows

#### Prerequisites

1. **Visual Studio Build Tools** — install from [visualstudio.microsoft.com](https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio-2026). Select individual components: *MSVC x64/x86 build tools (latest)* and *Windows SDK*.
2. **CMake** — [cmake.org/download](https://cmake.org/download/)
3. **Git** — [git-scm.com](https://git-scm.com/)
4. **PowerShell** >= 7 — [github.com/PowerShell/PowerShell/releases](https://github.com/PowerShell/PowerShell/releases)
5. **GStreamer MSVC x86_64** — install both the *runtime* and *development* packages from [gstreamer.freedesktop.org](https://gstreamer.freedesktop.org/download/)
6. **DLStreamer runtime environment** — follow the [DLStreamer Windows Install Guide](https://github.com/open-edge-platform/dlstreamer/blob/main/docs/user-guide/get_started/install/install_guide_windows.md): download the DLL archive from [edge-ai-libraries releases](https://github.com/open-edge-platform/edge-ai-libraries/releases), extract to `C:\dlstreamer_dlls\`, then run `setup_dls_env.ps1` as Administrator from that folder. This installs GStreamer and creates the `C:\dlstreamer_dlls\` plugin directory.
7. **Camera vendor GenTL producer** — install the SDK for your camera (e.g. Basler pylon, Balluff Impact Acquire, or HikRobot MVS). The installer registers the GenTL producer path.

The GenICam SDK is **not** a prerequisite — the build script downloads it automatically.

#### Source path length

The GenICam SDK zip contains paths that exceed 260 characters when the source root is deep. **Clone or copy the repository to a short path before building.**

If your clone lives at a long path (common when it is nested inside a larger repo), use this workflow each time you want to build:

```powershell
# 1. Pull latest changes in the original (long-path) clone
cd "C:\path\to\...\src-gst-gencamsrc"
git pull

# 2. Refresh the short-path working copy
Remove-Item -Recurse -Force C:\p\gencamsrc -ErrorAction SilentlyContinue
xcopy /E /I /Q . "C:\p\gencamsrc"

# 3. Clean any leftover extraction temp files from previous runs (default temp dir is C:\tmp;
#    override with -TempDir if needed)
Remove-Item -Recurse -Force C:\tmp\_gc_* -ErrorAction SilentlyContinue

# 4. Build from the short path
cd C:\p\gencamsrc
.\build_gencamsrc.ps1 -FetchGenicamSdk
```

If you clone directly to a short path (e.g. `git clone <url> C:\p\gencamsrc`), steps 1-3 are unnecessary - just `git pull` and run the script.

#### Build

From the source directory, run in PowerShell:

```powershell
.\build_gencamsrc.ps1
```

On first run the script downloads the EMVA GenICam SDK v3.1 (VC120 binaries) automatically and places it under `plugins\genicam-core\genicam_win\`. Subsequent runs reuse the cached folder without re-downloading.

To force a fresh download (e.g. after deleting the folder):

```powershell
.\build_gencamsrc.ps1 -FetchGenicamSdk
```

If you already have the GenICam SDK installed system-wide (via Basler pylon, Balluff Impact Acquire, etc.), the script picks it up automatically from the `GENICAM_ROOT64` / `GENICAM_ROOT` environment variable set by the vendor installer — no extra flags needed.

The GStreamer installation is located automatically via the Windows registry, the `GSTREAMER_1_0_ROOT_MSVC_X86_64` environment variable (set by the official installer), or the default path `C:\Program Files\gstreamer\1.0\msvc_x86_64`.

The built DLL will be at `build\bin\Release\gstgencamsrc.dll`.

#### Install

Copy the plugin DLL to the DLStreamer plugin directory (`C:\dlstreamer_dlls\` is created by the DLStreamer `setup_dls_env.ps1` setup script):

```powershell
Copy-Item "build\bin\Release\gstgencamsrc.dll" "C:\dlstreamer_dlls\gstgencamsrc.dll" -Force
```

Verify the installation (see [Windows Runtime Setup](#windows-runtime-setup) first for required environment variables):

```powershell
gst-inspect-1.0 gencamsrc
```

### Windows Runtime Setup

Before running `gst-inspect-1.0` or `gst-launch-1.0` on Windows, set the following environment variables in PowerShell. Adjust paths to match your actual installation.

```powershell
# GenICam runtime DLLs (downloaded by build script into the source tree)
$genicamRuntime = "C:\p\gencamsrc\plugins\genicam-core\genicam_win\Runtime\bin\Win64_x64"

# GStreamer MSVC x86_64 installation
$gstRoot = "C:\Program Files\gstreamer\1.0\msvc_x86_64"

# DLStreamer plugin directory (created by DLStreamer setup_dls_env.ps1)
$dls = "C:\dlstreamer_dlls"

$env:PATH = "$genicamRuntime;$gstRoot\bin;$dls;" + $env:PATH
$env:GST_PLUGIN_PATH = $dls

# Set to the GenTL producer path for your camera vendor, for example:
#   Basler pylon:           C:\Program Files\Basler\pylon\Runtime\x64
#   Balluff Impact Acquire: C:\Program Files\Balluff\ImpactAcquire\bin\x64
#   HikRobot MVS:           C:\Program Files (x86)\Common Files\MVS\Runtime\Win64_x64
$env:GENICAM_GENTL64_PATH = "<path-to-vendor-gentl-producer>"

# Always clear the GStreamer plugin registry cache before inspect/launch.
# A stale cache causes "No such element" errors even when the DLL is valid.
Remove-Item "C:\Temp\gst-registry-clean.bin" -ErrorAction SilentlyContinue
$env:GST_REGISTRY_1_0 = "C:\Temp\gst-registry-clean.bin"
```

Then verify the plugin is found:

```powershell
gst-inspect-1.0 gencamsrc
```

## Clean

To remove the build directory:

```bash
rm -rf build
```

## Usage

Example pipelines. Replace `<camera-serial>` with your camera's serial number (run `gst-inspect-1.0 gencamsrc` to find available devices, or omit `serial` if only one camera is connected).

```bash
gst-launch-1.0 gencamsrc serial=<camera-serial> ! videoconvert ! ximagesink
gst-launch-1.0 gencamsrc serial=<camera-serial> pixel-format=bayerbggr ! bayer2rgb ! ximagesink
```

## Troubleshooting

### GenICam runtime binaries error

If the pipeline returns an error like:

```
module_open failed: libGenApi_gcc42_v3_1.so: cannot open shared object file: No such file or directory
```

The GenICam runtime libraries are missing from the linker cache. This plugin bundles the required GenICam runtime — `cmake --install build` copies them to `/usr/local/lib/`. Make sure you ran `sudo ldconfig` after install to update the cache:

```bash
sudo ldconfig
```

If the error persists, verify the libraries are present:

```bash
ls /usr/local/lib/libGenApi*.so
```

### GenTL producer error

If the pipeline returns error similar below, then GenTL producer is not found.

```
No transport layers found in path
```

In that case, set GENICAM_GENTL64_PATH environment variable to the GenTL producer installation path. Please install the compatible GenTL producer for the camera if not already done.

Install the GenTL producer for your camera vendor:

- **Basler** — download pylon from <https://www.baslerweb.com/en/downloads/software/pylon/>. After installation the GenTL producer is typically at `/opt/pylon/lib/gentlproducer/gtl/`.
- **Balluff** — install Impact Acquire from [balluff.com](https://www.balluff.com)
- **HikRobot** — install MVS from [hikrobotics.com](https://www.hikrobotics.com)

Then set `GENICAM_GENTL64_PATH` to the producer directory, for example:

```bash
export GENICAM_GENTL64_PATH=/opt/pylon/lib/gentlproducer/gtl/
```

Add this to `~/.bashrc` so it persists across terminal sessions.

### Windows: No such element 'gencamsrc'

GStreamer caches plugin scan results in a registry file. A stale cache causes this error even when the DLL is valid. Always delete the registry before testing:

```powershell
Remove-Item "C:\Temp\gst-registry-clean.bin" -ErrorAction SilentlyContinue
$env:GST_REGISTRY_1_0 = "C:\Temp\gst-registry-clean.bin"
gst-inspect-1.0 gencamsrc
```

### Windows: No transport layers found in path

The `GENICAM_GENTL64_PATH` environment variable is not set or does not point to a valid GenTL producer `.cti` file. Set it to the vendor SDK path before launching — see [Windows Runtime Setup](#windows-runtime-setup) above.

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

> The sample pipelines mentioned in this readme were tested using gst-launch-1.0 tool. For working with DLStreamer Pipeline Server service refer [DLStreamer Pipeline Server-README](../../../docs/user-guide/advanced-guide/detailed_usage/camera/genicam.md#genicam-gige-or-usb3-cameras) for the ingestor configurations.
