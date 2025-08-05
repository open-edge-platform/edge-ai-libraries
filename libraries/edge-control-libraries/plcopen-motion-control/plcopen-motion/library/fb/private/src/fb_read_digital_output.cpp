// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_read_digital_output.cpp
 *
 * Maintainer: Wu Xian <xian.wu@intel.com>
 *
 */

#include <fb/private/include/fb_read_digital_output.hpp>

namespace RTmotion
{
FbReadDigitalOutput::FbReadDigitalOutput()
{
  io_type_ = typeOutput;
}

void FbReadDigitalOutput::setOutputNumber(mcUINT outputNum)
{
  io_num_ = outputNum;
}

mcBOOL FbReadDigitalOutput::getValue()
{
  return io_data_;
}

}  // namespace RTmotion
