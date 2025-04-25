/*
 * GStreamer Generic Camera Plugin
 * Copyright (c) 2020, Intel Corporation
 * All rights reserved.
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

#ifndef _GEN_I_CAM_H_
#define _GEN_I_CAM_H_

#include <gst/gst.h>
#include <gst/video/video-format.h>

#include "gencambase.h"

//---------------------------- includes for streaming -----------------------------
#include "genicam-core/rc_genicam_api/buffer.h"
#include "genicam-core/rc_genicam_api/config.h"
#include "genicam-core/rc_genicam_api/device.h"
#include "genicam-core/rc_genicam_api/image.h"
#include "genicam-core/rc_genicam_api/image_store.h"
#include "genicam-core/rc_genicam_api/interface.h"
#include "genicam-core/rc_genicam_api/stream.h"
#include "genicam-core/rc_genicam_api/system.h"
#include "genicam-core/rc_genicam_api/pixel_formats.h"

#include <Base/GCException.h>

#include <signal.h>
#include <algorithm>
#include <atomic>
#include <chrono>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <thread>
// ------------------------------------------------------------------------------

#define EXTERNC extern "C"

#define ROUNDED_DOWN(val, align)        ((val) & ~((align)))
#define ROUNDED_UP(  val, align)        ROUNDED_DOWN((val) + (align) - 1, (align))
#define GRAB_DELAY 5  // In seconds

class Genicam
{
public:
  /*
   * Initializes the pointer data member to parameter structure

   @param params       Pointer to gencamParams structure to initialize
   @return             True if data member is assigned from the pointer
   */
  bool Init (GencamParams * params, GstBaseSrc * src);

  /*
   * Opens the camera device, configures the camera with the defined parameters
   and starts the streaming

   @return             True if width, height and pixel format are successfully
   configured. False otherwise. True is returned
   irrespective of other configurations success or fail.
   */
  bool Start (void);

  /*
   * Stops the streaming and closes the device

   @return             True after stopping the streaming and closing the device
   */
  bool Stop (void);

  /*
   * Creates the buffer corresponding to a frame to be pushed in the pipeline

   @param buf          Double pointer GstBuffer structure to allocate the
   buffer and copy the frame data
   @param mapInfo      Pointer to the structure that contains buffer
   information
   @return             True after receiving the buffer containing a frame.
   False otherwise.
   */
  bool Create (GstBuffer ** buf, GstMapInfo * mapInfo);

private:
  /* Pointer to gencamParams structure */
    GencamParams * gencamParams;

  /* Pointer to gencamsrc structure */
    GstBaseSrc * gencamsrc;

  /* Serial number of all connected cameras */
    std::vector <std::string> serials;

  /* Shared pointer to device object */
    std::shared_ptr < rcg::Device > dev;

  /* Shared pointer to stream object */
    std::vector < std::shared_ptr < rcg::Stream >> stream;

  /* Shared pointer to nodemap */
    std::shared_ptr < GenApi::CNodeMapRef > nodemap;

  /*Camera information*/
  struct camInfo_t {
      std::string vendorName; // Camera vendor name
      std::string modelName;  // Camera model name
  } camInfo;

  /* For trigger mode */
    std::string triggerMode;

  /* For black level auto */
    std::string blackLevelAuto;

  /* For gain auto */
    std::string gainAuto;

  /* For width max */
    int widthMax;

  /* For height max */
    int heightMax;

  /* For offset redable */
    bool offsetXYwritable;

  /* For trigger source */
    std::string triggerSource;

  /* For acquisition mode */
    std::string acquisitionMode;

  /* For checking if Acquisition Status is a feature or not */
  bool isAcquisitionStatusFeature;

  /* Device Link Throughput Limit Mode
   * This is not exposed outside and set automatically depending
   * on Device Link Throughput Limit value */
    std::string deviceLinkThroughputLimitMode;

  // Feature type list
  enum featureType {
    TYPE_NO = 0,
    TYPE_ENUM,
    TYPE_INT,
    TYPE_FLOAT,
    TYPE_BOOL,
    TYPE_STRING,
    TYPE_CMD,
    MAX_TYPE
  };

  /* Check if the feature is present or not */
  bool isFeature (const char *, featureType *);

  /* Generic enum feature method */
  bool setEnumFeature (const char *, const char *, const bool);

  /* Generic int feature method */
  bool setIntFeature (const char *, int *, const bool);

  /* Generic float feature method */
  bool setFloatFeature (const char *, float *, const bool);

  /* Get Camera Information */
  void getCameraInfo (void);

  /* Get Serial Number of camera */
  bool getCameraSerialNumber (void);

  /* Resets the device to factory power up state */
  bool resetDevice (void);

  /* Sets binning selector feature */
  bool setBinningSelector (void);

  /* Sets binning horizontal mode feature */
  bool setBinningHorizontalMode (void);

  /* Sets binning horizontal feature */
  bool setBinningHorizontal (void);

  /* Sets binning vertical mode feature */
  bool setBinningVerticalMode (void);

  /* Sets binning vertical feature */
  bool setBinningVertical (void);

  /* Sets decimation horizontal feature */
  bool setDecimationHorizontal (void);

  /* Sets decimation vertical feature */
  bool setDecimationVertical (void);

  /* Sets width and height */
  bool setWidthHeight (void);

  /* Sets pixel format */
  bool setPixelFormat (void);

  /* Sets offset-x and offset-y features */
  bool setOffsetXY (void);

  /* Sets acquisition frame rate */
  bool setAcquisitionFrameRate (void);

  /* Sets device clock selector */
  bool setDeviceClockSelector (void);

  /* Gets device clock frequency */
  bool getDeviceClockFrequency (void);

  /* Sets exposure mode */
  bool setExposureMode (void);

  /* Sets exposure time if exposure mode is timed */
  bool setExposureTime (void);

  /* Sets exposure auto */
  bool setExposureAuto (void);

  /* Sets exposure time selector */
  bool setExposureTimeSelector (void);

  /* Sets Black Level Selector */
  bool setBlackLevelSelector (void);

  /* Sets Black Level Auto */
  bool setBlackLevelAuto (void);

  /* Sets Black Level */
  bool setBlackLevel (void);

  /* Sets Gamma */
  bool setGamma (void);

  /* Sets gain selector */
  bool setGainSelector (void);

  /* Sets gain */
  bool setGain (void);

  /* Sets gain auto */
  bool setGainAuto (void);

  /* Sets gain auto balance */
  bool setGainAutoBalance (void);

  /* Sets Balance White Auto */
  bool setBalanceWhiteAuto (void);

  /* Sets Balance Ratio */
  bool setBalanceRatio (void);

  /* Sets acquisition mode */
  bool setAcquisitionMode (void);

  /* Sets Trigger Multiplier */
  bool setTriggerMultiplier (void);

  /* Sets Trigger Divider */
  bool setTriggerDivider (void);

  /* Sets Trigger Delay */
  bool setTriggerDelay (void);

  /* Sets Trigger Mode */
  bool setTriggerMode (const char *);

  /* Sets Trigger Overlap */
  bool setTriggerOverlap (void);

  /* Sets Trigger Activation */
  bool setTriggerActivation (void);

  /* Sets Trigger Selector */
  bool setTriggerSelector (void);

  /* Sets Trigger Source */
  bool setTriggerSource (void);

  /* Sets Trigger Software */
  bool setTriggerSoftware (void);

  /* Sets the Stream Packet Size */
  bool setChannelPacketSize (void);

  /* Sets the Stream Packet Delay */
  bool setChannelPacketDelay (void);

  /* Sets Device Link Throughput Limit */
  bool setDeviceLinkThroughputLimit (void);
};

#endif
