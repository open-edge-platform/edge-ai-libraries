/*
# Apache v2 license
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
*/

#include <iostream>
#include <gst/gst.h>
#include <gst/video/video-format.h>

#include "genicam.h"
#include "gstgencamsrc.h"

/* On MSVC the debug category is defined in a .c TU (C linkage); the extern
 * declaration must match that linkage so the linker can resolve it. */
extern "C" { GST_DEBUG_CATEGORY_EXTERN (gst_gencamsrc_debug_category); }
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
