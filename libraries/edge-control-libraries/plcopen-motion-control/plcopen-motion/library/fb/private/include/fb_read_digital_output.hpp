// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_read_digital_output.hpp
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
 * @brief Function block base for digital output read
 */
class FbReadDigitalOutput : public FbIoOperation
{
public:
  FbReadDigitalOutput();
  ~FbReadDigitalOutput() override = default;

  // Functions for addressing inputs
  void setOutputNumber(mcUINT outputNum);

  // Functions for returning outputs
  mcBOOL getValue();
};
}  // namespace RTmotion
