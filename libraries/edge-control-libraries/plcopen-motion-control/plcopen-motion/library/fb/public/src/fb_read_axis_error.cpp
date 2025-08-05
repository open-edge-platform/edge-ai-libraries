// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_read_axis_error.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <fb/public/include/fb_read_axis_error.hpp>

namespace RTmotion
{
FbReadAxisError::FbReadAxisError() : axis_error_id_(mcErrorCodeGood)
{
}

MC_ERROR_CODE FbReadAxisError::onExecution()
{
  return axis_error_id_ = axis_->getAxisError();
}

MC_ERROR_CODE FbReadAxisError::onFallingEdgeExecution()
{
  axis_error_id_ = mcErrorCodeGood;

  return mcErrorCodeGood;
}

MC_ERROR_CODE FbReadAxisError::getAxisErrorId()
{
  return axis_error_id_;
}

}  // namespace RTmotion
