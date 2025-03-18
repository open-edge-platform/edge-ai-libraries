/*
 * This file is part of the rc_genicam_api package.
 *
 * Copyright (c) 2019 Roboception GmbH
 * All rights reserved
 *
 * Author: Heiko Hirschmueller
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *
 * 1. Redistributions of source code must retain the above copyright notice,
 * this list of conditions and the following disclaimer.
 *
 * 2. Redistributions in binary form must reproduce the above copyright notice,
 * this list of conditions and the following disclaimer in the documentation
 * and/or other materials provided with the distribution.
 *
 * 3. Neither the name of the copyright holder nor the names of its contributors
 * may be used to endorse or promote products derived from this software without
 * specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
 * AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 * IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
 * ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
 * LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
 * CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
 * SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
 * INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
 * CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
 * ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 * POSSIBILITY OF SUCH DAMAGE.
 */

#ifndef RC_GENICAM_API_IMAGE_STORE
#define RC_GENICAM_API_IMAGE_STORE

#include "image.h"

#include <string>

namespace rcg
{

enum ImgFmt { PNM, PNG };

/**
  This method checks if the given file name already exists and produces a new
  file name if this happens.
*/

std::string ensureNewFileName(std::string name);

/**
  Stores the given image.

  NOTE: An exception that is based on std::exception is thrown in case of an
  error, e.g. if input or output format is not supported.

  @param name    Name of output file without suffix.
  @param fmt     Image file format.
  @param image   Image to be stored.
  @param yoffset First image row to be stored.
  @param height  Number of image rows to be stored. 0 means all rows.
*/

std::string storeImage(const std::string &name, ImgFmt fmt, const rcg::Image &image,
  size_t yoffset=0, size_t height=0);

/**
  Stores the given image as disparity. The image format must be Coord3D_C16.

  NOTE: An exception that is based on std::exception is thrown in case of an
  error, e.g. if input or output format is not supported.

  @param name   Name of output file without suffix.
  @param image  Image to be stored.
  @param inv    Value to mark invalid pixels.
  @param scale  Scale factor for valid values.
  @param offset Offset for valid values.
*/

std::string storeImageAsDisparityPFM(const std::string &name, const rcg::Image &image,
  int inv, float scale, float offset);

}

#endif
