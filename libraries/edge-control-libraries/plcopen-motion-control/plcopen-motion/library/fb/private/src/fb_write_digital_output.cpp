// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_write_digital_output.cpp
 *
 * Maintainer: Wu Xian <xian.wu@intel.com>
 *
 */

#include <fb/private/include/fb_write_digital_output.hpp>

namespace RTmotion
{
FbWriteDigitalOutput::FbWriteDigitalOutput()
{
  // set write type
  is_write_ = mcTRUE;
  io_type_  = typeOutput;
}

void FbWriteDigitalOutput::setOutputNumber(mcUINT outputNum)
{
  io_num_ = outputNum;
}

void FbWriteDigitalOutput::setValue(mcBOOL data)
{
  // set write value
  set_value_ = data;
}

}  // namespace RTmotion
