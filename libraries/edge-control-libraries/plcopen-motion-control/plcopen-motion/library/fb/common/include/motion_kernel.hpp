// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file motion_kernel.hpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#pragma once

#include <fb/common/include/global.hpp>
#include <queue>
#include <fb/common/include/execution_node.hpp>

namespace RTmotion
{
class ExecutionNode;

class MotionKernel
{
public:
  MotionKernel();

  virtual ~MotionKernel();

  virtual void runCycle(const mcLREAL master_ref_pos,
                        const mcLREAL master_ref_vel,
                        const mcLREAL axis_ref_pos, const mcLREAL axis_ref_vel,
                        const mcLREAL axis_ref_acc, MC_AXIS_STATES* state,
                        OverrideFactors& override_factors);

  void setNodeStartState(ExecutionNode* fb, mcLREAL current_pos,
                         mcLREAL current_vel, mcLREAL current_acc,
                         mcLREAL end_acc);

  void addFBToQueue(ExecutionNode* fb, mcLREAL current_pos, mcLREAL current_vel,
                    mcLREAL current_acc, mcLREAL end_acc);

  std::deque<ExecutionNode*>& getQueuedMotions();

  void getCommands(mcLREAL* pos_cmd, mcLREAL* vel_cmd, mcLREAL* acc_cmd);

  void setAllFBsAborted();

  void offsetAllFBs(mcLREAL home_pos);

  void addSupMoveFB(ExecutionNode* node, mcLREAL current_pos,
                    mcLREAL current_vel, mcLREAL current_acc, mcLREAL end_acc);

  void abortCurSupMoveFB();

  void getSupMoveCommands(mcLREAL* pos_cmd, mcLREAL* vel_cmd, mcLREAL* acc_cmd);

  void replanUnderlyingNode(mcLREAL sup_move_pos, mcLREAL current_pos,
                            mcLREAL current_vel, mcLREAL current_acc);

private:
  std::deque<ExecutionNode*> fb_queue_;
  ExecutionNode* fb_hold_ = nullptr;
  // Move Superimposed vars
  ExecutionNode* underlying_move_node_ = nullptr;
  ExecutionNode* sup_move_node_        = nullptr;
  FbAxisNode* fb_axis_node_sup_        = nullptr;
  FbAxisNode* fb_axis_node_und_        = nullptr;
  FbAxisNode* fb_axis_node_tmp_        = nullptr;
};

}  // namespace RTmotion