// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_read_digital_input.hpp
 *
 * Maintainer: Wu Xian <xian.wu@intel.com>
 *
 */

#pragma once

#include <fb/private/include/fb_io_operation.hpp>
#include <fb/private/include/io.hpp>

namespace RTmotion
{
/**
 * @brief Function block base for digital input read
 */
class FbReadDigitalInput : public FbIoOperation
{
public:
  FbReadDigitalInput();
  ~FbReadDigitalInput() override = default;

  // Functions for addressing inputs
  void setInputNumber(mcUINT inputNum);

  // Functions for returning outputs
  mcBOOL getValue();
};
}  // namespace RTmotion
