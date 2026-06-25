/*
# Apache v2 license
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
*/

#ifndef _GEN_CAM_BASE_H_
#define _GEN_CAM_BASE_H_

#include <stdbool.h>

#include <gst/gst.h>
#include <gst/base/gstpushsrc.h>
#include <gst/video/video-format.h>

#define EXTERNC extern "C"

#ifdef __cplusplus
extern "C"
{
#endif

  /* Parameters structure for configuration by the user */
  typedef struct _GencamParams
  {
    const char *deviceSerialNumber; /* Identify the device to stream from */
    char *pixelFormat;          /* Format of the pixels from camera */
    char *binningSelector;      /* Binning engine controlled by
                                   binning horizontal and binning vertical */
    char *binningHorizontalMode; /* Mode to combine horizontal
                                   photo-sensitive cells */
    char *binningVerticalMode;  /* Mode to combine vertical
                                   photo-sensitive cells */
    char *exposureAuto;         /* Timed exposure type */
    char *exposureTimeSelector; /* Exposure related operations */
    char *exposureMode;         /* Operation mode of exposure */
    char *triggerOverlap;       /* Overlap type with previous frame or line */
    char *triggerActivation;    /* Capture TriggerActivation */
    char *triggerSelector;      /* Capture Trigger Selector */
    char *triggerSource;        /* Capture Trigger Source */
    char *acquisitionMode;      /* Frame Acquisition Mode  */
    char *blackLevelSelector;   /* Configure which brightness of the picture to set */
    char *blackLevelAuto;       /* Control the automatic black level adjustments */
    char *gammaSelector;        /* Configure the gamma selector */
    char *gainSelector;         /* All channels or particular channel in
                                   analog/digital */
    char *gainAuto;             /* Automatic gain control (AGC) mode */
    char *gainAutoBalance;      /* Automatic gain balancing between channels */
    char *balanceRatioSelector; /* Select the balance ratio control */
    char *balanceWhiteAuto;     /* Automatically corrects color shifts in images */
    char *deviceClockSelector;  /* Select clock frequency to access from device*/
    int binningHorizontal;      /* Number of horizontal photo-sensitive
                                   cells to combine */
    int binningVertical;        /* Number of vertical photo-sensitive
                                   cells to combine */
    int decimationHorizontal;   /* Horizontal sub-sampling of the image */
    int decimationVertical;     /* Vertical sub-sampling of the image */
    int width;                  /* Width of the ROI in pixels */
    int height;                 /* Height of the ROI in pixels */
    int offsetX;                /* Offset of ROI left pixel */
    int offsetY;                /* Offset of ROI top pixel */
    int triggerDivider;         /* Division factor for trigger pulses */
    int triggerMultiplier;      /* Multiplication factor for trigger pulses */
    int hwTriggerTimeout;       /* Retry while waiting for the hw trigger */
    int deviceLinkThroughputLimit; /* Max bandwidth streamed by the camera */
    int channelPacketSize;      /* Specifies the packet size */
    int channelPacketDelay;     /* controls delay between each packets  */
    float triggerDelay;         /* Capture Trigger Delay */
    float exposureTime;         /* Exposure Time in us */
    float gain;                 /* Amplification applied to video signal */
    float acquisitionFrameRate; /* Controls the acquisition rate */
    float blackLevel;           /* configure overall brightness of the picture */
    float gamma;                /* Controls the gamma correction of pixel intensity */
    float balanceRatio;         /* Controls ratio of the selected color */
    bool deviceReset;           /* Resets the device to factory state */
    bool useDefaultProperties;  /* Resets the gencamsrc properties that are not provided in the gstreamer pipelines to the default values decided by gencamsrc */
    int propertyHolder[45];   /* For decision making of whether to use the above 45 properties or not in the camera based on useDefaultProperties value. A property provided as user input has a "non -1" value at a designated index in this array*/
  } GencamParams;

  /* Initialize generic camera base class */
  bool gencamsrc_init (GencamParams *, GstBaseSrc *);

  /* Open the camera device and connect */
  bool gencamsrc_start (GstBaseSrc * src);

  /* Close the device */
  bool gencamsrc_stop (GstBaseSrc * src);

  /* Receive the frame to create output buffer */
  bool gencamsrc_create (GstBuffer ** buf, GstMapInfo * mapInfo, GstBaseSrc *src);
#ifdef __cplusplus
}
#endif

#endif
