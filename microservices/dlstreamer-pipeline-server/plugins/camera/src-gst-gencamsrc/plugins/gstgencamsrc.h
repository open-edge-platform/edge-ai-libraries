/*
# Apache v2 license
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
*/

#ifndef _GST_GENCAMSRC_H_
#define _GST_GENCAMSRC_H_

#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <gst/base/gstpushsrc.h>

G_BEGIN_DECLS
#define GST_TYPE_GENCAMSRC (gst_gencamsrc_get_type())
#define GST_GENCAMSRC(obj)                                                     \
  (G_TYPE_CHECK_INSTANCE_CAST((obj), GST_TYPE_GENCAMSRC, GstGencamsrc))
#define GST_GENCAMSRC_CLASS(klass)                                             \
  (G_TYPE_CHECK_CLASS_CAST((klass), GST_TYPE_GENCAMSRC, GstGencamsrcClass))
#define GST_IS_GENCAMSRC(obj)                                                  \
  (G_TYPE_CHECK_INSTANCE_TYPE((obj), GST_TYPE_GENCAMSRC))
#define GST_IS_GENCAMSRC_CLASS(obj)                                            \
  (G_TYPE_CHECK_CLASS_TYPE((klass), GST_TYPE_GENCAMSRC))
#define ZERO 0
typedef struct _GstGencamsrc GstGencamsrc;
typedef struct _GstGencamsrcClass GstGencamsrcClass;

struct _GstGencamsrc
{
  GstPushSrc base_gencamsrc;

  /* Declare data members */
  guint frameNumber;            // for every frame out

  /* Declare plugin properties here */
  GencamParams properties;
  gpointer gencam;

  /* Declaration for FPS calculation*/
  guint64 frames;
  guint64 prevSecTime;
  guint64 elapsedTime;

};

struct _GstGencamsrcClass
{
  GstPushSrcClass base_gencamsrc_class;
};

GType gst_gencamsrc_get_type (void);

G_END_DECLS
#endif
