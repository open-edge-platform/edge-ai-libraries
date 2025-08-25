// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_reset.hpp
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
class FbReset : public FbAxisAdmin
{
public:
  FbReset()           = default;
  ~FbReset() override = default;

  MC_ERROR_CODE onExecution() override;
};
}  // namespace RTmotion
