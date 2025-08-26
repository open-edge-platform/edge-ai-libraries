// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_read_axis_error.hpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#pragma once

#include <fb/common/include/fb_axis_read.hpp>

namespace RTmotion
{
/**
 * @brief Function block base for single axis motion
 */
class FbReadAxisError : public FbAxisRead
{
public:
  FbReadAxisError();
  ~FbReadAxisError() override = default;

  MC_ERROR_CODE onExecution() override;
  MC_ERROR_CODE onFallingEdgeExecution() override;
  MC_ERROR_CODE getAxisErrorId();

public:
  VAR_OUTPUT MC_ERROR_CODE axis_error_id_;
};
}  // namespace RTmotion