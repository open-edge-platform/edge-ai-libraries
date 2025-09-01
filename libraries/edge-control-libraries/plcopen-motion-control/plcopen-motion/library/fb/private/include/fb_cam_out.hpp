// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_cam_out.hpp
 *
 * Maintainer: Yichong Tang <yichong.tang@intel.com>
 *
 */

#pragma once

#include <fb/common/include/global.hpp>
#include <fb/common/include/fb_axis_motion.hpp>
#include <fb/private/include/fb_cam_table_select.hpp>

namespace RTmotion
{
/**
 * @brief MC_CamOut
 */

class FbCamOut : public FbAxisMotion
{
public:
  FbCamOut()           = default;
  ~FbCamOut() override = default;

  MC_ERROR_CODE onRisingEdgeExecution() override;

  void setSlave(AXIS_REF slave);
};
}  // namespace RTmotion