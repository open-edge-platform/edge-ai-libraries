// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_read_digital_input.cpp
 *
 * Maintainer: Wu Xian <xian.wu@intel.com>
 *
 */

#include <fb/private/include/fb_read_digital_input.hpp>

namespace RTmotion
{
FbReadDigitalInput::FbReadDigitalInput()
{
  io_type_ = typeInput;
}

void FbReadDigitalInput::setInputNumber(mcUINT inputNum)
{
  io_num_ = inputNum;
}

mcBOOL FbReadDigitalInput::getValue()
{
  return io_data_;
}

}  // namespace RTmotion
