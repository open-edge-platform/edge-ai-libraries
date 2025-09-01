// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_read_raw_position.hpp
 *
 * Maintainer: Yichong Tang <yichong.tang@intel.com>
 *
 */

#pragma once

#include <fb/common/include/fb_axis_read.hpp>

namespace RTmotion
{
/**
 * @brief Function block base for single axis motion
 */
class FbReadRawPosition : public FbAxisRead
{
public:
  FbReadRawPosition()           = default;
  ~FbReadRawPosition() override = default;

  mcLREAL getAxisValue() override;
};
}  // namespace RTmotion