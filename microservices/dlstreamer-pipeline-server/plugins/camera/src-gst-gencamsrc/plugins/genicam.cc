/*
 * GStreamer Generic Camera Plugin
 * Copyright (c) 2020, Intel Corporation
 * All rights reserved.
 *
 * Authors:
 *   Gowtham Hosamane <gowtham.hosamane@intel.com>
 *   Smitesh Sutaria <smitesh.sutaria@intel.com>
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

#include "genicam.h"
#include "gstgencamsrc.h"

GST_DEBUG_CATEGORY_EXTERN (gst_gencamsrc_debug_category);
#define GST_CAT_DEFAULT gst_gencamsrc_debug_category

bool
Genicam::Init (GencamParams * params, GstBaseSrc * src)
{
  gencamsrc = src;
  GST_DEBUG_OBJECT (gencamsrc, "START: %s", __func__);

  gencamParams = params;

  triggerMode.assign ("Off\0");
  deviceLinkThroughputLimitMode.assign ("Off\0");

  GST_DEBUG_OBJECT (gencamsrc, "END: %s", __func__);
  return TRUE;
}


bool
Genicam::Start (void)
{
  /* Enumerate & open device.
     Set the property (resolution, pixel format, etc.,)
     allocate buffers and start streaming from the camera */

  GST_DEBUG_OBJECT (gencamsrc, "START: %s", __func__);

  /* Get Serial Number */
  if (gencamParams->deviceSerialNumber == NULL) {
    getCameraSerialNumber ();
  }

  dev = rcg::getDevice (gencamParams->deviceSerialNumber);

  if (dev) {

    dev->open (rcg::Device::CONTROL);
    GST_INFO_OBJECT (gencamsrc, "Camera: %s opened successfully.",
        gencamParams->deviceSerialNumber);

    nodemap = dev->getRemoteNodeMap ();

    getCameraInfo ();

    // get chunk adapter (this switches chunk mode on if possible and
    // returns a null pointer if this is not possible)
    std::shared_ptr < GenApi::CChunkAdapter > chunkadapter = 0;

    try {
      // DeviceReset feature
      if (gencamParams->deviceReset == true) {
        return resetDevice ();
      }
      // Binning selector feature
      if (gencamParams->binningSelector) {
        // if this is a user provided input, then set it.
        // Otherwise, only set it if default value is instructed to be set
        if (gencamParams->propertyHolder[9] != -1) {
          setBinningSelector ();
        }
        else {
          if (gencamParams->useDefaultProperties == true) {
            setBinningSelector ();
          }
        }
      }

      // Binning horizontal mode feature
      if (gencamParams->binningHorizontalMode) {
        // if this is a user provided input, then set it.
        // Otherwise, only set it if default value is instructed to be set
        if (gencamParams->propertyHolder[10] != -1) {
          setBinningHorizontalMode ();
        }
        else {
          if (gencamParams->useDefaultProperties == true) {
            setBinningHorizontalMode ();
          }
        }
      }

      // Binning Horizontal feature
      if (gencamParams->binningHorizontal > 0) {
        // if this is a user provided input, then set it.
        // Otherwise, only set it if default value is instructed to be set
        if (gencamParams->propertyHolder[12] != -1) {
          setBinningHorizontal ();
        }
        else {
          if (gencamParams->useDefaultProperties == true) {
            setBinningHorizontal ();
          }
        }
      }
      
      // Binning Vertical mode feature
      if (gencamParams->binningVerticalMode) {
        // if this is a user provided input, then set it.
        // Otherwise, only set it if default value is instructed to be set
        if (gencamParams->propertyHolder[11] != -1) {
          setBinningVerticalMode ();
        }
        else {
          if (gencamParams->useDefaultProperties == true) {
            setBinningVerticalMode ();
          }
        }
      }

      // Binning Vertical feature
      if (gencamParams->binningVertical > 0) {
        // if this is a user provided input, then set it.
        // Otherwise, only set it if default value is instructed to be set
        if (gencamParams->propertyHolder[13] != -1) {
          setBinningVertical ();
        }
        else {
          if (gencamParams->useDefaultProperties == true) {
            setBinningVertical ();
          }
        }
      }

      // Decimation Horizontal feature
      if (gencamParams->decimationHorizontal > 0) {
        // if this is a user provided input, then set it.
        // Otherwise, only set it if default value is instructed to be set
        if (gencamParams->propertyHolder[7] != -1) {
          setDecimationHorizontal ();
        }
        else {
          if (gencamParams->useDefaultProperties == true) {
            setDecimationHorizontal ();
          }
        }
      }

      // Decimation Vertical feature
      if (gencamParams->decimationVertical > 0) {
        // if this is a user provided input, then set it.
        // Otherwise, only set it if default value is instructed to be set
        if (gencamParams->propertyHolder[8] != -1) {
          setDecimationVertical ();
        }
        else {
          if (gencamParams->useDefaultProperties == true) {
            setDecimationVertical ();
          }
        }
      }
      
      // Width and Height features
      if (!setWidthHeight ()) {
        return FALSE;
      }

      // PixelFormat and PixelSize features. 
      // Defaults to mono8 if explicitly no pixel-format is specified by user. 
      // Doesn't retain previously set pixel format in camera from GUI tools like Pylonviewer, VimbaSDK, Impact Acquire etc.,
      // Doesn't use the camera's static datasheet value (camera's default value) for pixel-format either.
      if (!setPixelFormat ()) {
        return FALSE;
      }

      // // if this is a user provided input, then set it.
      // // Otherwise, only set it if default value is instructed to be set
      // if (gencamParams->propertyHolder[2] != -1) {
      //   // PixelFormat and PixelSize features
      //   if (!setPixelFormat ()) {
      //     return FALSE;
      //   }
      // }
      // else {
      //   if (gencamParams->useDefaultProperties == true) {
      //     // PixelFormat and PixelSize features
      //     if (!setPixelFormat ()) {
      //       return FALSE;
      //     }
      //   }
      // }

    }
    catch (const std::exception & ex) {
      GST_ERROR_OBJECT (gencamsrc, "Exception: %s", ex.what ());
      Stop ();
      return FALSE;
    }
    catch (const GENICAM_NAMESPACE::GenericException & ex) {
      GST_ERROR_OBJECT (gencamsrc, "Exception: %s", ex.what ());
      Stop ();
      return FALSE;
    }
    catch ( ...) {
      GST_ERROR_OBJECT (gencamsrc, "Exception: unknown");
      Stop ();
      return FALSE;
    }

    /* Configure other features below,
       failure of which doesn't require pipeline to be reconnected
     */
    {
      // OffsetX and OffsetY feature
      if (offsetXYwritable) {
        // if this is a user provided input, then set it.
        // Otherwise, only set it if default value is instructed to be set
        if (gencamParams->propertyHolder[5] != -1 || gencamParams->propertyHolder[6] != -1) {
          setOffsetXY ();
        }
        else {
          if (gencamParams->useDefaultProperties == true) {
            setOffsetXY ();
          }
        }
      }
      // Device Clock Selector feature
      if (gencamParams->deviceClockSelector) {
        // if this is a user provided input, then set it.
        // Otherwise, only set it if default value is instructed to be set
        if (gencamParams->propertyHolder[15] != -1) {
          setDeviceClockSelector ();
        }
        else {
          if (gencamParams->useDefaultProperties == true) {
            setDeviceClockSelector ();
          }
        }
      }
      // Read Device Clock Frequency
      getDeviceClockFrequency ();

      /* DeviceLinkThroughputLimit and Mode features */
      if (gencamParams->deviceLinkThroughputLimit > 0) {
        // if this is a user provided input, then set it.
        // Otherwise, only set it if default value is instructed to be set
        if (gencamParams->propertyHolder[40] != -1) {
          setDeviceLinkThroughputLimit ();
        }
        else {
          if (gencamParams->useDefaultProperties == true) {
            setDeviceLinkThroughputLimit ();
          }
        }
      }

      // if this is a user provided input, then set it.
      // Otherwise, only set it if default value is instructed to be set
      if (gencamParams->propertyHolder[43] != -1) {
        // Acquisition Frame Rate feature
        // This has to be after throughput limit as that has impact on this
        setAcquisitionFrameRate ();
      }
      else {
        if (gencamParams->useDefaultProperties == true) {
          // Acquisition Frame Rate feature
          // This has to be after throughput limit as that has impact on this
          setAcquisitionFrameRate ();
        }
      }

      // Acquisition Mode feature
      if (gencamParams->acquisitionMode) {
        setAcquisitionMode ();
        // // if this is a user provided input, then set it.
        // // Otherwise, only set it if default value is instructed to be set
        // if (gencamParams->propertyHolder[14] != -1) {
        //   setAcquisitionMode ();
        // }
        // else {
        //   if (gencamParams->useDefaultProperties == true) {
        //     setAcquisitionMode ();
        //   }
        // }
      }

      // Trigger Selector feature
      if (gencamParams->triggerSelector) {
        // if this is a user provided input, then set it.
        // Otherwise, only set it if default value is instructed to be set
        if (gencamParams->propertyHolder[21] != -1) {
          setTriggerSelector ();
        }
        else {
          if (gencamParams->useDefaultProperties == true) {
            setTriggerSelector ();
          }
        }
      }

      // Trigger Activation feature
      if (gencamParams->triggerActivation) {
        // if this is a user provided input, then set it.
        // Otherwise, only set it if default value is instructed to be set
        if (gencamParams->propertyHolder[20] != -1) {
          setTriggerActivation ();
        }
        else {
          if (gencamParams->useDefaultProperties == true) {
            setTriggerActivation ();
          }
        }
      }

      // Trigger Source feature, needs trigger mode on
      if (gencamParams->triggerSource) {
        // if this is a user provided input, then set it.
        // Otherwise, only set it if default value is instructed to be set
        if (gencamParams->propertyHolder[22] != -1) {
          setTriggerSource ();
        }
        else {
          if (gencamParams->useDefaultProperties == true) {
            setTriggerSource ();
          }
        }
      }

      // Trigger Multiplier feature
      if (gencamParams->triggerMultiplier > 0) {
        // if this is a user provided input, then set it.
        // Otherwise, only set it if default value is instructed to be set
        if (gencamParams->propertyHolder[18] != -1) {
          setTriggerMultiplier ();
        }
        else {
          if (gencamParams->useDefaultProperties == true) {
            setTriggerMultiplier ();
          }
        }
      }

      // Trigger Divider feature
      if (gencamParams->triggerDivider > 0) {
        // if this is a user provided input, then set it.
        // Otherwise, only set it if default value is instructed to be set
        if (gencamParams->propertyHolder[17] != -1) {
          setTriggerDivider ();
        }
        else {
          if (gencamParams->useDefaultProperties == true) {
            setTriggerDivider ();
          }
        }
      }

      // TriggerDelay feature
      if (gencamParams->triggerDelay > -1) {
        // if this is a user provided input, then set it.
        // Otherwise, only set it if default value is instructed to be set
        if (gencamParams->propertyHolder[16] != -1) {
          setTriggerDelay ();
        }
        else {
          if (gencamParams->useDefaultProperties == true) {
            setTriggerDelay ();
          }
        }
      }

      // Trigger overlap feature
      if (gencamParams->triggerOverlap) {
        // if this is a user provided input, then set it.
        // Otherwise, only set it if default value is instructed to be set
        if (gencamParams->propertyHolder[19] != -1) {
          setTriggerOverlap ();
        }
        else {
          if (gencamParams->useDefaultProperties == true) {
            setTriggerOverlap ();
          }
        }
      }

      // Exposure Mode feature
      if (gencamParams->exposureMode) {
        // if this is a user provided input, then set it.
        // Otherwise, only set it if default value is instructed to be set
        if (gencamParams->propertyHolder[24] != -1) {
          setExposureMode ();
        }
        else {
          if (gencamParams->useDefaultProperties == true) {
            setExposureMode ();
          }
        }
      }

      // Exposure Auto feature
      if (gencamParams->exposureAuto) {
        // if this is a user provided input, then set it.
        // Otherwise, only set it if default value is instructed to be set
        if (gencamParams->propertyHolder[26] != -1) {
          setExposureAuto ();
        }
        else {
          if (gencamParams->useDefaultProperties == true) {
            setExposureAuto ();
          }
        }
      }

      // Balance White Auto Feature
      if (gencamParams->balanceWhiteAuto) {
        // if this is a user provided input, then set it.
        // Otherwise, only set it if default value is instructed to be set
        if (gencamParams->propertyHolder[39] != -1) {
          setBalanceWhiteAuto ();
        }
        else {
          if (gencamParams->useDefaultProperties == true) {
            setBalanceWhiteAuto ();
          }
        }
      }

      // Balance Ratio Feature
      if (gencamParams->balanceRatio != 9999.0
          || gencamParams->balanceRatioSelector) {
        // if this is a user provided input, then set it.
        // Otherwise, only set it if default value is instructed to be set
        if (gencamParams->propertyHolder[38] != -1) {
          setBalanceRatio ();
        }
        else {
          if (gencamParams->useDefaultProperties == true) {
            setBalanceRatio ();
          }
        }
      }

      // Exposure Time Selector feature
      if (gencamParams->exposureTimeSelector) {
        // if this is a user provided input, then set it.
        // Otherwise, only set it if default value is instructed to be set
        if (gencamParams->propertyHolder[27] != -1) {
          setExposureTimeSelector ();
        }
        else {
          if (gencamParams->useDefaultProperties == true) {
            setExposureTimeSelector ();
          }
        }
      }

      // Exposure Time feature
      /* Needs ExposureMode = Timed and ExposureAuto = Off */
      if (gencamParams->exposureTime > -1) {
        GST_DEBUG_OBJECT(gencamsrc, "*****genicamcc: prop->exposureTime is %f", gencamParams->exposureTime);
        // if this is a user provided input, then set it.
        // Otherwise, only set it if default value is instructed to be set
        if (gencamParams->propertyHolder[25] != -1) {
          setExposureTime ();
        }
        else {
          if (gencamParams->useDefaultProperties == true) {
            setExposureTime ();
          }
        }
      }

      // Black Level Selector Feature
      if (gencamParams->blackLevelSelector) {
        // if this is a user provided input, then set it.
        // Otherwise, only set it if default value is instructed to be set
        if (gencamParams->propertyHolder[28] != -1) {
          setBlackLevelSelector ();
        }
        else {
          if (gencamParams->useDefaultProperties == true) {
            setBlackLevelSelector ();
          }
        }
      }

      // Gamma Feature
      if (gencamParams->gamma > 0.0) {
        // if this is a user provided input, then set it.
        // Otherwise, only set it if default value is instructed to be set
        if (gencamParams->propertyHolder[31] != -1) {
          setGamma ();
        }
        else {
          if (gencamParams->useDefaultProperties == true) {
            setGamma ();
          }
        }
      }

      // Black Level Auto Feature
      if (gencamParams->blackLevelAuto) {
        // if this is a user provided input, then set it.
        // Otherwise, only set it if default value is instructed to be set
        if (gencamParams->propertyHolder[29] != -1) {
          setBlackLevelAuto ();
        }
        else {
          if (gencamParams->useDefaultProperties == true) {
            setBlackLevelAuto ();
          }
        }
      }

      // Black Level Feature
      if (gencamParams->blackLevel != 9999.0) {
        // if this is a user provided input, then set it.
        // Otherwise, only set it if default value is instructed to be set
        if (gencamParams->propertyHolder[30] != -1) {
          setBlackLevel ();
        }
        else {
          if (gencamParams->useDefaultProperties == true) {
            setBlackLevel ();
          }
        }
      }

      // Gain selector feature
      if (gencamParams->gainSelector) {
        // if this is a user provided input, then set it.
        // Otherwise, only set it if default value is instructed to be set
        if (gencamParams->propertyHolder[33] != -1) {
          setGainSelector ();
        }
        else {
          if (gencamParams->useDefaultProperties == true) {
            setGainSelector ();
          }
        }
      }

      // Gain auto feature
      if (gencamParams->gainAuto) {
        // if this is a user provided input, then set it.
        // Otherwise, only set it if default value is instructed to be set
        if (gencamParams->propertyHolder[35] != -1) {
          setGainAuto ();
        }
        else {
          if (gencamParams->useDefaultProperties == true) {
            setGainAuto ();
          }
        }
      }
      // Gain feature
      if (gencamParams->gain != 9999.0) {
        // if this is a user provided input, then set it.
        // Otherwise, only set it if default value is instructed to be set
        if (gencamParams->propertyHolder[34] != -1) {
          setGain ();
        }
        else {
          if (gencamParams->useDefaultProperties == true) {
            setGain ();
          }
        }
      }
      // Gain auto balance feature
      if (gencamParams->gainAutoBalance) {
        // if this is a user provided input, then set it.
        // Otherwise, only set it if default value is instructed to be set
        if (gencamParams->propertyHolder[36] != -1) {
          setGainAutoBalance ();
        }
        else {
          if (gencamParams->useDefaultProperties == true) {
            setGainAutoBalance ();
          }
        }
      }
      // StreamChannelPacketSize feature
      if (gencamParams->channelPacketSize > 0) {
        // if this is a user provided input, then set it.
        // Otherwise, only set it if default value is instructed to be set
        if (gencamParams->propertyHolder[41] != -1) {
          setChannelPacketSize ();
        }
        else {
          if (gencamParams->useDefaultProperties == true) {
            setChannelPacketSize ();
          }
        }
      }
      // StreamChannelPacketDelay feature
      if (gencamParams->channelPacketDelay > -1) {
        // if this is a user provided input, then set it.
        // Otherwise, only set it if default value is instructed to be set
        if (gencamParams->propertyHolder[42] != -1) {
          setChannelPacketDelay ();
        }
        else {
          if (gencamParams->useDefaultProperties == true) {
            setChannelPacketDelay ();
          }
        }
      }
    }

    /* Check if AcquisitionStatus feature is present for
       non-continuous mode operation in "Create" */
    isAcquisitionStatusFeature = isFeature ("AcquisitionStatus\0", NULL);

    stream = dev->getStreams ();
    if (stream.size () > 0) {
      // opening first stream
      stream[0]->open ();
      stream[0]->startStreaming ();

      if (acquisitionMode != "Continuous" && triggerMode == "On") {
        if (triggerSource == "Software") {
          setTriggerSoftware ();
        } else {
          // validating the hw trigger timeout here, ensuring min value is 1 sec
          gencamParams->hwTriggerTimeout =
              (gencamParams->hwTriggerTimeout <=
              0) ? 10 : gencamParams->hwTriggerTimeout;
        }
      } else if (acquisitionMode == "Continuous" && triggerMode == "Off") {
        // Setting this to 0 in case user has configured it
        gencamParams->hwTriggerTimeout = 0;
      }
    }

  } else {
    GST_ERROR_OBJECT (gencamsrc, "Camera: %s not detected",
        gencamParams->deviceSerialNumber);
    return FALSE;
  }

  GST_DEBUG_OBJECT (gencamsrc, "END: %s", __func__);
  return TRUE;
}


bool
Genicam::Stop (void)
{
  GST_DEBUG_OBJECT (gencamsrc, "START: %s", __func__);
  try {
    // Stop and close the streams opened
    if (stream.size () > 0) {
      stream[0]->stopStreaming ();
      stream[0]->close ();
    }
    // Close the device opened
    if (dev) {
      dev->close ();
    }
  }
  catch (const std::exception & ex)
  {
    GST_WARNING_OBJECT (gencamsrc, "Exception: %s", ex.what ());
  } catch (const GENICAM_NAMESPACE::GenericException & ex)
  {
    GST_WARNING_OBJECT (gencamsrc, "Exception: %s", ex.what ());
  } catch ( ...) {
    GST_WARNING_OBJECT (gencamsrc, "Exception: unknown");
  }

  // Clear the system
  rcg::System::clearSystems ();

  GST_DEBUG_OBJECT (gencamsrc, "END: %s", __func__);
  return TRUE;
}


bool Genicam::Create (GstBuffer ** buf, GstMapInfo * mapInfo)
{
  /* Grab the buffer, copy and release, set framenum */
  int
      hwTriggerCheck = 0;
  GST_DEBUG_OBJECT (gencamsrc, "START: %s", __func__);
  try {
    const
        rcg::Buffer *
        buffer;

  // not necessary as it is taken care of at init time and this doesn't make a difference, 
  // but present on safer side: disabling unlimited license every frame for Balluff from DLStreamer Pipeline Server v2.2.0 onwards
  unsetenv("BALLUFF_ACQ_LIC_MODULE");

    while (!(buffer = stream[0]->grab (GRAB_DELAY * 1000))) {
      if (acquisitionMode != "Continuous" && triggerMode == "On"
          && triggerSource != "Software") {
        // If Hw trigger, wait for specified timeout
        int
            tLeft =
            (gencamParams->hwTriggerTimeout - ++hwTriggerCheck) * GRAB_DELAY;
        GST_INFO_OBJECT (gencamsrc, "Waiting %d more seconds for trigger..",
            tLeft);
      }
      if (hwTriggerCheck == gencamParams->hwTriggerTimeout) {
        GST_ERROR_OBJECT (gencamsrc, "No frame received from the camera");
        return FALSE;
      }
    }
    guint
        globalSize = buffer->getGlobalSize ();
    guint64
        timestampNS = buffer->getTimestampNS ();

    *buf = gst_buffer_new_allocate (NULL, globalSize, NULL);
    if (*buf == NULL) {
      GST_ERROR_OBJECT (gencamsrc, "Buffer couldn't be allocated");
      return FALSE;
    }
    GST_BUFFER_PTS (*buf) = timestampNS;
    gst_buffer_map (*buf, mapInfo, GST_MAP_WRITE);

    memcpy (mapInfo->data, buffer->getGlobalBase (), mapInfo->size);

    // For Non continuous modes, execute TriggerSoftware command
    if (acquisitionMode != "Continuous") {
      stream[0]->stopStreaming ();
      stream[0]->startStreaming ();

      // TODO handle multi frame, needs separate frame count for that
      if (triggerMode == "On" && triggerSource == "Software") {
        // If "AcquisitionStatus" feature is present, check the status
        while (!(rcg::getBoolean (nodemap, "AcquisitionStatus", false, false))
            && isAcquisitionStatusFeature);
        setTriggerSoftware ();
      }
    }
    GST_DEBUG_OBJECT (gencamsrc, "END: %s", __func__);
    return TRUE;
  }

  catch (const std::exception & ex) {
    GST_ERROR_OBJECT (gencamsrc, "Exception: %s", ex.what ());
    return FALSE;
  }
  catch (const GENICAM_NAMESPACE::GenericException & ex) {
    GST_ERROR_OBJECT (gencamsrc, "Exception: %s", ex.what ());
    return FALSE;
  }
  catch ( ...) {
    GST_ERROR_OBJECT (gencamsrc, "Exception: unknown");
    return FALSE;
  }

  return FALSE;
}


bool
Genicam::isFeature (const char *featureName, featureType * fType)
{
  bool ret = true;
  char featureStr[32] = "Feature not found\0";
  char typeStr[MAX_TYPE][32] = { "\0",  // NO_TYPE
    "Feature not enumeration\0",        // TYPE_ENUM
    "Feature not integer\0",    // TYPE_INT
    "Feature not float\0",      // TYPE_FLOAT
    "Feature not boolean\0",    // TYPE_BOOL
    "Feature of unknown datatype\0",    // TYPE_STRING
    "\0"
  };

  if (fType != NULL)
    *fType = TYPE_NO;

  try {
    if (fType != NULL)
      *fType = TYPE_ENUM;
    rcg::getEnum (nodemap, featureName, true);
  }
  catch (const std::exception & ex)
  {
    if (strncmp (ex.what (), featureStr, strlen (featureStr)) == 0) {
      // if feature not present, then no need to check rest just return
      ret = false;
      if (fType != NULL)
        *fType = TYPE_NO;
      return ret;
    }
    if (strncmp (ex.what (), typeStr[TYPE_ENUM],
            strlen (typeStr[TYPE_ENUM])) == 0) {
      if (fType != NULL)
        *fType = TYPE_NO;
    }
  }
  if (fType && *fType != TYPE_NO) {
    // return as type found
    return ret;
  } else if (fType == NULL) {
    // only feature existence needs to be checked.
    // Feature type can be ignored, so return
    return ret;
  }

  /* Check if feature is not a Integer */
  try {
    if (fType != NULL)
      *fType = TYPE_INT;
    rcg::getInteger (nodemap, featureName, NULL, NULL, true, false);
  }
  catch (const std::exception & ex)
  {
    if (strncmp (ex.what (), typeStr[TYPE_INT],
            strlen (typeStr[TYPE_INT])) == 0) {
      if (fType != NULL)
        *fType = TYPE_NO;
    }
  }
  if (fType && *fType != TYPE_NO) {
    // return as type found
    return ret;
  }

  /* Check if feature is not a float */
  try {
    if (fType != NULL)
      *fType = TYPE_FLOAT;
    rcg::getFloat (nodemap, featureName, NULL, NULL, true, false);
  }
  catch (const std::exception & ex)
  {
    if (strncmp (ex.what (), typeStr[TYPE_FLOAT],
            strlen (typeStr[TYPE_FLOAT])) == 0) {
      if (fType != NULL)
        *fType = TYPE_NO;
    }
  }
  if (fType && *fType != TYPE_NO) {
    // return as type found
    return ret;
  }

  /* Check if feature is not a boolean */
  try {
    if (fType != NULL)
      *fType = TYPE_BOOL;
    rcg::getBoolean (nodemap, featureName, true, false);
  }
  catch (const std::exception & ex)
  {
    if (strncmp (ex.what (), typeStr[TYPE_BOOL],
            strlen (typeStr[TYPE_BOOL])) == 0) {
      if (fType != NULL)
        *fType = TYPE_NO;
    }
  }
  if (fType && *fType != TYPE_NO) {
    // return as type found
    return ret;
  }

  /* Check if feature is not a string */
  try {
    if (fType != NULL)
      *fType = TYPE_STRING;
    rcg::getString (nodemap, featureName, true, false);
  }
  catch (const std::exception & ex)
  {
    if (strncmp (ex.what (), typeStr[TYPE_STRING],
            strlen (typeStr[TYPE_STRING])) == 0) {
      if (fType != NULL)
        *fType = TYPE_NO;
    }
  }
  if (fType && *fType == TYPE_NO) {
    // Only option left is CMD type
    *fType = TYPE_CMD;
  }

  return ret;
}

bool
Genicam::setEnumFeature (const char *featureName, const char *str,
    const bool ex)
{
  bool isEnumFeatureSet = false, matchFound = false;
  std::vector < std::string > featureList;

  if (featureName == NULL || str == NULL) {
    GST_ERROR_OBJECT (gencamsrc, "Enter valid feature and mode");
    return isEnumFeatureSet;
  }
  try {
    // Read the featureName supported
    rcg::getEnum (nodemap, featureName, featureList, ex);

    // Check if list is empty
    if (featureList.size () == 0) {
      GST_WARNING_OBJECT (gencamsrc, "%s: list empty, writing not supported",
          featureName);
      return isEnumFeatureSet;
    }

    for (size_t k = 0; k < featureList.size (); k++) {
      // Iterate all possible values if it matches
      if (strcasecmp (str, featureList[k].c_str ()) == 0) {
        matchFound = true;
        isEnumFeatureSet =
            rcg::setEnum (nodemap, featureName, featureList[k].c_str (), ex);
        break;
      }
    }
  }
  catch (const std::exception & ex)
  {
    GST_WARNING_OBJECT (gencamsrc, "Exception: %s", ex.what ());
  } catch ( ...) {
    GST_WARNING_OBJECT (gencamsrc, "Exception: unknown");
  }

  if (!matchFound) {
    // User parameter did not match
    GST_WARNING_OBJECT (gencamsrc, "%s: Invalid mode \"%s\".", featureName,
        str);
    GST_INFO_OBJECT (gencamsrc, "Supported list below:");
    for (size_t k = 0; k < featureList.size (); k++) {
      GST_INFO_OBJECT (gencamsrc, "    %s", featureList[k].c_str ());
    }
    GST_WARNING_OBJECT (gencamsrc, "  %s is \"%s\"", featureName,
        rcg::getEnum (nodemap, featureName, false).c_str ());
  } else if (matchFound && !isEnumFeatureSet) {
    // Command failed
    std::string featureStr = rcg::getEnum (nodemap, featureName, false);
    GST_WARNING_OBJECT (gencamsrc, "%s: %s set failed. Current mode %s",
        featureName, str, featureStr.c_str ());
  } else {
    // Command passed
    std::string featureStr = rcg::getEnum (nodemap, featureName, false);
    GST_INFO_OBJECT (gencamsrc, "%s: \"%s\" set successful.", featureName,
        featureStr.c_str ());
  }

  return isEnumFeatureSet;
}


bool
Genicam::setIntFeature (const char *featureName, int *val, const bool ex)
{
  bool isIntFeatureSet = false;
  int64_t vMin, vMax, vInc;
  int64_t diff;

  rcg::getInteger (nodemap, featureName, &vMin, &vMax, &vInc, false, false);

  if (vInc == 0) {
    vInc = 1;
  }

  /* Value of integer should be aligned such that difference of value and Min
   * should be a factor of vInc
   */
  if (*val > vMin) {
    diff = *val - vMin;
    *val -= (diff % vInc);
  }
  // check Range and cap it if needed
  if (*val < vMin) {
    GST_WARNING_OBJECT (gencamsrc, "%s: value %d capping near minimum %ld",
        featureName, *val, vMin);
    // Increase the value to vMin so that  "value-vMin" is a factor of "vInc".
    *val = vMin;
  } else if (*val > vMax) {
    GST_WARNING_OBJECT (gencamsrc, "%s: value %d capping near maximum %ld",
        featureName, *val, vMax);
    // Decrease the value if difference between "value-vMin" is not a factor of "vInc".
    diff = vMax - vMin;
    *val = vMax - (diff % vInc);
  }
  // Configure Int feature
  try {
    isIntFeatureSet = rcg::setInteger (nodemap, featureName, *val, ex);
  }
  catch (const std::exception & ex)
  {
    GST_WARNING_OBJECT (gencamsrc, "Exception: %s", ex.what ());
  }

  if (!isIntFeatureSet) {
    // Command failed
    int ret = rcg::getInteger (nodemap, featureName, NULL, NULL, false, false);
    GST_WARNING_OBJECT (gencamsrc, "%s: %d set failed. Current value is %d",
        featureName, *val, ret);
  } else {
    // Command passed
    int ret = rcg::getInteger (nodemap, featureName, NULL, NULL, false, false);
    GST_INFO_OBJECT (gencamsrc, "%s: %d set successful.", featureName, ret);
  }

  return isIntFeatureSet;
}


bool
Genicam::setFloatFeature (const char *featureName, float *val, const bool ex)
{
  bool isFloatFeatureSet = false;
  double vMin, vMax;

  rcg::getFloat (nodemap, featureName, &vMin, &vMax, false, false);

  // check Range and cap it if needed
  if (*val < vMin) {
    GST_WARNING_OBJECT (gencamsrc, "%s: value %f capping near minimum %lf",
        featureName, *val, vMin);
    *val = vMin;
  } else if (*val > vMax) {
    GST_WARNING_OBJECT (gencamsrc, "%s: value %f capping near maximum %lf",
        featureName, *val, vMax);
    *val = vMax;
  }
  // Configure Float feature
  try {
    isFloatFeatureSet = rcg::setFloat (nodemap, featureName, *val, ex);
  }
  catch (const std::exception & ex)
  {
    GST_WARNING_OBJECT (gencamsrc, "Exception: %s", ex.what ());;
  }

  if (!isFloatFeatureSet) {
    // Command failed
    float ret = rcg::getFloat (nodemap, featureName, NULL, NULL, false, false);
    GST_WARNING_OBJECT (gencamsrc, "%s: %f set failed. Current value is %f",
        featureName, *val, ret);
  } else {
    // Command passed
    float ret = rcg::getFloat (nodemap, featureName, NULL, NULL, false, false);
    GST_INFO_OBJECT (gencamsrc, "%s: %f set successful.", featureName, ret);
  }

  return isFloatFeatureSet;
}


void
Genicam::getCameraInfo (void)
{
  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);

  if (isFeature ("DeviceVendorName\0", NULL)) {
    camInfo.vendorName = rcg::getString (nodemap, "DeviceVendorName", 0, 0);
    GST_INFO_OBJECT (gencamsrc, "Camera Vendor: %s",
        camInfo.vendorName.c_str ());
  }
  if (isFeature ("DeviceModelName\0", NULL)) {
    camInfo.modelName = rcg::getString (nodemap, "DeviceModelName", 0, 0);
    GST_INFO_OBJECT (gencamsrc, "Camera Model: %s", camInfo.modelName.c_str ());
  }

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
}


bool
Genicam::getCameraSerialNumber (void)
{
  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);

  // get all systems
  std::vector < std::shared_ptr < rcg::System > >system =
      rcg::System::getSystems ();

  for (size_t i = 0; i < system.size (); i++) {
    // Open systems, and get all interfaces
    system[i]->open ();
    std::vector < std::shared_ptr < rcg::Interface > >interf =
        system[i]->getInterfaces ();
    for (size_t k = 0; k < interf.size (); k++) {
      // Open interfaces, and get all cameras
      interf[k]->open ();
      std::vector < std::shared_ptr < rcg::Device > >device =
          interf[k]->getDevices ();
      for (size_t j = 0; j < device.size (); j++) {
        // Check for duplicate serials
        bool match = std::find (serials.begin (), serials.end (),
            device[j]->getSerialNumber ()) != serials.end ();
        if (!match) {
          serials.push_back (device[j]->getSerialNumber ());
          GST_INFO_OBJECT (gencamsrc, "> Camera found with Serial# %s",
              device[j]->getSerialNumber ().c_str ());
        }
      }
      // Close interfaces
      interf[k]->close ();
    }
    // Close systems
    system[i]->close ();
  }

  if (serials.size () == 0) {
    // No cameras found
    GST_ERROR_OBJECT (gencamsrc, "No Cameras found.");
  } else {
    // Connect to the first camera found
    GST_INFO_OBJECT (gencamsrc, "Connecting to camera: %s",
        serials[0].c_str ());
    gencamParams->deviceSerialNumber = serials[0].c_str ();
  }

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);

  return (!serials.empty ());
}


bool
Genicam::resetDevice (void)
{
  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);

  // WARNING:: Do not modify unless absolutely sure
  rcg::callCommand (nodemap, "DeviceReset", true);

  // Device will poweroff immediately
  GST_INFO_OBJECT (gencamsrc, "DeviceReset: %d triggered",
      gencamParams->deviceReset);
  GST_INFO_OBJECT (gencamsrc,
      "Device will take a few seconds to reset to factory default");

  // Stop gracefully if poweroff taking time
  Stop ();

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return FALSE;
}


bool
Genicam::setBinningSelector (void)
{
  bool isBinningSelectorSet = false;

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);

  //Possible values : Sensor, Region0, Region1, Region2
  isBinningSelectorSet =
      setEnumFeature ("BinningSelector\0", gencamParams->binningSelector, true);

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);

  return isBinningSelectorSet;
}


bool
Genicam::setBinningHorizontalMode (void)
{
  bool isBinningHorizontalModeSet = false;

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);

  std::vector < std::string > binningHorizontalModes;

  // Read binning engines supported by the camera
  rcg::getEnum (nodemap, "BinningHorizontalMode", binningHorizontalModes,
      false);
  if (binningHorizontalModes.empty ()) {
    // Handle variations, deviations from SFNC standard
    rcg::getEnum (nodemap, "BinningModeHorizontal", binningHorizontalModes,
        false);
  }
  // Iterate the configured binning horizontal mode with camera supported list
  if (strcasecmp (gencamParams->binningHorizontalMode, "sum") == 0) {
    // Sum binning horizontal mode is supported?
    for (size_t k = 0; k < binningHorizontalModes.size (); k++) {
      // Summing is a deviation but some cameras use
      if ((binningHorizontalModes[k] == "Sum") ||
          (binningHorizontalModes[k] == "Summing")) {
        isBinningHorizontalModeSet =
            rcg::setEnum (nodemap, "BinningHorizontalMode",
            binningHorizontalModes[k].c_str (), false);
        if (!isBinningHorizontalModeSet) {
          // Deviation from SFNC, handle it
          isBinningHorizontalModeSet =
              rcg::setEnum (nodemap, "BinningModeHorizontal",
              binningHorizontalModes[k].c_str (), false);
        }
        break;
      }
    }

  } else if (strcasecmp (gencamParams->binningHorizontalMode, "average") == 0) {
    // Average binning horizontal mode is supported?
    for (size_t k = 0; k < binningHorizontalModes.size (); k++) {
      // Averaging is a deviation but some cameras use
      if ((binningHorizontalModes[k] == "Average") ||
          (binningHorizontalModes[k] == "Averaging")) {
        isBinningHorizontalModeSet =
            rcg::setEnum (nodemap, "BinningHorizontalMode",
            binningHorizontalModes[k].c_str (), false);
        if (!isBinningHorizontalModeSet) {
          // Deviation from SFNC, handle it
          isBinningHorizontalModeSet =
              rcg::setEnum (nodemap, "BinningModeHorizontal",
              binningHorizontalModes[k].c_str (), false);
        }
        break;
      }
    }

  } else {
    GST_WARNING_OBJECT (gencamsrc, "Invalid BinningHorizontalMode: %s",
        gencamParams->binningHorizontalMode);
    return FALSE;
  }


  if (isBinningHorizontalModeSet) {
    // Binning Horizontal Mode set success
    GST_INFO_OBJECT (gencamsrc, "BinningHorizontalMode: \"%s\" set successful.",
        gencamParams->binningHorizontalMode);
  } else {
    // Binning horizontal modes not supported by the camera
    GST_WARNING_OBJECT (gencamsrc,
        "BinningHorizontalMode: Invalid mode \"%s\".",
        gencamParams->binningHorizontalMode);
    if (binningHorizontalModes.size () > 0) {
      GST_INFO_OBJECT (gencamsrc, "Supported binning horizontal modes are,");
      for (size_t k = 0; k < binningHorizontalModes.size (); k++) {
        GST_INFO_OBJECT (gencamsrc, "    %s",
            binningHorizontalModes[k].c_str ());
      }
    } else {
      GST_WARNING_OBJECT (gencamsrc, "Feature not supported");
    }
  }

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);

  return TRUE;
}


bool
Genicam::setBinningHorizontal (void)
{
  bool ret = false;
  int64_t vMin, vMax;

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);
  if (rcg::getInteger (nodemap, "BinningHorizontal", &vMin, &vMax, false, true)) {
    ret =
        setIntFeature ("BinningHorizontal\0", &gencamParams->binningHorizontal,
        false);
  }

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return ret;
}


bool
Genicam::setBinningVerticalMode (void)
{
  bool isBinningVerticalModeSet = false;

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);

  std::vector < std::string > binningVerticalModes;

  // Read binning engines supported by the camera
  rcg::getEnum (nodemap, "BinningVerticalMode", binningVerticalModes, false);
  if (binningVerticalModes.empty ()) {
    // Handle deviations from SFNC standard
    rcg::getEnum (nodemap, "BinningModeVertical", binningVerticalModes, false);
  }
  // Iterate the configured binning vertical mode with camera supported list
  if (strcasecmp (gencamParams->binningVerticalMode, "sum") == 0) {
    // Sum binning vertical mode is supported?
    for (size_t k = 0; k < binningVerticalModes.size (); k++) {
      if ((binningVerticalModes[k] == "Sum") ||
          (binningVerticalModes[k] == "Summing")) {
        isBinningVerticalModeSet =
            rcg::setEnum (nodemap, "BinningVerticalMode",
            binningVerticalModes[k].c_str (), false);
        if (!isBinningVerticalModeSet) {
          // Deviation from SFNC, handle it
          isBinningVerticalModeSet =
              rcg::setEnum (nodemap, "BinningModeVertical",
              binningVerticalModes[k].c_str (), false);
        }
        break;
      }
    }

  } else if (strcasecmp (gencamParams->binningVerticalMode, "average") == 0) {
    // Average binning vertical mode is supported?
    for (size_t k = 0; k < binningVerticalModes.size (); k++) {
      if ((binningVerticalModes[k] == "Average") ||
          (binningVerticalModes[k] == "Averaging")) {
        isBinningVerticalModeSet =
            rcg::setEnum (nodemap, "BinningVerticalMode",
            binningVerticalModes[k].c_str (), false);
        if (!isBinningVerticalModeSet) {
          // Deviation from SFNC, handle it
          isBinningVerticalModeSet =
              rcg::setEnum (nodemap, "BinningModeVertical",
              binningVerticalModes[k].c_str (), false);
        }
        break;
      }
    }

  } else {
    GST_WARNING_OBJECT (gencamsrc, "Invalid BinningVerticalMode: %s",
        gencamParams->binningVerticalMode);
    return FALSE;
  }

  if (isBinningVerticalModeSet) {
    // Binning Vertical Mode set success
    GST_INFO_OBJECT (gencamsrc, "BinningVerticalMode: \"%s\" set successful.",
        gencamParams->binningVerticalMode);
  } else {
    // Binning vertical modes not supported by the camera
    GST_WARNING_OBJECT (gencamsrc, "BinningVerticalMode: Invalid mode \"%s\".",
        gencamParams->binningVerticalMode);
    if (binningVerticalModes.size () > 0) {
      GST_INFO_OBJECT (gencamsrc, "Supported binning vertical modes are,");
      for (size_t k = 0; k < binningVerticalModes.size (); k++) {
        GST_INFO_OBJECT (gencamsrc, "    %s", binningVerticalModes[k].c_str ());
      }
    } else {
      GST_WARNING_OBJECT (gencamsrc, "Feature not supported");
    }
  }

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return TRUE;
}


bool
Genicam::setBinningVertical (void)
{
  bool ret = false;
  int64_t vMin, vMax;

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);
  if (rcg::getInteger (nodemap, "BinningVertical", &vMin, &vMax, false, true)) {
    ret =
        setIntFeature ("BinningVertical\0", &gencamParams->binningVertical,
        false);
  }

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return ret;
}


bool
Genicam::setDecimationHorizontal (void)
{
  bool isDecimationHorizontalSet = false;

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);
  // Is DecimationHorizontal supported? if not then return
  if (!isFeature ("DecimationHorizontal\0", NULL)) {
    GST_WARNING_OBJECT (gencamsrc,
        "DecimationHorizontal: feature not supported");
    return isDecimationHorizontalSet;
  }
  // Configure Decimation
  isDecimationHorizontalSet =
      setIntFeature ("DecimationHorizontal\0",
      &gencamParams->decimationHorizontal, true);

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return isDecimationHorizontalSet;
}


bool
Genicam::setDecimationVertical (void)
{
  bool isDecimationVerticalSet = false;

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);
  // Is DecimationVertical supported? if not then return
  if (!isFeature ("DecimationVertical\0", NULL)) {
    GST_WARNING_OBJECT (gencamsrc, "DecimationVertical: feature not supported");
    return isDecimationVerticalSet;
  }
  // Configure Decimation
  isDecimationVerticalSet =
      setIntFeature ("DecimationVertical\0",
      &gencamParams->decimationVertical, true);

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return isDecimationVerticalSet;
}


bool
Genicam::setPixelFormat (void)
{
  bool isPixelFormatSet = false;
  std::vector < std::string > pixelFormats;

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);
  // Read the pixel formats supported by the camera
  rcg::getEnum (nodemap, "PixelFormat", pixelFormats, true);

  // Iterate the configured format with camera supported list
  // Mapping necessary from FOURCC to GenICam SFNC / PFNC

  if (strcasecmp (gencamParams->pixelFormat, "mono8") == 0) {
    // Check Mono8 / GRAY8 / Y8 is supported by the camera
    for (size_t k = 0; k < pixelFormats.size (); k++) {
      if (pixelFormats[k] == "Mono8") {
        rcg::setEnum (nodemap, "PixelFormat", pixelFormats[k].c_str (), true);
        isPixelFormatSet = true;
        break;
      }
    }

  } else if (strcasecmp (gencamParams->pixelFormat, "ycbcr411_8") == 0) {
    // I420 / YUV420 / YCbCr411 8 bit supported by the camera?
    for (size_t k = 0; k < pixelFormats.size (); k++) {
      if (pixelFormats[k] == "YCbCr411_8") {
        rcg::setEnum (nodemap, "PixelFormat", pixelFormats[k].c_str (), true);
        isPixelFormatSet = true;
        break;
      }
    }

  } else if (strcasecmp (gencamParams->pixelFormat, "ycbcr422_8") == 0) {
    // YUY2 / YUV422 / Ycbcr422 8 bit supported by the camera?
    for (size_t k = 0; k < pixelFormats.size (); k++) {
      if (pixelFormats[k] == "YUV422_8"
          || pixelFormats[k] == "YUV422_YUYV_Packed"
          || pixelFormats[k] == "YCbCr422_8") {
        rcg::setEnum (nodemap, "PixelFormat", pixelFormats[k].c_str (), true);
        isPixelFormatSet = true;
        break;
      }
    }

  } else if (strcasecmp (gencamParams->pixelFormat, "bayerbggr") == 0) {
    // BayerBG8 is supported by the camera?
    for (size_t k = 0; k < pixelFormats.size (); k++) {
      if (pixelFormats[k] == "BayerBG8") {
        rcg::setEnum (nodemap, "PixelFormat", pixelFormats[k].c_str (), true);
        isPixelFormatSet = true;
        break;
      }
    }

  } else if (strcasecmp (gencamParams->pixelFormat, "bayerrggb") == 0) {
    // BayerRG8 supported by the camera?
    for (size_t k = 0; k < pixelFormats.size (); k++) {
      if (pixelFormats[k] == "BayerRG8") {
        rcg::setEnum (nodemap, "PixelFormat", pixelFormats[k].c_str (), true);
        isPixelFormatSet = true;
        break;
      }
    }

  } else if (strcasecmp (gencamParams->pixelFormat, "bayergrbg") == 0) {
    // BayerBG8 supported by the camera?
    for (size_t k = 0; k < pixelFormats.size (); k++) {
      if (pixelFormats[k] == "BayerGR8") {
        rcg::setEnum (nodemap, "PixelFormat", pixelFormats[k].c_str (), true);
        isPixelFormatSet = true;
        break;
      }
    }

  } else if (strcasecmp (gencamParams->pixelFormat, "bayergbrg") == 0) {
    // BayerGB8 supported by the camera?
    for (size_t k = 0; k < pixelFormats.size (); k++) {
      if (pixelFormats[k] == "BayerGB8") {
        rcg::setEnum (nodemap, "PixelFormat", pixelFormats[k].c_str (), true);
        isPixelFormatSet = true;
        break;
      }
    }

  } else if (strcasecmp (gencamParams->pixelFormat, "rgb8") == 0) {
    // RGB8, 24 bit supported by the camera?
    for (size_t k = 0; k < pixelFormats.size (); k++) {
      if (pixelFormats[k] == "RGB8" || pixelFormats[k] == "RGB8Packed") {
        rcg::setEnum (nodemap, "PixelFormat", pixelFormats[k].c_str (), true);
        isPixelFormatSet = true;
        break;
      }
    }

  } else if (strcasecmp (gencamParams->pixelFormat, "bgr8") == 0) {
    // BGR8, 24 bit supported by the camera?
    for (size_t k = 0; k < pixelFormats.size (); k++) {
      if (pixelFormats[k] == "BGR8" || pixelFormats[k] == "BGR8Packed") {
        rcg::setEnum (nodemap, "PixelFormat", pixelFormats[k].c_str (), true);
        isPixelFormatSet = true;
        break;
      }
    }
  }

  if (isPixelFormatSet) {
    // Format set success
    GST_INFO_OBJECT (gencamsrc, "PixelFormat: \"%s\" set successful.",
        rcg::getEnum (nodemap, "PixelFormat", false).c_str ());
    if (isFeature ("PixelSize\0", NULL)) {
      GST_INFO_OBJECT (gencamsrc, "PixelSize: \"%s\" set successful.",
          rcg::getEnum (nodemap, "PixelSize", false).c_str ());
    }
  } else {
    // Format is not supported by the camera, terminate
    GST_WARNING_OBJECT (gencamsrc,
        "PixelFormat: \"%s\" not supported by the camera",
        gencamParams->pixelFormat);
    GST_INFO_OBJECT (gencamsrc, "Pixel formats supported are below,");
    for (size_t k = 0; k < pixelFormats.size (); k++) {
      GST_INFO_OBJECT (gencamsrc, "    %s", pixelFormats[k].c_str ());
    }
    Stop ();
    return FALSE;
  }

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return TRUE;
}


bool
Genicam::setWidthHeight (void)
{
  int64_t vMinX, vMaxX;
  int64_t vMinY, vMaxY;
  char str[32] = "Feature not writable";
  bool isWidthHeightSet = false;

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);
  // Write Offsets = 0, so that resolution can be set first smoothly
  // Offsets will be configured later
  // Also, check if offset is a writable feature. If not, ignore setting it later
  try {
    offsetXYwritable = true;
    rcg::setInteger (nodemap, "OffsetX", 0, true);
    rcg::setInteger (nodemap, "OffsetY", 0, true);
  } catch (const std::exception & ex)
  {
    // Feature not writable
    if (strncmp (ex.what (), str, strlen (str)) == 0) {
      offsetXYwritable = false;
      GST_WARNING_OBJECT (gencamsrc, "OffsetX and OffsetY not writable");
    }
  }

  // Print Max resolution supported by camera
  widthMax = rcg::getInteger (nodemap, "WidthMax", NULL, NULL, false, 0);
  heightMax = rcg::getInteger (nodemap, "HeightMax", NULL, NULL, false, 0);

  GST_INFO_OBJECT (gencamsrc, "Maximum resolution supported by Camera: %d x %d",
      widthMax, heightMax);

  // Maximum Width check
  rcg::getInteger (nodemap, "Width", &vMinX, &vMaxX, false, false);
  if (gencamParams->width > vMaxX) {
    // Align the width to 4
    gencamParams->width = ROUNDED_DOWN (vMaxX, 0x4 - 1);
    GST_WARNING_OBJECT (gencamsrc, "Width: capping to maximum %d",
        gencamParams->width);
  }
  // Maximum Height check
  rcg::getInteger (nodemap, "Height", &vMinY, &vMaxY, false, false);
  if (gencamParams->height > vMaxY) {
    // Align the height to 4
    gencamParams->height = ROUNDED_DOWN (vMaxY, 0x4 - 1);
    GST_WARNING_OBJECT (gencamsrc, "Height: capping to maximum %d",
        gencamParams->height);
  }

  isWidthHeightSet =
      rcg::setInteger (nodemap, "Width", gencamParams->width, true);
  isWidthHeightSet |=
      rcg::setInteger (nodemap, "Height", gencamParams->height, true);

  if (isWidthHeightSet) {
    GST_INFO_OBJECT (gencamsrc, "Current resolution: %ld x %ld",
        rcg::getInteger (nodemap, "Width", NULL, NULL, false, true),
        rcg::getInteger (nodemap, "Height", NULL, NULL, false, true));
  } else {
    GST_ERROR_OBJECT (gencamsrc, "Width and Height set error");
    Stop ();
  }

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return isWidthHeightSet;
}


bool
Genicam::setOffsetXY (void)
{
  bool isOffsetXYset = false;

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);
  isOffsetXYset = setIntFeature ("OffsetX\0", &gencamParams->offsetX, true);
  isOffsetXYset |= setIntFeature ("OffsetY\0", &gencamParams->offsetY, true);

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return isOffsetXYset;
}


bool
Genicam::setAcquisitionFrameRate (void)
{
  // AcquisitionFrameRateEnable and AcquisitionFrameRate feature
  bool isFrameRateSet = false;
  float frameRate;
  double vMin, vMax;
  char frameRateString[32];

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);
  if (isFeature ("AcquisitionFrameRate\0", NULL)) {
    strncpy (frameRateString, "AcquisitionFrameRate\0",
        sizeof ("AcquisitionFrameRate\0"));
  } else if (isFeature ("AcquisitionFrameRateAbs\0", NULL)) {
    strncpy (frameRateString, "AcquisitionFrameRateAbs\0",
        sizeof ("AcquisitionFrameRateAbs\0"));
  } else {
    GST_WARNING_OBJECT (gencamsrc,
        "AcquisitionFrameRate: feature not supported");
  }

  frameRate =
      rcg::getFloat (nodemap, frameRateString, &vMin, &vMax, false, false);

  // Incase of no input, read current framerate and set it again
  if (gencamParams->acquisitionFrameRate == 0) {
    gencamParams->acquisitionFrameRate = frameRate;
  }

  isFrameRateSet =
      (rcg::setBoolean (nodemap, "AcquisitionFrameRateEnable", 1, false)
      || rcg::setBoolean (nodemap, "AcquisitionFrameRateEnabled", 1, false));

  if (!isFrameRateSet) {
    gencamParams->acquisitionFrameRate = frameRate;
    GST_WARNING_OBJECT (gencamsrc,
        "AcquisitionFrameRate not configurable, current FrameRate = %f",
        frameRate);
  } else {
    isFrameRateSet =
        setFloatFeature (frameRateString, &gencamParams->acquisitionFrameRate,
        true);
  }

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return isFrameRateSet;
}


bool
Genicam::setExposureMode (void)
{
  bool isExposureModeSet = false;
  double vMin, vMax, expTime;

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);
  (expTime =
      rcg::getFloat (nodemap, "ExposureTime", &vMin, &vMax, false,
          0)) ? expTime : rcg::getFloat (nodemap, "ExposureTimeAbs", &vMin,
      &vMax, false, 0);

  // Set the limits for Exposure Modes
  rcg::setFloat (nodemap, "AutoExposureTimeAbsLowerLimit", vMin, false);
  rcg::setFloat (nodemap, "AutoExposureTimeLowerLimit", vMin, false);
  rcg::setFloat (nodemap, "AutoExposureTimeAbsUpperLimit", vMax, false);
  rcg::setFloat (nodemap, "AutoExposureTimeUpperLimit", vMax, false);

  // Possible values: Off, Timed, TriggerWidth, TriggerControlled
  isExposureModeSet =
      setEnumFeature ("ExposureMode\0", gencamParams->exposureMode, false);

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return isExposureModeSet;
}


bool
Genicam::setExposureTime (void)
{
  bool isExposureTimeSet = false;
  char exposureTimeStr[32];

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);
  if (isFeature ("ExposureTime\0", NULL)) {
    strncpy (exposureTimeStr, "ExposureTime", sizeof ("ExposureTime\0"));
  } else if (isFeature ("ExposureTimeAbs\0", NULL)) {
    strncpy (exposureTimeStr, "ExposureTimeAbs", sizeof ("ExposureTimeAbs\0"));
  } else {
    GST_WARNING_OBJECT (gencamsrc, "ExposureTime: feature not supported");
    return isExposureTimeSet;
  }

  std::string exposureMode = rcg::getEnum (nodemap, "ExposureMode", false);
  std::string exposureAuto = rcg::getEnum (nodemap, "ExposureAuto", false);

  // Proceed only if ExposureMode = Timed and ExposureAuto = Off
  if (exposureMode != "Timed" || exposureAuto != "Off") {
    GST_WARNING_OBJECT (gencamsrc,
        "ExposureTime not set, exposureMode must be \"Timed\" and exposureAuto must be \"Off\"");
    return isExposureTimeSet;
  }

  isExposureTimeSet =
      setFloatFeature (exposureTimeStr, &gencamParams->exposureTime, false);

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return isExposureTimeSet;
}


bool
Genicam::setBlackLevelSelector (void)
{
  bool isBlackLevelSelectorSet = false;

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);
  // check if blackLevelSelector is present
  if (isFeature ("BlackLevelSelector\0", NULL) == false) {
    GST_WARNING_OBJECT (gencamsrc, "BlackLevelSelector: feature not supported");
    return isBlackLevelSelectorSet;
  }
  // Possible values: All, Red, Green, Blue, Y, U, V, Tap1, Tap2...
  isBlackLevelSelectorSet =
      setEnumFeature ("BlackLevelSelector\0", gencamParams->blackLevelSelector,
      false);

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return isBlackLevelSelectorSet;
}


bool
Genicam::setBlackLevelAuto (void)
{
  bool isBlackLevelAutoSet = false;

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);
  // check if blackLevelSelector is present
  if (!isFeature ("BlackLevelAuto\0", NULL)) {
    GST_WARNING_OBJECT (gencamsrc, "BlackLevelAuto: feature not supported");
    return isBlackLevelAutoSet;
  }
  // Possible values: Off, Once, Continuous
  isBlackLevelAutoSet =
      setEnumFeature ("BlackLevelAuto\0", gencamParams->blackLevelAuto, false);
  // if success, assigned value can be later checked in BlackLevel
  std::string str = rcg::getEnum (nodemap, "BlackLevelAuto", false);
  blackLevelAuto.assign (str);

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return isBlackLevelAutoSet;
}


bool
Genicam::setBlackLevel (void)
{
  bool isBlackLevelSet = false;
  char blackLevelStr[32];
  featureType fType = TYPE_NO, fTypeTemp;

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);
  // Proceed only if BlackLevelAuto is "Off"
  if ((isFeature ("BlackLevelAuto\0", NULL)) && (blackLevelAuto != "Off")
      && (blackLevelAuto != "")) {
    GST_WARNING_OBJECT (gencamsrc,
        "BlackLevel not set, BlackLevelAuto should be \"Off\"");
    return isBlackLevelSet;
  }
  // Enable the blacklevel enable bit in case if it is present
  if (isFeature ("BlackLevelEnabled\0", NULL)) {
    rcg::setBoolean (nodemap, "BlackLevelEnabled", 1, false);
  }
  // Check the feature string and if the feature is int or float
  if (isFeature ("BlackLevel\0", &fTypeTemp)) {
    strncpy (blackLevelStr, "BlackLevel\0", sizeof ("BlackLevel\0"));
    fType = fTypeTemp;
  } else if (isFeature ("BlackLevelRaw\0", &fTypeTemp)) {
    strncpy (blackLevelStr, "BlackLevelRaw\0", sizeof ("BlackLevelRaw\0"));
    fType = fTypeTemp;
  } else {
    // Feature not found return
    GST_WARNING_OBJECT (gencamsrc, "BlackLevel: feature not supported");
    return isBlackLevelSet;
  }

  // If the feature type is int
  if (fType == TYPE_INT) {
    isBlackLevelSet =
        setIntFeature (blackLevelStr, (int *) (&gencamParams->blackLevel),
        false);
  }
  // If the feature type is float
  if (fType == TYPE_FLOAT) {
    isBlackLevelSet =
        setFloatFeature (blackLevelStr, &gencamParams->blackLevel, false);
  }

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return isBlackLevelSet;
}


bool
Genicam::setGamma (void)
{
  bool isGammaSet = false;
  std::string gammaSelector;

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);
  // Check if Gamma feature is present
  if (!isFeature ("Gamma\0", NULL)) {
    GST_WARNING_OBJECT (gencamsrc, "Gamma: feature not supported");
    return isGammaSet;
  }
  // Set GammaSelector feature
  if (gencamParams->gammaSelector) {
    if (isFeature ("GammaSelector\0", NULL)) {
      // Possible valuse: sRGB, User
      setEnumFeature ("GammaSelector\0", gencamParams->gammaSelector, false);
    } else {
      // Feature not found, still don't return and try to set Gamma
      GST_WARNING_OBJECT (gencamsrc, "GammaSelector: feature not supported");
    }
  }
  // Enable Gamma Feature
  rcg::setBoolean (nodemap, "GammaEnable", 1, false);
  rcg::setBoolean (nodemap, "GammaEnabled", 1, false);

  // Set Gamma when GammaSelector is anyways not present or
  // if Gammaselector is present, and it's valie should be User
  gammaSelector = rcg::getEnum (nodemap, "GammaSelector", false);
  if (isFeature ("GammaSelector\0", NULL) && gammaSelector != "User") {
    GST_WARNING_OBJECT (gencamsrc,
        "Gamma set failed because GammaSelector is not \"User\"");
    return isGammaSet;
  }
  // Set the feature
  isGammaSet = setFloatFeature ("Gamma\0", &gencamParams->gamma, false);

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return isGammaSet;
}

bool
Genicam::setBalanceRatio (void)
{
  bool isBalanceRatioSet = false;
  double vMin, vMax;
  char balanceRatioStr[32];

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);

  // Set BalanceRatioSelector feature
  if (!isFeature ("BalanceRatioSelector\0", NULL)) {
    // Don't return, still set the BalanceRatio if present
    GST_WARNING_OBJECT (gencamsrc,
        "BalanceRatioSelector: feature not supported");
  } else {
    if (gencamParams->balanceRatioSelector) {
      // Possible values: All, Red, Green, Blue, Y, U, V, Tap1, Tap2...
      setEnumFeature ("BalanceRatioSelector\0",
          gencamParams->balanceRatioSelector, false);
    }
  }

  // No need to configure balance ratio, return
  if (gencamParams->balanceRatio == 9999.0) {
    return isBalanceRatioSet;
  }
  // Check the feature string if it exists or not
  if (isFeature ("BalanceRatio\0", NULL)) {
    strncpy (balanceRatioStr, "BalanceRatio\0", sizeof ("BalanceRatio\0"));
  } else if (isFeature ("BalanceRatioAbs\0", NULL)) {
    strncpy (balanceRatioStr, "BalanceRatioAbs\0",
        sizeof ("BalanceRatioAbs\0"));
  } else {
    // Feature does not exist
    GST_WARNING_OBJECT (gencamsrc, "BalanceRatio: feature not supported");
    return isBalanceRatioSet;
  }

  // Check if Auto White Balance is "Off", if not then return
  std::string balanceWhiteAuto =
      rcg::getEnum (nodemap, "BalanceWhiteAuto", false);
  if (balanceWhiteAuto != "Off") {
    GST_WARNING_OBJECT (gencamsrc,
        "Ignore setting \"BalanceRatio\" as \"BalanceWhiteAuto\" not \"Off\"");
    return isBalanceRatioSet;
  }
  // Set the BalanceRatio feature
  // Track min and max value
  rcg::getFloat (nodemap, balanceRatioStr, &vMin, &vMax, false, 0);
  if (gencamParams->balanceRatio < vMin) {
    GST_WARNING_OBJECT (gencamsrc, "BalanceRatio: capping to minimum %lf",
        vMin);
    gencamParams->balanceRatio = vMin;
  } else if (gencamParams->balanceRatio > vMax) {
    GST_WARNING_OBJECT (gencamsrc, "BalanceRatio: capping to maximum %lf",
        vMax);
    gencamParams->balanceRatio = vMax;
  }

  isBalanceRatioSet =
      rcg::setFloat (nodemap, balanceRatioStr, gencamParams->balanceRatio,
      false);

  // Failed to set the feature
  if (!isBalanceRatioSet) {
    GST_WARNING_OBJECT (gencamsrc, "BalanceRatio: %f set failed.",
        gencamParams->balanceRatio);
  } else {
    std::string balanceRatioSelector =
        rcg::getEnum (nodemap, "BalanceRatioSelector", false);
    GST_INFO_OBJECT (gencamsrc, "BalanceRatio[%s]: %f set successful.",
        balanceRatioSelector.c_str (), gencamParams->balanceRatio);
  }

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return isBalanceRatioSet;
}

bool
Genicam::setBalanceWhiteAuto (void)
{
  bool isBalanceWhiteAutoSet = false;

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);
  // check if BalanceWhiteAuto is present
  if (isFeature ("BalanceWhiteAuto\0", NULL) == false) {
    GST_WARNING_OBJECT (gencamsrc, "BalanceWhiteAuto: feature not supported");
    return isBalanceWhiteAutoSet;
  }
  // Possible values: Off, Once, Continuous
  isBalanceWhiteAutoSet =
      setEnumFeature ("BalanceWhiteAuto\0", gencamParams->balanceWhiteAuto,
      false);

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return isBalanceWhiteAutoSet;
}


bool
Genicam::setExposureAuto (void)
{
  bool isExposureAutoSet = false;

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);
  // check if ExposureAuto is present
  if (isFeature ("ExposureAuto\0", NULL) == false) {
    GST_WARNING_OBJECT (gencamsrc, "ExposureAuto: feature not supported");
    return isExposureAutoSet;
  }
  // Possible values: Off, Once, Continuous
  isExposureAutoSet =
      setEnumFeature ("ExposureAuto\0", gencamParams->exposureAuto, false);

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return isExposureAutoSet;
}


bool
Genicam::setExposureTimeSelector (void)
{
  bool isExposureTimeSelectorSet = false;

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);
  // Check if ExposureTimeSelector feature is present.
  if (!isFeature ("ExposureTimeSelector\0", NULL)) {
    GST_WARNING_OBJECT (gencamsrc,
        "ExposureTimeSelector: feature not Supported");
    return isExposureTimeSelectorSet;
  }

  /* exposure time selector should be set in conjuction with
     exposure time mode. If common both should be common.
     For others, time mode should be individual */
  if (strcasecmp (gencamParams->exposureTimeSelector, "Common") == 0) {
    GST_INFO_OBJECT (gencamsrc, "Setting ExposureTimeSelector to \"Common\"");
    rcg::setEnum (nodemap, "ExposureTimeMode", "Common", false);
  } else {
    GST_INFO_OBJECT (gencamsrc,
        "Setting ExposureTimeSelector to \"Individual\"");
    rcg::setEnum (nodemap, "ExposureTimeMode", "Individual", false);
  }

  isExposureTimeSelectorSet =
      setEnumFeature ("ExposureTimeSelector\0",
      gencamParams->exposureTimeSelector, false);

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return isExposureTimeSelectorSet;
}


bool
Genicam::setGainSelector (void)
{
  bool isGainSelectorSet = false;

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);
  // Check if GainSelector feature is present.
  if (!isFeature ("GainSelector\0", NULL)) {
    GST_WARNING_OBJECT (gencamsrc, "GainSelector: feature not supported");
    return isGainSelectorSet;
  }

  isGainSelectorSet =
      setEnumFeature ("GainSelector\0", gencamParams->gainSelector, true);

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return isGainSelectorSet;
}


bool
Genicam::setGain (void)
{
  bool isGainSet = false, isFloat = true;
  double vMin, vMax, gain;
  int64_t vMinInt, vMaxInt, gainInt;

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);
  // Proceed only if GainAuto is "Off"
  if ((isFeature ("GainAuto\0", NULL)) && (gainAuto != "Off")
      && (gainAuto != "")) {
    GST_WARNING_OBJECT (gencamsrc, "Gain not set, GainAuto should be \"Off\"");
    return isGainSet;
  }
  gain = rcg::getFloat (nodemap, "Gain", &vMin, &vMax, false);
  if (!gain && !vMin && !vMax) {
    // Either feature not supported or deviation from standard
    // Let's check if deviation
    gainInt = rcg::getInteger (nodemap, "GainRaw", &vMinInt, &vMaxInt, false);
    if (!gainInt && !vMinInt && !vMaxInt) {
      GST_WARNING_OBJECT (gencamsrc, "Gain: feature not supported");
      return isGainSet;
    }
    // Deviation it is, It's gain raw instead of gain and int instead of float
    isFloat = false;
  }

  if (isFloat) {
    isGainSet = setFloatFeature ("Gain\0", &gencamParams->gain, false);
  } else {
    int gainTemp = (int) gencamParams->gain;

    isGainSet = setIntFeature ("GainRaw\0", &gainTemp, false);
    gencamParams->gain = (float) gainTemp;
  }

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return isGainSet;
}


bool
Genicam::setGainAuto (void)
{
  bool isGainAutoSet = false;

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);
  // check if feature is present
  if (!isFeature ("GainAuto\0", NULL)) {
    GST_WARNING_OBJECT (gencamsrc, "GainAuto: feature not supported");
    return isGainAutoSet;
  }
  //Possible values: Off, Once, Continuous
  isGainAutoSet = setEnumFeature ("GainAuto\0", gencamParams->gainAuto, false);
  std::string str = rcg::getEnum (nodemap, "GainAuto", false);
  gainAuto.assign (str);

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return isGainAutoSet;
}


bool
Genicam::setGainAutoBalance (void)
{
  bool isGainAutoBalanceSet = false;

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);
  // Check if feature not supported
  if (!isFeature ("GainAutoBalance\0", NULL)) {
    GST_WARNING_OBJECT (gencamsrc, "GainAutoBalance: feature not supported");
    return isGainAutoBalanceSet;
  }
  // Possible values: Off, Once, Continuous
  isGainAutoBalanceSet =
      setEnumFeature ("GainAutoBalance\0", gencamParams->gainAutoBalance,
      false);

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return isGainAutoBalanceSet;
}


bool
Genicam::setTriggerDivider (void)
{
  bool ret = false;

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);
  // check if feature is present
  if (!isFeature ("TriggerDivider\0", NULL)) {
    GST_WARNING_OBJECT (gencamsrc, "TriggerDivider: feature not supported");
    return ret;
  }
  // Set Trigger Divider for the incoming Trigger Pulses.
  ret =
      setIntFeature ("TriggerDivider\0", &gencamParams->triggerDivider, false);

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return ret;
}


bool
Genicam::setTriggerMultiplier (void)
{
  bool ret = false;

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);
  // check if feature is present
  if (!isFeature ("TriggerMultiplier\0", NULL)) {
    GST_WARNING_OBJECT (gencamsrc, "TriggerMultiplier: feature not supported");
    return ret;
  }
  // Set Trigger Multiplier for the incoming Trigger Pulses.
  ret =
      setIntFeature ("TriggerMultiplier\0", &gencamParams->triggerMultiplier,
      false);

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return ret;
}


bool
Genicam::setTriggerDelay (void)
{
  bool ret = false;
  char triggerDelayStr[32];

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);
  // Check the feature string if it exists or not
  if (isFeature ("TriggerDelay\0", NULL)) {
    strncpy (triggerDelayStr, "TriggerDelay\0", sizeof ("TriggerDelay\0"));
  } else if (isFeature ("TriggerDelayAbs\0", NULL)) {
    strncpy (triggerDelayStr, "TriggerDelayAbs\0",
        sizeof ("TriggerDelayAbs\0"));
  } else {
    // Feature does not exist
    GST_WARNING_OBJECT (gencamsrc, "TriggerDelay: feature not supported");
    return ret;
  }

  // Set Trigger Delay after trigger reception before activating it.
  ret = setFloatFeature (triggerDelayStr, &gencamParams->triggerDelay, false);

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return ret;
}


bool
Genicam::setTriggerMode (const char *tMode)
{
  bool ret = false;

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);
  // Set the Trigger Mode.
  ret = rcg::setEnum (nodemap, "TriggerMode", tMode, false);

  if (!ret) {
    GST_WARNING_OBJECT (gencamsrc, "TriggerMode: %s set failed.", tMode);
  } else {
    GST_INFO_OBJECT (gencamsrc, "TriggerMode: %s set successful.", tMode);
    triggerMode.assign (tMode);
  }

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return ret;
}


bool
Genicam::setTriggerOverlap (void)
{
  bool isTriggerOverlapSet = false;

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);
  // Check if the feature is supported or not.
  if (!isFeature ("TriggerOverlap\0", NULL)) {
    GST_WARNING_OBJECT (gencamsrc, "TriggerOverlap: feature not Supported");
    return isTriggerOverlapSet;
  }
  // Possible values: Off, ReadOut, PreviousFrame, PreviousLine
  isTriggerOverlapSet =
      setEnumFeature ("TriggerOverlap\0", gencamParams->triggerOverlap, false);

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return isTriggerOverlapSet;
}


bool
Genicam::setTriggerActivation (void)
{
  bool isTriggerActivationSet = false;

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);
  // Check if the feature is supported or not.
  if (!isFeature ("TriggerActivation\0", NULL)) {
    GST_WARNING_OBJECT (gencamsrc, "TriggerActivation: feature not Supported");
    return isTriggerActivationSet;
  }
  // Possible values: RisingEdge, FallingEdge, AnyEdge. LevelHigh, LevelLow
  isTriggerActivationSet =
      setEnumFeature ("TriggerActivation\0", gencamParams->triggerActivation,
      false);

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return isTriggerActivationSet;
}


bool
Genicam::setAcquisitionMode (void)
{
  bool isAcquisitionModeSet = false;

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);
  // Possible values: Continuous, MultiFrame, SingleFrame
  isAcquisitionModeSet =
      setEnumFeature ("AcquisitionMode\0", gencamParams->acquisitionMode,
      false);

  std::string aMode = rcg::getEnum (nodemap, "AcquisitionMode", false);
  acquisitionMode.assign (aMode);
  if (aMode == "Continuous") {
    // Set trigger mode Off for Continuous mode
    // TODO handle trigger mode on for continuous
    setTriggerMode ("Off");
  } else {
    // Set trigger mode On for Non-Continuous mode
    setTriggerMode ("On");

    // Set "FrameTriggerWait" to check AcquisitionStatus in Create for TriggerSource = Software
    GST_INFO_OBJECT (gencamsrc,
        "Setting AcquisitionStatusSelector to \"FrameTriggerWait\"");
    rcg::setEnum (nodemap, "AcquisitionStatusSelector", "FrameTriggerWait",
        false);
  }

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return isAcquisitionModeSet;
}


bool
Genicam::setDeviceClockSelector (void)
{
  bool isDeviceClockSelectorSet = false;

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);
  // Check if DeviceClockSelector is present or not, if not then return
  if (!isFeature ("DeviceClockSelector\0", NULL)) {
    GST_WARNING_OBJECT (gencamsrc,
        "DeviceClockSelector: feature not supported");
    return isDeviceClockSelectorSet;
  }
  // Possible values: Sensor, SensorDigitization, CameraLink, Device-specific
  isDeviceClockSelectorSet =
      setEnumFeature ("DeviceClockSelector\0",
      gencamParams->deviceClockSelector, false);

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return isDeviceClockSelectorSet;
}


bool
Genicam::getDeviceClockFrequency (void)
{
  float deviceClockFrequency;

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);
  // Check if DeviceClockFrequency is present or not, if not then return
  if (!isFeature ("DeviceClockFrequency\0", NULL)) {
    GST_WARNING_OBJECT (gencamsrc,
        "DeviceClockFrequency: feature not supported");
    return false;
  }

  deviceClockFrequency =
      rcg::getFloat (nodemap, "DeviceClockFrequency", NULL, NULL, false, 0);

  std::string deviceClockSelector =
      rcg::getEnum (nodemap, "DeviceClockSelector", false);
  GST_INFO_OBJECT (gencamsrc, "DeviceClockFrequency[%s]: value is %f.",
      deviceClockSelector.c_str (), deviceClockFrequency);

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return true;
}


bool
Genicam::setTriggerSoftware (void)
{
  bool ret = false;

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);
  // Proceed only when TriggerSource = Software
  if (triggerSource != "Software") {
    GST_WARNING_OBJECT (gencamsrc,
        "TriggerSoftware: command not trigerred; TriggerSource is not \"Software\"");
    return ret;
  }
  // Execute TriggerSoftware command
  ret = rcg::callCommand (nodemap, "TriggerSoftware", false);
  if (!ret) {
    GST_WARNING_OBJECT (gencamsrc, "TriggerSoftware set failed.");
  } else {
    GST_INFO_OBJECT (gencamsrc, "Call Command: \"TriggerSoftware\"");
  }

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return ret;
}


bool
Genicam::setTriggerSelector (void)
{
  bool isTriggerSelectorSet = false;

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);
  // Check if feature is supported or not.
  if (!isFeature ("TriggerSelector\0", NULL)) {
    GST_WARNING_OBJECT (gencamsrc, "TriggerSelector: feature not supported");
    return isTriggerSelectorSet;
  }
  // Possible values: AcquisitionStart, AcquisitionEnd, AcquisitionActive, FrameStart, FrameEnd,
  // FrameActive, FrameBurstStart, FrameBurstEnd, FrameBurstActive, LineStart, ExposureStart,
  // ExposureEnd, ExposureActive, MultiSlopeExposureLimit1
  isTriggerSelectorSet =
      setEnumFeature ("TriggerSelector\0", gencamParams->triggerSelector,
      false);

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return isTriggerSelectorSet;
}


bool
Genicam::setTriggerSource (void)
{
  bool isTriggerSourceSet = false;
  std::vector < std::string > triggerSources;

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);
  // Check if feature is supported or not.
  rcg::getEnum (nodemap, "TriggerSource", triggerSources, false);
  if (triggerSources.size () == 0) {
    GST_WARNING_OBJECT (gencamsrc, "TriggerSource: feature not Supported");
    return isTriggerSourceSet;
  }
  // Proceed only if TriggerMode is ON
  /* TODO By default, setting trigger source software is a good idea
     even if trigger mode is not on */
  if (triggerMode != "On") {
    GST_WARNING_OBJECT (gencamsrc,
        "TriggerSource: not configured as TriggerMode is not \"On\"");
    return isTriggerSourceSet;
  }
  // Possible values: Software, SoftwareSignal<n>, Line<n>, UserOutput<n>, Counter<n>Start,
  // Counter<n>End, Timer<n>Start, Timer<n>End, Encoder<n>, <LogicBlock<n>>, Action<n>,
  // LinkTrigger<n>, CC<n>, ...
  isTriggerSourceSet =
      setEnumFeature ("TriggerSource\0", gencamParams->triggerSource, false);

  std::string tSource = rcg::getEnum (nodemap, "TriggerSource", false);
  triggerSource.assign (tSource);

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return isTriggerSourceSet;
}


bool
Genicam::setDeviceLinkThroughputLimit (void)
{
  bool isThroughputLimitSet = false;
  std::vector < std::string > throughputLimitModes;

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);
  // Is DeviceLinkThroughputLimit supported? if not then return
  if (!isFeature ("DeviceLinkThroughputLimit\0", NULL)) {
    GST_WARNING_OBJECT (gencamsrc,
        "DeviceLinkThroughputLimit: feature not supported");
    return isThroughputLimitSet;
  }
  // Is DeviceLinkThroughputLimitMode supported? Enable if supported
  rcg::getEnum (nodemap, "DeviceLinkThroughputLimitMode", throughputLimitModes,
      false);
  if (throughputLimitModes.size () > 0) {
    // Set DeviceLinkThroughputLimitMode On
    deviceLinkThroughputLimitMode.assign ("On\0");
    rcg::setEnum (nodemap, "DeviceLinkThroughputLimitMode",
        deviceLinkThroughputLimitMode.c_str (), false);
    GST_INFO_OBJECT (gencamsrc,
        "Setting DeviceLinkThroughputLimitMode to \"On\"");
  }
  // Configure DeviceLinkThroughputLimit
  isThroughputLimitSet =
      setIntFeature ("DeviceLinkThroughputLimit\0",
      &gencamParams->deviceLinkThroughputLimit, true);

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return isThroughputLimitSet;
}


bool
Genicam::setChannelPacketSize (void)
{
  bool isChannelPacketSizeSet = false;

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);
  // Is GevSCPSPacketSize supported? if not then return
  if (!isFeature ("GevSCPSPacketSize\0", NULL)) {
    GST_WARNING_OBJECT (gencamsrc, "GevSCPSPacketSize: feature not supported");
    return isChannelPacketSizeSet;
  }
  // Configure GevSCPSPacketSize
  isChannelPacketSizeSet =
      setIntFeature ("GevSCPSPacketSize\0", &gencamParams->channelPacketSize,
      true);

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return isChannelPacketSizeSet;
}


bool
Genicam::setChannelPacketDelay (void)
{
  bool isChannelPacketDelaySet = false;

  GST_TRACE_OBJECT (gencamsrc, "START: %s", __func__);
  // Is GevSCPD supported? if not then return
  if (!isFeature ("GevSCPD\0", NULL)) {
    GST_WARNING_OBJECT (gencamsrc, "GevSCPD: feature not supported");
    return isChannelPacketDelaySet;
  }
  // Configure GevSCPD
  isChannelPacketDelaySet =
      setIntFeature ("GevSCPD\0", &gencamParams->channelPacketDelay, false);

  GST_TRACE_OBJECT (gencamsrc, "END: %s", __func__);
  return isChannelPacketDelaySet;
}
