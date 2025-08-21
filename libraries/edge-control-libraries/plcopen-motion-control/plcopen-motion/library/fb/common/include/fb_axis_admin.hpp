// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_axis_admin.hpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#pragma once

#include <fb/common/include/fb_base.hpp>

namespace RTmotion
{
/**
 * @brief Function block base for single axis motion
 */
class FbAxisAdmin : public FunctionBlock
{
public:
  FbAxisAdmin();
  ~FbAxisAdmin() override = default;

  // Functions for addressing inputs
  virtual void setEnable(mcBOOL enable);

  virtual mcBOOL isEnabled();
  virtual mcBOOL isDone();
  virtual mcBOOL isValid();
  virtual mcBOOL isBusy();
  virtual mcBOOL isError();
  virtual MC_ERROR_CODE getErrorID();

  void runCycle() override;
  void onError(MC_ERROR_CODE error_code) override;

protected:
  // Inputs
  VAR_INPUT mcBOOL enable_;

  // Outputs
  VAR_OUTPUT mcBOOL done_;
  VAR_OUTPUT mcBOOL valid_;
  VAR_OUTPUT mcBOOL busy_;
  VAR_OUTPUT mcBOOL error_;
  VAR_OUTPUT MC_ERROR_CODE error_id_;

  mcBOOL enabled_;
};
}  // namespace RTmotion