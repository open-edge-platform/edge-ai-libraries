// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_read_raw_position.cpp
 *
 * Maintainer: Yichong Tang <yichong.tang@intel.com>
 *
 */

#include <fb/private/include/fb_read_raw_position.hpp>

namespace RTmotion
{
mcLREAL FbReadRawPosition::getAxisValue()
{
  return axis_->getPos();
}

}  // namespace RTmotion
