// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_axis_read.hpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#pragma once

#include <fb/common/include/fb_axis_admin.hpp>

namespace RTmotion
{
/**
 * @brief Function block base for single axis motion
 */
class FbAxisRead : public FbAxisAdmin
{
public:
  FbAxisRead();
  ~FbAxisRead() override = default;

  virtual mcLREAL getFloatValue();
  virtual mcLREAL getAxisValue();

  MC_ERROR_CODE onExecution() override;
  MC_ERROR_CODE onFallingEdgeExecution() override;

protected:
  mcLREAL value_;
};
}  // namespace RTmotion