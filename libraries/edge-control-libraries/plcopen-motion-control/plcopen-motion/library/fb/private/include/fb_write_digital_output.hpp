// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_write_digital_output.hpp
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
class FbWriteDigitalOutput : public FbIoOperation
{
public:
  FbWriteDigitalOutput();
  ~FbWriteDigitalOutput() override = default;

  // Functions for addressing inputs
  void setOutputNumber(mcUINT outputNum);
  void setValue(mcBOOL data);
};
}  // namespace RTmotion
