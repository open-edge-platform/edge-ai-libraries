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
