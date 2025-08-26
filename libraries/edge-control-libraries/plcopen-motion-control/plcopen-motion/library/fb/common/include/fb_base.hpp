// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_base.hpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#pragma once

#include <fb/common/include/axis.hpp>
#include <fb/common/include/logging.hpp>
#include <map>

namespace RTmotion
{
class Axis;

class FunctionBlock
{
public:
  FunctionBlock();

  FunctionBlock(const FunctionBlock& fb);

  FunctionBlock& operator=(const FunctionBlock& fb);

  virtual ~FunctionBlock();

  virtual void setAxis(AXIS_REF axis);

  virtual void runCycle();

  // Functions for working on different status
  virtual MC_ERROR_CODE onRisingEdgeExecution();

  virtual MC_ERROR_CODE onFallingEdgeExecution();

  virtual MC_ERROR_CODE onExecution();

  virtual MC_ERROR_CODE afterFallingEdgeExecution();

  virtual void onError(MC_ERROR_CODE error_code);

protected:
  /// AXIS_REF
  VAR_IN_OUT AXIS_REF axis_;
};

}  // namespace RTmotion
