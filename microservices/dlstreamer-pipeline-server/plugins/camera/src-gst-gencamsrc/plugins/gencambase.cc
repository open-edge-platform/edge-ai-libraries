/*
 * GStreamer Generic Camera Plugin
 * Copyright (c) 2020, Intel Corporation
 * All rights reserved.
 *
 * Authors:
 *   Gowtham Hosamane <gowtham.hosamane@intel.com>
 *   Smitesh Sutaria <smitesh.sutaria@intel.com>
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

#include <iostream>
#include <gst/gst.h>
#include <gst/video/video-format.h>

#include "genicam.h"
#include "gstgencamsrc.h"

GST_DEBUG_CATEGORY_EXTERN (gst_gencamsrc_debug_category);
#define GST_CAT_DEFAULT gst_gencamsrc_debug_category

using namespace std;


EXTERNC bool
gencamsrc_init (GencamParams * properties, GstBaseSrc * src)
{
  bool retVal = false;

  GstGencamsrc *gencamsrc = GST_GENCAMSRC (src);

  GST_DEBUG_OBJECT (gencamsrc, "START: %s", __func__);

  Genicam *genicam = new Genicam;
  retVal = genicam->Init (properties, src);

  gencamsrc->gencam = (void *) genicam;

  GST_DEBUG_OBJECT (gencamsrc, "END: %s", __func__);
  return retVal;
}


EXTERNC bool
gencamsrc_start (GstBaseSrc * src)
{
  bool retVal = false;

  GstGencamsrc *gencamsrc = GST_GENCAMSRC (src);

  GST_DEBUG_OBJECT (gencamsrc, "START: %s", __func__);

  Genicam *genicam = (Genicam *) gencamsrc->gencam;
  retVal = genicam->Start ();

  GST_DEBUG_OBJECT (gencamsrc, "END: %s", __func__);
  return retVal;
}


EXTERNC bool
gencamsrc_stop (GstBaseSrc * src)
{
  bool retVal = false;

  GstGencamsrc *gencamsrc = GST_GENCAMSRC (src);

  GST_DEBUG_OBJECT (gencamsrc, "START: %s", __func__);

  Genicam *genicam = (Genicam *) gencamsrc->gencam;
  retVal = genicam->Stop ();

  delete genicam;
  genicam = nullptr;
  gencamsrc->gencam = genicam;

  GST_DEBUG_OBJECT (gencamsrc, "END: %s", __func__);
  return retVal;
}


EXTERNC bool
gencamsrc_create (GstBuffer ** buf, GstMapInfo * mapInfo, GstBaseSrc * src)
{
  bool retVal = false;
  GstGencamsrc *gencamsrc = GST_GENCAMSRC (src);

  GST_DEBUG_OBJECT (gencamsrc, "START: %s", __func__);

  Genicam *genicam = (Genicam *) gencamsrc->gencam;
  retVal = genicam->Create (buf, mapInfo);

  GST_DEBUG_OBJECT (gencamsrc, "END: %s", __func__);

  return retVal;
}
