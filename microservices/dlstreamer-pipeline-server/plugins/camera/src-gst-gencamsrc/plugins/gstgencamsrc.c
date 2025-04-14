/*
 * GStreamer Generic Camera Plugin
 * Copyright (c) 2020, Intel Corporation
 * All rights reserved.
 *
 * Authors:
 *   Gowtham Hosamane <gowtham.hosamane@intel.com>
 *   Deval Vekaria <deval.vekaria@intel.com>
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *
 * 1. Redistributions of source code must retain the above copyright notice,
 *    this list of conditions and the following disclaimer.
 *
 * 2. Redistributions in binary form must reproduce the above copyright notice,
 *    this list of conditions and the following disclaimer in the documentation
 *    and/or other materials provided with the distribution.
 *
 * 3. Neither the name of the copyright holder nor the names of its contributors
 *    may be used to endorse or promote products derived from this software
 *    without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
 * AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
 * THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
 * PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
 * CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
 * EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
 * PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS;
 * OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
 * WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
 * OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE,
 * EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */

/**
 * SECTION:element-gstgencamsrc
 *
 * The gencamsrc element streams video from GenICam compliant
 * industrial machine vision camera.
 *
 * <refsect2>
 * <title>Example launch line</title>
 * |[
 * gst-launch-1.0 gencamsrc serial=<deviceSerialNumber> pixel-format=mono8 !
 * videoconvert ! ximagesink
 * gst-launch-1.0 gencamsrc serial=<deviceSerialNumber> ! bayer2rgb !
 * ximagesink
 * ]|
 * This is an example pipeline to stream from GenICam camera pushing to
 * to ximagesink with a color space converter in between
 * </refsect2>
 */

#include "gencambase.h"
#include "gstgencamsrc.h"

#define WIDTH (7680)
#define HEIGHT (4320)
#define TIMETICK_NS (1000000000UL)
#define TIMETICK_MS (1000)
#define FPS_REPORT_TIME TIMETICK_MS

GST_DEBUG_CATEGORY (gst_gencamsrc_debug_category);
#define GST_CAT_DEFAULT gst_gencamsrc_debug_category

/* prototypes */
static void
gst_gencamsrc_set_property (GObject * object, guint property_id,
    const GValue * value, GParamSpec * pspec);
static void
gst_gencamsrc_get_property (GObject * object, guint property_id,
    GValue * value, GParamSpec * pspec);
static void gst_gencamsrc_dispose (GObject * object);
static void gst_gencamsrc_finalize (GObject * object);

static GstCaps *gst_gencamsrc_get_caps (GstBaseSrc * src, GstCaps * filter);
// static gboolean gst_gencamsrc_negotiate (GstBaseSrc * src);
// static GstCaps *gst_gencamsrc_fixate (GstBaseSrc * src, GstCaps * caps);
static gboolean gst_gencamsrc_set_caps (GstBaseSrc * src, GstCaps * caps);
static gboolean gst_gencamsrc_start (GstBaseSrc * src);
static gboolean gst_gencamsrc_stop (GstBaseSrc * src);
static void
gst_gencamsrc_get_times (GstBaseSrc * src, GstBuffer * buffer,
    GstClockTime * start, GstClockTime * end);
// static gboolean gst_gencamsrc_query (GstBaseSrc * src, GstQuery * query);
// static gboolean gst_gencamsrc_event (GstBaseSrc * src, GstEvent * event);
static GstFlowReturn gst_gencamsrc_create (GstPushSrc * src, GstBuffer ** buf);

enum
{
  PROP_0,
  PROP_SERIAL,
  PROP_PIXELFORMAT,
  PROP_WIDTH,
  PROP_HEIGHT,
  PROP_OFFSETX,
  PROP_OFFSETY,
  PROP_DECIMATIONHORIZONTAL,
  PROP_DECIMATIONVERTICAL,
  PROP_BINNINGSELECTOR,
  PROP_BINNINGHORIZONTALMODE,
  PROP_BINNINGVERTICALMODE,
  PROP_BINNINGHORIZONTAL,
  PROP_BINNINGVERTICAL,
  PROP_ACQUISITIONMODE,
  PROP_DEVICECLOCKSELECTOR,
  PROP_TRIGGERDELAY,
  PROP_TRIGGERDIVIDER,
  PROP_TRIGGERMULTIPLIER,
  PROP_TRIGGEROVERLAP,
  PROP_TRIGGERACTIVATION,
  PROP_TRIGGERSELECTOR,
  PROP_TRIGGERSOURCE,
  PROP_HWTRIGGERTIMEOUT,
  PROP_EXPOSUREMODE,
  PROP_EXPOSURETIME,
  PROP_EXPOSUREAUTO,
  PROP_EXPOSURETIMESELECTOR,
  PROP_BLACKLEVELSELECTOR,
  PROP_BLACKLEVELAUTO,
  PROP_BLACKLEVEL,
  PROP_GAMMA,
  PROP_GAMMASELECTOR,
  PROP_GAINSELECTOR,
  PROP_GAIN,
  PROP_GAINAUTO,
  PROP_GAINAUTOBALANCE,
  PROP_BALANCERATIOSELECTOR,
  PROP_BALANCERATIO,
  PROP_BALANCEWHITEAUTO,
  PROP_DEVICELINKTHROUGHPUTLIMIT,
  PROP_CHANNELPACKETSIZE,
  PROP_CHANNELPACKETDELAY,
  PROP_FRAMERATE,
  PROP_RESET,
  PROP_USEDEFAULTPROPERTIES
};

/* pad templates */

#define GCS_FORMATS_SUPPORTED "{ BGR, RGB, I420, YUY2, GRAY8 }"

#define GCS_CAPS                                                               \
  GST_VIDEO_CAPS_MAKE(GCS_FORMATS_SUPPORTED)                                   \
  ","                                                                          \
  "multiview-mode = { mono, left, right }"                                     \
  ";"                                                                          \
  "video/x-bayer, format=(string) { bggr, rggb, grbg, gbrg }, "                \
  "width = " GST_VIDEO_SIZE_RANGE ", "                                         \
  "height = " GST_VIDEO_SIZE_RANGE ", "                                        \
  "framerate = " GST_VIDEO_FPS_RANGE ", "                                      \
  "multiview-mode = { mono, left, right }"

static GstStaticPadTemplate
    gst_gencamsrc_src_template =
GST_STATIC_PAD_TEMPLATE ("src", GST_PAD_SRC, GST_PAD_ALWAYS,
    GST_STATIC_CAPS (GCS_CAPS));

/* class initialization */
#define gst_gencamsrc_parent_class parent_class

G_DEFINE_TYPE_WITH_CODE (GstGencamsrc, gst_gencamsrc, GST_TYPE_PUSH_SRC,
    GST_DEBUG_CATEGORY_INIT (gst_gencamsrc_debug_category, "gencamsrc", 0,
        "debug category for gencamsrc element"));
static void
gst_gencamsrc_class_init (GstGencamsrcClass * klass)
{
  GObjectClass *gobject_class = G_OBJECT_CLASS (klass);
  GstBaseSrcClass *base_src_class = GST_BASE_SRC_CLASS (klass);
  GstPushSrcClass *push_src_class = GST_PUSH_SRC_CLASS (klass);

  /* Setting up pads and setting metadata should be moved to
     base_class_init if you intend to subclass this class. */
  gst_element_class_add_static_pad_template (GST_ELEMENT_CLASS (klass),
      &gst_gencamsrc_src_template);

  gst_element_class_set_static_metadata (GST_ELEMENT_CLASS (klass),
      "Intel Generic Camera Src Plugin", "Source/Video/Camera",
      "Intel Generic Camera Source Plugin",
      "Gowtham Hosamane <gowtham.hosamane@intel.com>");

  gobject_class->set_property = gst_gencamsrc_set_property;
  gobject_class->get_property = gst_gencamsrc_get_property;
  gobject_class->dispose = gst_gencamsrc_dispose;
  gobject_class->finalize = gst_gencamsrc_finalize;

  base_src_class->get_caps = GST_DEBUG_FUNCPTR (gst_gencamsrc_get_caps);
  base_src_class->set_caps = GST_DEBUG_FUNCPTR (gst_gencamsrc_set_caps);
  base_src_class->start = GST_DEBUG_FUNCPTR (gst_gencamsrc_start);
  base_src_class->stop = GST_DEBUG_FUNCPTR (gst_gencamsrc_stop);
  base_src_class->get_times = GST_DEBUG_FUNCPTR (gst_gencamsrc_get_times);

  // Following are virtual overridden by push src
  push_src_class->create = GST_DEBUG_FUNCPTR (gst_gencamsrc_create);

  // The property list
  g_object_class_install_property (gobject_class, PROP_SERIAL,
      g_param_spec_string ("serial", "DeviceSerialNumber",
          "Device's serial number. This string is a unique identifier of the device.",
          "", (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_PIXELFORMAT,
      g_param_spec_string ("pixel-format", "PixelFormat",
          "Format of the pixels provided by the device. It represents all the information provided by PixelSize, PixelColorFilter combined in a single feature. Possible values (mono8/ycbcr411_8/ycbcr422_8/rgb8/bgr8/bayerbggr/bayerrggb/bayergrbg/bayergbrg)",
          "mono8", (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_WIDTH,
      g_param_spec_int ("width", "Width",
          "Width of the image provided by the device (in pixels).", 0 /*Min */ ,
          INT_MAX /*Max */ , WIDTH /*Default */ ,
          (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_HEIGHT,
      g_param_spec_int ("height", "Height",
          "Height of the image provided by the device (in pixels).",
          0 /*Min */ , INT_MAX /*Max */ , HEIGHT /*Default */ ,
          (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_OFFSETX,
      g_param_spec_int ("offset-x", "OffsetX",
          "Horizontal offset from the origin to the region of interest (in pixels).",
          0 /*Min */ , INT_MAX /*Max */ , 0 /*Default */ ,
          (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_OFFSETY,
      g_param_spec_int ("offset-y", "OffsetY",
          "Vertical offset from the origin to the region of interest (in pixels).",
          0 /*Min */ , INT_MAX /*Max */ , 0 /*Default */ ,
          (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_DECIMATIONHORIZONTAL,
      g_param_spec_int ("decimation-horizontal", "DecimationHorizontal",
          "Horizontal sub-sampling of the image.",
          0 /*Min */ , INT_MAX /*Max */ , 0 /*Default */ ,
          (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_DECIMATIONVERTICAL,
      g_param_spec_int ("decimation-vertical", "DecimationVertical",
          "Number of vertical photo-sensitive cells to combine together.",
          0 /*Min */ , INT_MAX /*Max */ , 0 /*Default */ ,
          (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_BINNINGSELECTOR,
      g_param_spec_string ("binning-selector", "BinningSelector",
          "Selects which binning engine is controlled by the BinningHorizontal and BinningVertical features. Possible values (sensor/region0/region1/region2)",
          "", (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_BINNINGHORIZONTALMODE,
      g_param_spec_string ("binning-horizontal-mode", "BinningHorizontalMode",
          "Sets the mode to use to combine horizontal photo-sensitive cells together when BinningHorizontal is used. Possible values (sum/average)",
          "", (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_BINNINGVERTICALMODE,
      g_param_spec_string ("binning-vertical-mode", "BinningVerticalMode",
          "Sets the mode to use to combine vertical photo-sensitive cells together when BinningHorizontal is used. Possible values (sum/average)",
          "", (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_BINNINGHORIZONTAL,
      g_param_spec_int ("binning-horizontal", "BinningHorizontal",
          "Number of horizontal photo-sensitive cells to combine together. This reduces the horizontal resolution (width) of the image. A value of 1 indicates that no horizontal binning is performed by the camera.",
          0 /*Min */ , 10 /*Max */ , 0 /*Default */ ,
          (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_BINNINGVERTICAL,
      g_param_spec_int ("binning-vertical", "BinningVertical",
          "Number of vertical photo-sensitive cells to combine together. This reduces the vertical resolution (height) of the image. A value of 1 indicates that no vertical binning is performed by the camera.",
          0 /*Min */ , 10 /*Max */ , 0 /*Default */ ,
          (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_ACQUISITIONMODE,
      g_param_spec_string ("acquisition-mode", "AcquisitionMode",
          "Sets the acquisition mode of the device. It defines mainly the number of frames to capture during an acquisition and the way the acquisition stops. Possible values (continuous/multiframe/singleframe)",
          "continuous",
          (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_DEVICECLOCKSELECTOR,
      g_param_spec_string ("device-clock-selector", "DeviceClockSelector",
          "Selects the clock frequency to access from the device. Possible values (Sensor/SensorDigitization/CameraLink/Device-specific)",
          "", (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_TRIGGERDELAY,
      g_param_spec_float ("trigger-delay", "TriggerDelay",
          "Specifies the delay in microseconds (us) to apply after the trigger reception before activating it.",
          -1 /*Min */ , INT_MAX /*Max */ , -1 /*Default */ ,
          (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_TRIGGERDIVIDER,
      g_param_spec_int ("trigger-divider", "TriggerDivider",
          "Specifies a division factor for the incoming trigger pulses",
          0 /*Min */ , INT_MAX /*Max */ , 0 /*Default */ ,
          (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_TRIGGERMULTIPLIER,
      g_param_spec_int ("trigger-multiplier", "TriggerMultiplier",
          "Specifies a multiplication factor for the incoming trigger pulses.",
          0 /*Min */ , INT_MAX /*Max */ , 0 /*Default */ ,
          (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_TRIGGEROVERLAP,
      g_param_spec_string ("trigger-overlap", "TriggerOverlap",
          "Specifies the type trigger overlap permitted with the previous frame or line. Possible values (Off/ReadOut/PreviousFrame/PreviousLine)",
          "", (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_TRIGGERACTIVATION,
      g_param_spec_string ("trigger-activation", "TriggerActivation",
          "Specifies the activation mode of the trigger. Possible values (RisingEdge/FallingEdge/AnyEdge/LevelHigh/LevelLow)",
          "", (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_TRIGGERSELECTOR,
      g_param_spec_string ("trigger-selector", "TriggerSelector",
          "Selects the type of trigger to configure. Possible values (AcquisitionStart/AcquisitionEnd/AcquisitionActive/FrameStart/FrameEnd/FrameActive/FrameBurstStart/FrameBurstEnd/FrameBurstActive/LineStart/ExposureStart/ExposureEnd/ExposureActive/MultiSlopeExposureLimit1)",
          "", (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_TRIGGERSOURCE,
      g_param_spec_string ("trigger-source", "TriggerSource",
          "Specifies the internal signal or physical input Line to use as the trigger source. Possible values (Software/SoftwareSignal<n>/Line<n>/UserOutput<n>/Counter<n>Start/Counter<n>End/Timer<n>Start/Timer<n>End/Encoder<n>/<LogicBlock<n>>/Action<n>/LinkTrigger<n>/CC<n>/...)",
          "Software",
          (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_HWTRIGGERTIMEOUT,
      g_param_spec_int ("hw-trigger-timeout", "HardwareTriggerTimeout",
          "Wait timeout (in multiples of 5 secs) to receive frames before terminating the application.",
          0 /*Min */ , INT_MAX /*Max */ , 10 /*Default */ ,
          (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_EXPOSUREMODE,
      g_param_spec_string ("exposure-mode", "ExposureMode",
          "Sets the operation mode of the Exposure. Possible values (off/timed/trigger-width/trigger-controlled)",
          "timed", (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_EXPOSUREAUTO,
      g_param_spec_string ("exposure-auto", "ExposureAuto",
          "Sets the automatic exposure mode when ExposureMode is Timed. Possible values(off/once/continuous)",
          "Once", (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_EXPOSURETIMESELECTOR,
      g_param_spec_string ("exposure-time-selector", "ExposureTimeMode",
          "Selects which exposure time is controlled by the ExposureTime feature. This allows for independent control over the exposure components. Possible values(common/red/green/stage1/...)",
          "", (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_EXPOSURETIME,
      g_param_spec_float ("exposure-time", "ExposureTime",
          "Sets the Exposure time (in us) when ExposureMode is Timed and ExposureAuto is Off. This controls the duration where the photosensitive cells are exposed to light.",
          -1 /*Min */ , 10000000 /*Max */ , -1 /*uSec Default */ ,
          (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_BLACKLEVELSELECTOR,
      g_param_spec_string ("black-level-selector", "BlackLevelSelector",
          "Selects which Black Level is controlled by the various Black Level features. Possible values(All,Red,Green,Blue,Y,U,V,Tap1,Tap2...)",
          "All", (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_BLACKLEVELAUTO,
      g_param_spec_string ("black-level-auto", "BlackLevelAuto",
          "Controls the mode for automatic black level adjustment. The exact algorithm used to implement this adjustment is device-specific. Possible values(Off/Once/Continuous)",
          "Off", (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_BLACKLEVEL,
      g_param_spec_float ("black-level", "BlackLevel",
          "Controls the analog black level as an absolute physical value.",
          -9999.0 /*Min */ , 9999.0 /*Max */ , 9999.0 /*Default */ ,
          (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_GAMMA,
      g_param_spec_float ("gamma", "Gamma",
          "Controls the gamma correction of pixel intensity.",
          0 /*Min */ , 5.0 /*Max */ , 1.0 /*Default */ ,
          (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_GAMMASELECTOR,
      g_param_spec_string ("gamma-selector", "GammaSelector",
          "Select the gamma correction mode. Possible values (sRGB/User)",
          "", (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_GAINSELECTOR,
      g_param_spec_string ("gain-selector", "GainSelector",
          "Selects which gain is controlled by the various Gain features. It's device specific. Possible values (All/Red/Green/Blue/Y/U/V...)",
          "All", (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_GAIN,
      g_param_spec_float ("gain", "Gain",
          "Controls the selected gain as an absolute value. This is an amplification factor applied to video signal. Values are device specific.",
          -9999.0 /*Min */ , 9999.0 /*Max */ , 9999.0 /* Default */ ,
          (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_GAINAUTO,
      g_param_spec_string ("gain-auto", "GainAuto",
          "Sets the automatic gain control (AGC) mode. Possible values (off/once/continuous)",
          "off", (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_GAINAUTOBALANCE,
      g_param_spec_string ("gain-auto-balance", "GainAutoBalance",
          "Sets the mode for automatic gain balancing between the sensor color channels or taps. Possible values (off/once/continuous)",
          "off", (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_BALANCERATIOSELECTOR,
      g_param_spec_string ("balance-ratio-selector", "BalanceRatioSelector",
          "Selects which Balance ratio to control. Possible values(All,Red,Green,Blue,Y,U,V,Tap1,Tap2...)",
          "", (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_BALANCERATIO,
      g_param_spec_float ("balance-ratio", "BalanceRatio",
          "Controls ratio of the selected color component to a reference color component",
          0 /*Min */ , 9999.0 /*Max */ , 9999.0 /*Default */ ,
          (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_BALANCEWHITEAUTO,
      g_param_spec_string ("balance-white-auto", "BalanceWhiteAuto",
          "Controls the mode for automatic white balancing between the color channels. The white balancing ratios are automatically adjusted. Possible values(Off,Once,Continuous)",
          "Off", (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class,
      PROP_DEVICELINKTHROUGHPUTLIMIT, g_param_spec_int ("throughput-limit",
          "DeviceLinkThroughputLimit",
          "Limits the maximum bandwidth (in Bps) of the data that will be streamed out by the device on the selected Link. If necessary, delays will be uniformly inserted between transport layer packets in order to control the peak bandwidth.",
          0 /*Min */ , INT_MAX /*Max */ , 10000000 /*Default */ ,
          (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_CHANNELPACKETSIZE,
      g_param_spec_int ("packet-size", "GevSCPSPacketSize",
          "Specifies the stream packet size, in bytes, to send on the selected channel for a Transmitter or specifies the maximum packet size supported by a receiver.",
          0 /*Min */ , INT_MAX /*Max */ , 0 /*Default */ ,
          (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_CHANNELPACKETDELAY,
      g_param_spec_int ("packet-delay", "GevSCPD",
          "Controls the delay (in GEV timestamp counter unit) to insert between each packet for this stream channel. This can be used as a crude flow-control mechanism if the application or the network infrastructure cannot keep up with the packets coming from the device.",
          -1 /*Min */ , INT_MAX /*Max */ , -1 /*Default */ ,
          (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_FRAMERATE,
      g_param_spec_float ("frame-rate", "AcquisitionFrameRate",
          "Controls the acquisition rate (in Hertz) at which the frames are captured.",
          0 /*Min */ , 120 /*Max */ , 0 /*Default */ ,
          (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_RESET,
      g_param_spec_boolean ("reset", "DeviceReset",
          "Resets the device to its power up state. After reset, the device must be rediscovered. Do not use unless absolutely required.",
          false /* Default */ ,
          (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_USEDEFAULTPROPERTIES,
      g_param_spec_boolean ("use-default-properties", "UseDefaultProperties",
          "Resets the gencamsrc properties that are not provided in the gstreamer pipelines to the default values decided by gencamsrc",
          false /* Default */ ,
          (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));
}

static void
gst_gencamsrc_init (GstGencamsrc * gencamsrc)
{
  char* env_variable = "BALLUFF_ACQ_LIC_MODULE";
  char* run_mode = "GENICAM_MODE";
  char* env_variable_value = getenv(env_variable);
  char* run_mode_value = getenv(run_mode);

  if (run_mode_value != NULL) {
    GST_DEBUG_OBJECT (gencamsrc, "GENICAM_MODE is: %s", run_mode_value);
    if (strncmp(run_mode_value, "PROD", 4) == 0) {
      if (env_variable_value != NULL) {
        // commented out for privacy
        // GST_DEBUG_OBJECT (gencamsrc, "BALLUFF_ACQ_LIC_MODULE is: %s", env_variable_value);
      }
      else {
        // commented out for privacy
        // GST_DEBUG_OBJECT (gencamsrc, "BALLUFF_ACQ_LIC_MODULE doesn't exist. Setting it now...");
        setenv(env_variable,"/usr/local/lib/gstreamer-1.0/libgstgencamsrc.so",1);
        // commented out for privacy
        // env_variable_value = getenv(env_variable);
        // GST_DEBUG_OBJECT (gencamsrc, "new BALLUFF_ACQ_LIC_MODULE is: %s", env_variable_value);
      }
    }
  }
  else {
    GST_DEBUG_OBJECT (gencamsrc, "GENICAM_MODE doesn't exist");
  }

  // disabling unlimited license for Balluff from DLStreamer Pipeline Server v2.2.0 onwards
  unsetenv(env_variable);

  GencamParams *prop = &gencamsrc->properties;

  // Set following for live source
  gst_base_src_set_format (GST_BASE_SRC (gencamsrc), GST_FORMAT_TIME);
  gst_base_src_set_live (GST_BASE_SRC (gencamsrc), TRUE);

  // Initialize data members
  gencamsrc->frameNumber = 0;

  // Initialize core
  gencamsrc->gencam = NULL;

  // Initialize plugin properties with dummy values
  prop->deviceSerialNumber = NULL;
  prop->pixelFormat = "mono8\0";
  prop->width = WIDTH;
  prop->height = HEIGHT;
  prop->offsetX = 0;
  prop->offsetY = 0;
  // provide 0 since 0 is invalid value
  prop->decimationHorizontal = 0;
  prop->decimationVertical = 0;
  prop->balanceRatio = 9999.0;
  prop->balanceWhiteAuto = "Off\0";
  prop->balanceRatioSelector = NULL;
  prop->binningSelector = NULL;
  prop->binningHorizontalMode = NULL;
  prop->binningHorizontal = 0;
  prop->binningVerticalMode = NULL;
  prop->binningVertical = 0;
  prop->acquisitionMode = "continuous\0";
  prop->exposureMode = "Timed\0";
  prop->exposureAuto = "Once\0";
  prop->exposureTimeSelector = NULL;
  // provide -1 since 0 is valid value and -1 is invalid value
  prop->exposureTime = -1;
  prop->blackLevelSelector = "All\0";
  prop->blackLevelAuto = "Off\0";
  prop->blackLevel = 9999.0;
  prop->gamma = 1.0;
  prop->gammaSelector = NULL;
  prop->gainSelector = "All\0";
  prop->gain = 9999.0;
  prop->gainAuto = "Off\0";
  prop->gainAutoBalance = "Off\0";
  prop->triggerDelay = -1;
  prop->triggerSelector = NULL;
  prop->triggerSource = "Software\0";
  prop->triggerOverlap = NULL;
  prop->triggerActivation = NULL;
  prop->triggerMultiplier = 0;
  prop->triggerDivider = 0;
  prop->hwTriggerTimeout = 10;
  prop->deviceLinkThroughputLimit = 10000000;
  prop->channelPacketSize = 0;
  prop->channelPacketDelay = -1;
  prop->acquisitionFrameRate = 0;
  prop->deviceClockSelector = NULL;
  prop->deviceReset = false;
  prop->useDefaultProperties = false;

  // TODO: instead of hardcoding the size as 45 for propertyHolder, perhape use sizeof
  // initialize every index of this integer array to -1. To know if a particular property is provided by user, check the property's index (in the enum provided above) in propertyHolder.
  // If the value at the index is not -1, then it means that the property is provided by user.
  for(int i = 0; i < 45; i++) {
    prop->propertyHolder[i] = -1;
  }

  gencamsrc->prevSecTime = 0;
  gencamsrc->elapsedTime = 0;
  gencamsrc->frames = 0;

  // Initialize gencam base class and assign properties
  gencamsrc_init (&gencamsrc->properties, (GstBaseSrc *) gencamsrc);

  GST_DEBUG_OBJECT (gencamsrc, "The init function");
}

void
gst_gencamsrc_set_property (GObject * object, guint property_id,
    const GValue * value, GParamSpec * pspec)
// This function gets called for every property provided by the user.
{
  GstGencamsrc *gencamsrc = GST_GENCAMSRC (object);
  GencamParams *prop = &gencamsrc->properties;

  GST_DEBUG_OBJECT (gencamsrc, "set_property");

  // update the propertyHolder. property_id will be the index in the enum
  // ex: for PROP_PIXELFORMAT, propertyHolder[2] = 2 since enum { PROP_0, PROP_SERIAL, PROP_PIXELFORMAT,....}
  prop->propertyHolder[property_id] = property_id;
  switch (property_id) {
    case PROP_SERIAL:
      prop->deviceSerialNumber = g_value_dup_string (value + '\0');
      break;
    case PROP_PIXELFORMAT:
      prop->pixelFormat = g_value_dup_string (value + '\0');
      break;
    case PROP_WIDTH:
      GST_DEBUG_OBJECT (gencamsrc, "set_property for width called");
      prop->width = g_value_get_int (value);
      break;
    case PROP_HEIGHT:
      GST_DEBUG_OBJECT (gencamsrc, "set_property for height called");
      prop->height = g_value_get_int (value);
      break;
    case PROP_OFFSETX:
      prop->offsetX = g_value_get_int (value);
      break;
    case PROP_OFFSETY:
      prop->offsetY = g_value_get_int (value);
      break;
    case PROP_DECIMATIONHORIZONTAL:
      prop->decimationHorizontal = g_value_get_int (value);
      break;
    case PROP_DECIMATIONVERTICAL:
      prop->decimationVertical = g_value_get_int (value);
      break;
    case PROP_BINNINGSELECTOR:
      prop->binningSelector = g_value_dup_string (value + '\0');
      break;
    case PROP_BINNINGHORIZONTALMODE:
      prop->binningHorizontalMode = g_value_dup_string (value + '\0');
      break;
    case PROP_BINNINGVERTICALMODE:
      prop->binningVerticalMode = g_value_dup_string (value + '\0');
      break;
    case PROP_BINNINGHORIZONTAL:
      prop->binningHorizontal = g_value_get_int (value);
      break;
    case PROP_BINNINGVERTICAL:
      prop->binningVertical = g_value_get_int (value);
      break;
    case PROP_ACQUISITIONMODE:
      prop->acquisitionMode = g_value_dup_string (value + '\0');
      break;
    case PROP_DEVICECLOCKSELECTOR:
      prop->deviceClockSelector = g_value_dup_string (value + '\0');
      break;
    case PROP_TRIGGERDELAY:
      prop->triggerDelay = g_value_get_float (value);
      break;
    case PROP_TRIGGERDIVIDER:
      prop->triggerDivider = g_value_get_int (value);
      break;
    case PROP_TRIGGERMULTIPLIER:
      prop->triggerMultiplier = g_value_get_int (value);
      break;
    case PROP_TRIGGEROVERLAP:
      prop->triggerOverlap = g_value_dup_string (value + '\0');
      break;
    case PROP_TRIGGERACTIVATION:
      prop->triggerActivation = g_value_dup_string (value + '\0');
      break;
    case PROP_TRIGGERSELECTOR:
      prop->triggerSelector = g_value_dup_string (value + '\0');
      break;
    case PROP_TRIGGERSOURCE:
      prop->triggerSource = g_value_dup_string (value + '\0');
      break;
    case PROP_HWTRIGGERTIMEOUT:
      prop->hwTriggerTimeout = g_value_get_int (value);
      break;
    case PROP_EXPOSUREMODE:
      prop->exposureMode = g_value_dup_string (value + '\0');
      break;
    case PROP_EXPOSURETIME:
      prop->exposureTime = g_value_get_float (value);
      break;
    case PROP_BLACKLEVELSELECTOR:
      prop->blackLevelSelector = g_value_dup_string (value + '\0');
      break;
    case PROP_BALANCEWHITEAUTO:
      prop->balanceWhiteAuto = g_value_dup_string (value + '\0');
      break;
    case PROP_BLACKLEVELAUTO:
      prop->blackLevelAuto = g_value_dup_string (value + '\0');
      break;
    case PROP_BLACKLEVEL:
      prop->blackLevel = g_value_get_float (value);
      break;
    case PROP_GAMMA:
      prop->gamma = g_value_get_float (value);
      break;
    case PROP_GAMMASELECTOR:
      prop->gammaSelector = g_value_dup_string (value + '\0');
      break;
    case PROP_BALANCERATIOSELECTOR:
      prop->balanceRatioSelector = g_value_dup_string (value + '\0');
      break;
    case PROP_BALANCERATIO:
      prop->balanceRatio = g_value_get_float (value);
      break;
    case PROP_EXPOSUREAUTO:
      prop->exposureAuto = g_value_dup_string (value + '\0');
      break;
    case PROP_EXPOSURETIMESELECTOR:
      prop->exposureTimeSelector = g_value_dup_string (value + '\0');
      break;
    case PROP_GAINSELECTOR:
      prop->gainSelector = g_value_dup_string (value + '\0');
      break;
    case PROP_GAIN:
      prop->gain = g_value_get_float (value);
      break;
    case PROP_GAINAUTO:
      prop->gainAuto = g_value_dup_string (value + '\0');
      break;
    case PROP_GAINAUTOBALANCE:
      prop->gainAutoBalance = g_value_dup_string (value + '\0');
      break;
    case PROP_DEVICELINKTHROUGHPUTLIMIT:
      prop->deviceLinkThroughputLimit = g_value_get_int (value);
      break;
    case PROP_CHANNELPACKETSIZE:
      prop->channelPacketSize = g_value_get_int (value);
      break;
    case PROP_CHANNELPACKETDELAY:
      prop->channelPacketDelay = g_value_get_int (value);
      break;
    case PROP_FRAMERATE:
      prop->acquisitionFrameRate = g_value_get_float (value);
      break;
    case PROP_RESET:
      prop->deviceReset = g_value_get_boolean (value);
      break;
    case PROP_USEDEFAULTPROPERTIES:
      prop->useDefaultProperties = g_value_get_boolean (value);
      break;
    default:
      G_OBJECT_WARN_INVALID_PROPERTY_ID (object, property_id, pspec);
      break;
  }
}

void
gst_gencamsrc_get_property (GObject * object, guint property_id,
    GValue * value, GParamSpec * pspec)
{
  GstGencamsrc *gencamsrc = GST_GENCAMSRC (object);
  GencamParams *prop = &gencamsrc->properties;

  GST_DEBUG_OBJECT (gencamsrc, "get_property");

  switch (property_id) {
    case PROP_SERIAL:
      g_value_set_string (value, prop->deviceSerialNumber);
      break;
    case PROP_PIXELFORMAT:
      g_value_set_string (value, prop->pixelFormat);
      break;
    case PROP_WIDTH:
      GST_DEBUG_OBJECT (gencamsrc, "get_property for width called");
      g_value_set_int (value, prop->width);
      break;
    case PROP_HEIGHT:
      GST_DEBUG_OBJECT (gencamsrc, "get_property for height called");
      g_value_set_int (value, prop->height);
      break;
    case PROP_OFFSETX:
      g_value_set_int (value, prop->offsetX);
      break;
    case PROP_OFFSETY:
      g_value_set_int (value, prop->offsetY);
      break;
    case PROP_DECIMATIONHORIZONTAL:
      g_value_set_int (value, prop->decimationHorizontal);
      break;
    case PROP_DECIMATIONVERTICAL:
      g_value_set_int (value, prop->decimationVertical);
      break;
    case PROP_BINNINGSELECTOR:
      g_value_set_string (value, prop->binningSelector);
      break;
    case PROP_BINNINGHORIZONTALMODE:
      g_value_set_string (value, prop->binningHorizontalMode);
      break;
    case PROP_BINNINGVERTICALMODE:
      g_value_set_string (value, prop->binningVerticalMode);
      break;
    case PROP_BINNINGHORIZONTAL:
      g_value_set_int (value, prop->binningHorizontal);
      break;
    case PROP_BINNINGVERTICAL:
      g_value_set_int (value, prop->binningVertical);
      break;
    case PROP_ACQUISITIONMODE:
      g_value_set_string (value, prop->acquisitionMode);
      break;
    case PROP_DEVICECLOCKSELECTOR:
      g_value_set_string (value, prop->deviceClockSelector);
      break;
    case PROP_TRIGGERDELAY:
      g_value_set_float (value, prop->triggerDelay);
      break;
    case PROP_TRIGGERDIVIDER:
      g_value_set_int (value, prop->triggerDivider);
      break;
    case PROP_TRIGGERMULTIPLIER:
      g_value_set_int (value, prop->triggerMultiplier);
      break;
    case PROP_TRIGGEROVERLAP:
      g_value_set_string (value, prop->triggerOverlap);
      break;
    case PROP_TRIGGERACTIVATION:
      g_value_set_string (value, prop->triggerActivation);
      break;
    case PROP_TRIGGERSELECTOR:
      g_value_set_string (value, prop->triggerSelector);
      break;
    case PROP_TRIGGERSOURCE:
      g_value_set_string (value, prop->triggerSource);
      break;
    case PROP_HWTRIGGERTIMEOUT:
      g_value_set_int (value, prop->hwTriggerTimeout);
      break;
    case PROP_EXPOSUREMODE:
      g_value_set_string (value, prop->exposureMode);
      break;
    case PROP_EXPOSURETIME:
      g_value_set_float (value, prop->exposureTime);
      break;
    case PROP_BLACKLEVELSELECTOR:
      g_value_set_string (value, prop->blackLevelSelector);
      break;
    case PROP_BALANCEWHITEAUTO:
      g_value_set_string (value, prop->balanceWhiteAuto);
      break;
    case PROP_BLACKLEVELAUTO:
      g_value_set_string (value, prop->blackLevelAuto);
      break;
    case PROP_BLACKLEVEL:
      g_value_set_float (value, prop->blackLevel);
      break;
    case PROP_GAMMA:
      g_value_set_float (value, prop->gamma);
      break;
    case PROP_GAMMASELECTOR:
      g_value_set_string (value, prop->gammaSelector);
      break;
    case PROP_BALANCERATIOSELECTOR:
      g_value_set_string (value, prop->balanceRatioSelector);
      break;
    case PROP_BALANCERATIO:
      g_value_set_float (value, prop->balanceRatio);
      break;
    case PROP_EXPOSUREAUTO:
      g_value_set_string (value, prop->exposureAuto);
      break;
    case PROP_EXPOSURETIMESELECTOR:
      g_value_set_string (value, prop->exposureTimeSelector);
      break;
    case PROP_GAINSELECTOR:
      g_value_set_string (value, prop->gainSelector);
      break;
    case PROP_GAIN:
      g_value_set_float (value, prop->gain);
      break;
    case PROP_GAINAUTO:
      g_value_set_string (value, prop->gainAuto);
      break;
    case PROP_GAINAUTOBALANCE:
      g_value_set_string (value, prop->gainAutoBalance);
      break;
    case PROP_DEVICELINKTHROUGHPUTLIMIT:
      g_value_set_int (value, prop->deviceLinkThroughputLimit);
      break;
    case PROP_CHANNELPACKETSIZE:
      g_value_set_int (value, prop->channelPacketSize);
      break;
    case PROP_CHANNELPACKETDELAY:
      g_value_set_int (value, prop->channelPacketDelay);
      break;
    case PROP_FRAMERATE:
      g_value_set_float (value, prop->acquisitionFrameRate);
      break;
    case PROP_RESET:
      g_value_set_boolean (value, prop->deviceReset);
      break;
    case PROP_USEDEFAULTPROPERTIES:
      g_value_set_boolean (value, prop->useDefaultProperties);
      break;
    default:
      G_OBJECT_WARN_INVALID_PROPERTY_ID (object, property_id, pspec);
      break;
  }
}

void
gst_gencamsrc_dispose (GObject * object)
{
  GstGencamsrc *gencamsrc = GST_GENCAMSRC (object);

  GST_DEBUG_OBJECT (gencamsrc, "dispose");

  /* clean up as possible. May be called multiple times */
  G_OBJECT_CLASS (gst_gencamsrc_parent_class)->dispose (object);
}

void
gst_gencamsrc_finalize (GObject * object)
{
  GstGencamsrc *gencamsrc = GST_GENCAMSRC (object);

  GST_DEBUG_OBJECT (gencamsrc, "finalize");

  /* clean up object here */
  G_OBJECT_CLASS (gst_gencamsrc_parent_class)->finalize (object);
}

/* get caps from subclass */
static GstCaps *
gst_gencamsrc_get_caps (GstBaseSrc * src, GstCaps * filter)
{
  GstGencamsrc *gencamsrc = GST_GENCAMSRC (src);
  GencamParams *prop = &gencamsrc->properties;

  GST_DEBUG_OBJECT (gencamsrc, "get_caps, src pad %" GST_PTR_FORMAT,
      src->srcpad);

  char *type = "";
  char *format = "";
  if (strcmp (prop->pixelFormat, "mono8") == 0) {
    type = "video/x-raw\0";
    format = "GRAY8\0";
  } else if (strcmp (prop->pixelFormat, "ycbcr411_8") == 0) {
    type = "video/x-raw\0";
    format = "I420\0";
  } else if (strcmp (prop->pixelFormat, "ycbcr422_8") == 0) {
    type = "video/x-raw\0";
    format = "YUY2\0";
  } else if (strcmp (prop->pixelFormat, "rgb8") == 0) {
    type = "video/x-raw\0";
    format = "RGB\0";
  } else if (strcmp (prop->pixelFormat, "bgr8") == 0) {
    type = "video/x-raw\0";
    format = "BGR\0";
  } else if (strcmp (prop->pixelFormat, "bayerbggr") == 0) {
    type = "video/x-bayer\0";
    format = "bggr\0";
  } else if (strcmp (prop->pixelFormat, "bayerrggb") == 0) {
    type = "video/x-bayer\0";
    format = "rggb\0";
  } else if (strcmp (prop->pixelFormat, "bayergrbg") == 0) {
    type = "video/x-bayer\0";
    format = "grbg\0";
  } else if (strcmp (prop->pixelFormat, "bayergbrg") == 0) {
    type = "video/x-bayer\0";
    format = "gbrg\0";
  } else {
    GST_WARNING_OBJECT (gencamsrc, "Unsupported format, defaulting to Mono8");
    free (prop->pixelFormat);
    prop->pixelFormat = "mono8\0";
    type = "video/x-raw\0";
    format = "GRAY8\0";
  }

  //If width or height not initliazed set it to WIDTH and HEIGHT respectively
  if (prop->width == 0)
    prop->width = WIDTH;
  if (prop->height == 0)
    prop->height = HEIGHT;

  GstCaps *caps = gst_caps_new_simple (type,
      "format", G_TYPE_STRING, format,
      "width", G_TYPE_INT, prop->width,
      "height", G_TYPE_INT, prop->height, "framerate",
      GST_TYPE_FRACTION, 120, 1, NULL);

  GST_DEBUG_OBJECT (gencamsrc,
      "The caps sent: %s, %s, %d x %d, variable fps.", type, format,
      prop->width, prop->height);

  return caps;
}

/* decide on caps */
/*static gboolean
gst_gencamsrc_negotiate (GstBaseSrc * src)
{
  GstGencamsrc *gencamsrc = GST_GENCAMSRC (src);

  GST_DEBUG_OBJECT (gencamsrc, "negotiate");

  return TRUE;
}*/

/* called if, in negotiation, caps need fixating */
/*static GstCaps *
gst_gencamsrc_fixate (GstBaseSrc * src, GstCaps * caps)
{
  GstGencamsrc *gencamsrc = GST_GENCAMSRC (src);
  GstStructure *structure;

  GST_DEBUG_OBJECT (gencamsrc, "fixate mainly for framerate");

  caps = gst_caps_make_writable (caps);
  structure = gst_caps_get_structure (caps, 0);

  gst_structure_fixate_field_nearest_int (structure, "width", 640);
  gst_structure_fixate_field_nearest_int (structure, "height", 480);

  if (gst_structure_has_field (structure, "framerate"))
    gst_structure_fixate_field_nearest_fraction (structure, "framerate", 30, 1);
  else
    gst_structure_set (structure, "framerate", GST_TYPE_FRACTION, 30, 1, NULL);

  caps = GST_BASE_SRC_CLASS (parent_class)->fixate (src, caps);
  return caps;

  //return NULL;
}*/

/* notify the subclass of new caps */
static gboolean
gst_gencamsrc_set_caps (GstBaseSrc * src, GstCaps * caps)
{
  GstGencamsrc *gencamsrc = GST_GENCAMSRC (src);
  GstStructure *s = gst_caps_get_structure (caps, 0);

  GST_DEBUG_OBJECT (gencamsrc, "Setting caps to %" GST_PTR_FORMAT, caps);

  if (!g_str_equal ("video/x-bayer", gst_structure_get_name (s))
      && (!g_str_equal ("video/x-raw", gst_structure_get_name (s))
          || (!g_str_equal ("I420", gst_structure_get_string (s, "format"))
              && !g_str_equal ("YUY2", gst_structure_get_string (s, "format"))
              && !g_str_equal ("RGB", gst_structure_get_string (s, "format"))
              && !g_str_equal ("BGR", gst_structure_get_string (s, "format"))
              && !g_str_equal ("GRAY8", gst_structure_get_string (s,
                      "format"))))) {

    GST_ERROR_OBJECT (src, "unsupported caps %" GST_PTR_FORMAT, caps);

    return FALSE;
  }

  return TRUE;
}

/* start and stop processing, ideal for opening/closing the resource */
static gboolean
gst_gencamsrc_start (GstBaseSrc * src)
{
  GstGencamsrc *gencamsrc = GST_GENCAMSRC (src);

  GST_DEBUG_OBJECT (gencamsrc, "camera open, set property and start");

  return gencamsrc_start (src);
}

static gboolean
gst_gencamsrc_stop (GstBaseSrc * src)
{
  GstGencamsrc *gencamsrc = GST_GENCAMSRC (src);

  GST_DEBUG_OBJECT (gencamsrc, "stop camera and close");

  return gencamsrc_stop (src);
}

/* given a buffer, return start and stop time when it should be pushed
 * out. The base class will sync on the clock using these times. */
static void
gst_gencamsrc_get_times (GstBaseSrc * src, GstBuffer * buffer,
    GstClockTime * start, GstClockTime * end)
{
  GstGencamsrc *gencamsrc = GST_GENCAMSRC (src);

  {
    GstClockTime timestamp = GST_BUFFER_PTS (buffer);
    *start = timestamp;
    *end = timestamp +
        (unsigned long) (TIMETICK_NS /
        gencamsrc->properties.acquisitionFrameRate);
  }

  GST_DEBUG_OBJECT (gencamsrc, "get_times %" GST_TIME_FORMAT,
      GST_TIME_ARGS (GST_BUFFER_PTS (buffer)));
}

/* notify subclasses of a query */
/*static gboolean
gst_gencamsrc_query (GstBaseSrc * src, GstQuery * query)
{
  GstGencamsrc *gencamsrc = GST_GENCAMSRC (src);

  GST_DEBUG_OBJECT (gencamsrc, "query");

  return TRUE;
}*/

/* notify subclasses of an event */
/*static gboolean
gst_gencamsrc_event (GstBaseSrc * src, GstEvent * event)
{
  GstGencamsrc *gencamsrc = GST_GENCAMSRC (src);

  GST_DEBUG_OBJECT (gencamsrc, "event");

  return TRUE;
}*/

/* ask the subclass to create a buffer with offset and size, the default
 * implementation will call alloc and fill. */
static GstFlowReturn
gst_gencamsrc_create (GstPushSrc * src, GstBuffer ** buf)
{
  GstGencamsrc *gencamsrc = GST_GENCAMSRC (src);
  GstMapInfo mapInfo;

  GST_DEBUG_OBJECT (gencamsrc, "create frames");

  if (gencamsrc_create (buf, &mapInfo, (GstBaseSrc *) gencamsrc)) {
    // Set DTS to none
    // PTS is set inside the create function above
    GST_BUFFER_DTS (*buf) = GST_CLOCK_TIME_NONE;
    gst_object_sync_values (GST_OBJECT (src), GST_BUFFER_PTS (*buf));
    gst_buffer_unmap (*buf, &mapInfo);

    // Set frame offset
    GST_BUFFER_OFFSET (*buf) = gencamsrc->frameNumber;
    ++gencamsrc->frameNumber;
    GST_BUFFER_OFFSET_END (*buf) = gencamsrc->frameNumber;

    GST_DEBUG_OBJECT (src,
        "Frame number: %u, Timestamp: %" GST_TIME_FORMAT,
        gencamsrc->frameNumber, GST_TIME_ARGS (GST_BUFFER_PTS (*buf)));

    // get current time
    gint64 time =
        GST_TIME_AS_MSECONDS (gst_clock_get_time (gst_element_get_clock (
                (GstElement *) gencamsrc)));
    gencamsrc->prevSecTime =
        ((gencamsrc->prevSecTime == 0) ? time : gencamsrc->prevSecTime);
    gencamsrc->elapsedTime = time - gencamsrc->prevSecTime;
    // check if time elapsed is > 1s
    if (gencamsrc->elapsedTime >= FPS_REPORT_TIME) {
      int64_t frames = gencamsrc->frameNumber - gencamsrc->frames;
      int64_t elapsedTime = gencamsrc->elapsedTime;
      GST_INFO_OBJECT (src, "FPS: %f (Calculated time per frame: %.1fms)",
          ((float) frames / ((float) elapsedTime / FPS_REPORT_TIME)),
          (float) elapsedTime / frames);
      // record last frame# and frametime
      gencamsrc->frames = gencamsrc->frameNumber;
      gencamsrc->prevSecTime = time;
    }
  } else {
    GST_DEBUG_OBJECT (src, "Frame number: %u", gencamsrc->frameNumber);
    return GST_FLOW_ERROR;
  }

  return GST_FLOW_OK;
}

static gboolean
plugin_init (GstPlugin * plugin)
{

  return gst_element_register (plugin, "gencamsrc", GST_RANK_NONE,
      GST_TYPE_GENCAMSRC);
}

#ifndef VERSION
#define VERSION "1.3.0"
#endif
#ifndef PACKAGE
#define PACKAGE "gst-gencamsrc"
#endif
#ifndef PACKAGE_NAME
#define PACKAGE_NAME "gst-gencamsrc"
#endif
#ifndef GST_PACKAGE_ORIGIN
#define GST_PACKAGE_ORIGIN "https://www.intel.com/"
#endif

GST_PLUGIN_DEFINE (GST_VERSION_MAJOR, GST_VERSION_MINOR, gencamsrc,
    "Intel generic camera source elements", plugin_init, VERSION,
    "BSD", PACKAGE_NAME, GST_PACKAGE_ORIGIN)
