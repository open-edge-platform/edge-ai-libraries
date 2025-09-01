// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file function_block.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <fb/common/include/fb_base.hpp>

namespace RTmotion
{
FunctionBlock::FunctionBlock() : axis_(nullptr)
{
}

FunctionBlock::FunctionBlock(const FunctionBlock& fb)
{
  axis_ = fb.axis_;
}

FunctionBlock& FunctionBlock::operator=(const FunctionBlock& fb)
{
  if (this != &fb)
  {
    axis_ = fb.axis_;
  }
  return *this;
}

FunctionBlock::~FunctionBlock()
{
  axis_ = nullptr;
}

void FunctionBlock::setAxis(AXIS_REF axis)
{
  axis_ = axis;
}

void FunctionBlock::runCycle()
{
}

// Functions for working on different status
MC_ERROR_CODE FunctionBlock::onRisingEdgeExecution()
{
  return mcErrorCodeGood;
}

MC_ERROR_CODE FunctionBlock::onFallingEdgeExecution()
{
  return mcErrorCodeGood;
}

MC_ERROR_CODE FunctionBlock::onExecution()
{
  return mcErrorCodeGood;
}

MC_ERROR_CODE FunctionBlock::afterFallingEdgeExecution()
{
  return mcErrorCodeGood;
}

void FunctionBlock::onError(MC_ERROR_CODE /*error_code*/)
{
}

}  // namespace RTmotion