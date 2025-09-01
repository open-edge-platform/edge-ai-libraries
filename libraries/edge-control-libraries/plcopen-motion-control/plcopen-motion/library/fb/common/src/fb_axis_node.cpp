// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_axis_node.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <fb/common/include/fb_axis_node.hpp>
#include <fb/common/include/logging.hpp>

namespace RTmotion
{
FbAxisNode::FbAxisNode()
  : execute_(mcFALSE)
  , done_(mcFALSE)
  , busy_(mcFALSE)
  , active_(mcFALSE)
  , command_aborted_(mcFALSE)
  , error_(mcFALSE)
  , error_id_(mcErrorCodeGood)
  , buffer_mode_(mcBuffered)
  , output_flag_(mcFALSE)
{
}

void FbAxisNode::syncStatus(mcBOOL done, mcBOOL busy, mcBOOL active,
                            mcBOOL cmd_aborted, mcBOOL error,
                            MC_ERROR_CODE error_id)
{
  done_            = done;
  busy_            = busy;
  active_          = active;
  command_aborted_ = cmd_aborted;
  error_           = error;
  error_id_        = error_id;

  output_flag_ = execute_ == mcTRUE ? mcFALSE : mcTRUE;
  DEBUG_PRINT("FbAxisNode::syncStatus %s\n",
              done_ == mcTRUE ? "mcTRUE" : "mcFALSE");
}

mcBOOL FbAxisNode::isEnabled()
{
  return execute_;
}

mcBOOL FbAxisNode::isDone()
{
  return done_;
}

mcBOOL FbAxisNode::isBusy()
{
  return busy_;
}

mcBOOL FbAxisNode::isActive()
{
  return active_;
}

mcBOOL FbAxisNode::isAborted()
{
  return command_aborted_;
}

mcBOOL FbAxisNode::isError()
{
  DEBUG_PRINT("FbAxisNode::isError %s\n",
              error_ == mcTRUE ? "mcTRUE" : "mcFALSE");
  return error_;
}

MC_ERROR_CODE FbAxisNode::getErrorID()
{
  return error_id_;
}

}  // namespace RTmotion
