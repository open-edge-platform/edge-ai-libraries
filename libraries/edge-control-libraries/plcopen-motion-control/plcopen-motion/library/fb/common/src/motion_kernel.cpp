// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file motion_kernel.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <fb/common/include/motion_kernel.hpp>
#include <fb/common/include/logging.hpp>

namespace RTmotion
{
MotionKernel::MotionKernel()
{
}

MotionKernel::~MotionKernel()
{
}

void MotionKernel::runCycle(const mcLREAL master_ref_pos,
                            const mcLREAL master_ref_vel,
                            const mcLREAL axis_ref_pos,
                            const mcLREAL axis_ref_vel,
                            const mcLREAL axis_ref_acc, MC_AXIS_STATES* state,
                            OverrideFactors& override_factors)
{
  // FB queue process
  if (!fb_queue_.empty())
  {
    ExecutionNode* fb_front = fb_queue_.front();
    DEBUG_PRINT("MotionKernel::runCycle fb_queue_ is not empty %p.\n",
                (void*)fb_front);

    // Check if the motion kernel mission is done
    if (fb_front->checkMissionDone(axis_ref_pos, axis_ref_vel) == mcTRUE)
      fb_front->onDone(state);

    // If the first FB is aborted or in error, remove it from the execution
    // queue
    if (fb_front->isAborted() == mcTRUE || fb_front->isError() == mcTRUE)
    {
      DEBUG_PRINT("Abort front FB %p.\n", (void*)fb_front);
      fb_front->taken_ = mcFALSE;
      fb_queue_.pop_front();
    }

    // If the first FB is done, move it to be hold
    if (fb_front->isDone() == mcTRUE)
    {
      if (fb_hold_)
      {
        DEBUG_PRINT("Abort hold FB %p.\n", (void*)fb_hold_);
        fb_hold_->taken_ = mcFALSE;
        fb_hold_         = nullptr;
      }
      fb_hold_ = fb_front;
      fb_queue_.pop_front();
      DEBUG_PRINT(
          "MotionKernel::runCycle FB is done, hold it. FB queue is empty? %d\n",
          fb_queue_.empty());
    }

    // If there is any FB in the queue, activate it
    if (!fb_queue_.empty())
    {
      ExecutionNode* fb_front = fb_queue_.front();
      DEBUG_PRINT("Front node is active? %d, is enabled? %d.\n",
                  fb_front->isActive() == mcTRUE,
                  fb_front->getAxisNodeInstance()->isEnabled() == mcTRUE);
      if (fb_front->isActive() == mcFALSE &&
          fb_front->getAxisNodeInstance()->isEnabled() == mcTRUE)
      {
        fb_front->updateOverrideFactors(override_factors);
        fb_front->onActive(state);  // Activate the first node from queue
      }

      if (fb_front->isActive() ==
          mcTRUE)  // If the first FB is active, execute it
      {
        DEBUG_PRINT("FB queue is empty, FB mode is %d.\n",
                    fb_front->getBufferMode());
        if (fb_front->getBufferMode() == mcAborting)
        {
          DEBUG_PRINT("FB hold is %p.\n", (void*)fb_hold_);
          if (fb_hold_)  // Since the front FB from queue is ready to execute,
                         // remove the hold FB
          {
            DEBUG_PRINT("Abort hold FB %d.\n", fb_hold_->getMotionMode());
            fb_hold_->onCommandAborted();
            fb_hold_->taken_ = mcFALSE;
            fb_hold_         = nullptr;
          }
        }
        fb_front->onExecution(master_ref_pos, master_ref_vel);
        // check override state and replan the fb_front if it is overridden
        if (override_factors.override_flag == mcTRUE)
        {
          fb_front->setReplan();
          fb_front->restart();
          fb_front->updateOverrideFactors(override_factors);
          setNodeStartState(fb_front, axis_ref_pos, axis_ref_vel, axis_ref_acc,
                            fb_front->getEndAcc());
          override_factors.override_flag = mcFALSE;
        }
        underlying_move_node_ = fb_front;
      }
      else
        underlying_move_node_ = nullptr;
    }
    else if (fb_hold_)
    {
      // Superimposed move for fb_hold with velocity FB
      if (fb_hold_->getMotionMode() == mcMoveVelocityMode)
        underlying_move_node_ = fb_hold_;
    }
  }
  else if (fb_hold_ && override_factors.override_flag == mcTRUE)
  {
    // reset active, done, busy and command_aborted to trigger onActice
    fb_hold_->setReplan();
    fb_hold_->restart();
    fb_hold_->updateOverrideFactors(override_factors);
    setNodeStartState(fb_hold_, axis_ref_pos, axis_ref_vel, axis_ref_acc,
                      fb_hold_->getEndAcc());
    fb_queue_.push_back(fb_hold_);
    fb_hold_                       = nullptr;
    override_factors.override_flag = mcFALSE;
  }

  // Move superimposed node process
  if (sup_move_node_ != nullptr)
  {
    // Check FB done
    fb_axis_node_sup_ = sup_move_node_->getAxisNodeInstance();
    if (fb_axis_node_sup_ != nullptr)
    {
      if (fb_axis_node_sup_->isDone() == mcTRUE)
      {
        sup_move_node_->onDone(nullptr);
      }
    }

    // If the sup FB is aborted or in error
    if (sup_move_node_->isAborted() == mcTRUE ||
        sup_move_node_->isError() == mcTRUE)
    {
      sup_move_node_->taken_ = mcFALSE;
      sup_move_node_         = nullptr;
      return;
    }

    // Check execution node of superimposed is done
    if (sup_move_node_->isDone() == mcTRUE)
    {
      sup_move_node_->taken_ = mcFALSE;
      sup_move_node_         = nullptr;
    }

    if (sup_move_node_ != nullptr)
      sup_move_node_->onExecution(master_ref_pos, master_ref_vel);
  }
}

void MotionKernel::setNodeStartState(ExecutionNode* node, mcLREAL current_pos,
                                     mcLREAL current_vel, mcLREAL current_acc,
                                     mcLREAL end_acc)
{
  if (node->getPlannerType() != mcPoly5 && node->getPlannerType() != mcLine)
  {
    node->setStartPos(current_pos);
    node->setStartVel(current_vel);
    node->setStartAcc(current_acc);
    node->setEndAcc(end_acc);
    node->setTerminateCondition(current_pos);
    DEBUG_PRINT(
        "MotionKernel::setNodeStartState: fb_queue (size %zu) is empty\n",
        fb_queue_.size());
  }
}

void MotionKernel::addFBToQueue(ExecutionNode* node, mcLREAL current_pos,
                                mcLREAL current_vel, mcLREAL current_acc,
                                mcLREAL end_acc)
{
  node->setReplan();
  DEBUG_PRINT("MotionKernel::addFBToQueue: current_pos: %f, current_vel: %f\n",
              current_pos, current_vel);

  // If MC_MoveSuperimposed is active, then any new added FB will abort
  // underlying and on-going superimposed motion
  if (sup_move_node_ != nullptr)
  {
    abortCurSupMoveFB();
    setAllFBsAborted();
  }

  if (fb_queue_.empty())  // Probably there is a hold node
  {
    setNodeStartState(node, current_pos, current_vel, current_acc, end_acc);
  }
  else  // If queue is not empty, it's not possible to have a hold node
  {
    ExecutionNode* fb_prev = fb_queue_.back();

    // If not aborting, then set the end velocity of the previous FB
    switch (node->getBufferMode())
    {
      case mcBuffered:
        break;
      case mcAborting:
        if (node->getPlannerType() != mcPoly5 &&
            node->getPlannerType() != mcLine)
        {
          node->setStartPos(current_pos);
          node->setStartVel(current_vel);
          node->setStartAcc(current_acc);
          node->setEndAcc(end_acc);
          node->setTerminateCondition(fb_prev->getEndPos());
        }
        setAllFBsAborted();
        break;
      case mcBlendingPrevious: {
        fb_prev->setEndVel(fb_prev->getVelocity());
        fb_prev->setReplan();
      }
      break;
      case mcBlendingNext: {
        fb_prev->setEndVel(node->getVelocity());
        fb_prev->setReplan();
      }
      break;
      case mcBlendingHigh: {
        fb_prev->setEndVel(
            std::max(fb_prev->getVelocity(), node->getVelocity()));
        fb_prev->setReplan();
      }
      break;
      case mcBlendingLow: {
        fb_prev->setEndVel(
            std::min(fb_prev->getVelocity(), node->getVelocity()));
        fb_prev->setReplan();
      }
      break;
      default:
        break;
    }

    if (node->getBufferMode() != mcAborting)
    {
      node->setStartPos(fb_prev->getEndPos());
      node->setStartVel(fb_prev->getEndVel());
      node->setStartAcc(0.0);
      node->setEndAcc(0.0);
      node->setTerminateCondition(fb_prev->getEndPos());
    }
  }

  fb_queue_.push_back(node);
}

std::deque<ExecutionNode*>& MotionKernel::getQueuedMotions()
{
  return fb_queue_;
}

void MotionKernel::setAllFBsAborted()
{
  while (!fb_queue_.empty())
  {
    ExecutionNode* fb = fb_queue_.front();
    if (fb)
    {
      fb->onCommandAborted();
      fb->taken_ = mcFALSE;
    }
    fb_queue_.pop_front();
  }
  if (fb_hold_)
  {
    fb_hold_->onCommandAborted();
    fb_hold_->taken_ = mcFALSE;
    fb_hold_         = nullptr;
  }
}

void MotionKernel::getCommands(mcLREAL* pos_cmd, mcLREAL* vel_cmd,
                               mcLREAL* acc_cmd)
{
  if (!fb_queue_.empty())
  {
    DEBUG_PRINT(
        "MotionKernel::getCommands: fb_queue_ (size %zu) is not empty\n",
        fb_queue_.size());
    fb_queue_.front()->getCommands(pos_cmd, vel_cmd, acc_cmd);
  }
  else
  {
    DEBUG_PRINT("MotionKernel::getCommands: fb_queue_ (size %zu) is empty\n",
                fb_queue_.size());
    if (fb_hold_)
      fb_hold_->getCommands(pos_cmd, vel_cmd, acc_cmd);
  }
}

void MotionKernel::offsetAllFBs(mcLREAL home_pos)
{
  for (auto it : fb_queue_)
  {
    it->offsetFB(home_pos);
    it->setReplan();
  }
}

void MotionKernel::addSupMoveFB(ExecutionNode* node, mcLREAL current_pos,
                                mcLREAL current_vel, mcLREAL current_acc,
                                mcLREAL end_acc)
{
  // refresh basic params
  if (underlying_move_node_ != nullptr)
  {
    // Sup move add to underlying motion
    fb_axis_node_tmp_ = node->getAxisNodeInstance();
    fb_axis_node_und_ = underlying_move_node_->getAxisNodeInstance();
    if ((fb_axis_node_tmp_ != nullptr) && (fb_axis_node_und_ != nullptr))
      node->setBasicParams(
          fb_axis_node_tmp_, mcMoveSupMode,
          fb_axis_node_tmp_->getPosition() + fb_axis_node_und_->getPosition(),
          fb_axis_node_tmp_->getVelocity() + fb_axis_node_und_->getVelocity(),
          fb_axis_node_tmp_->getAcceleration() +
              fb_axis_node_und_->getAcceleration(),
          fb_axis_node_tmp_->getDeceleration() +
              fb_axis_node_und_->getDeceleration(),
          fb_axis_node_tmp_->getJerk() + fb_axis_node_und_->getJerk(),
          mcAborting, mcRuckig);
  }
  else
  {
    // non underlying motion FB, acts like move relative
    fb_axis_node_tmp_ = node->getAxisNodeInstance();
    if (fb_axis_node_tmp_ != nullptr)
      node->setBasicParams(fb_axis_node_tmp_, mcMoveSupMode,
                           fb_axis_node_tmp_->getPosition(),
                           fb_axis_node_tmp_->getVelocity(),
                           fb_axis_node_tmp_->getAcceleration(),
                           fb_axis_node_tmp_->getDeceleration(),
                           fb_axis_node_tmp_->getJerk(), mcAborting, mcRuckig);
  }
  // set other planner params
  node->setReplan();
  node->setStartPos(current_pos);
  node->setStartVel(current_vel);
  node->setStartAcc(current_acc);
  node->setEndAcc(end_acc);
  node->setTerminateCondition(current_pos);
  sup_move_node_    = node;
  fb_axis_node_und_ = nullptr;
  fb_axis_node_tmp_ = nullptr;
}

void MotionKernel::abortCurSupMoveFB()
{
  // new sup_move_node will abort current sup_move_node
  if (sup_move_node_ != nullptr)
  {
    sup_move_node_->onCommandAborted();
    DEBUG_PRINT(
        "MotionKernel::abortCurSupMoveFB: reset current sup-move-node. \n");
  }
}

void MotionKernel::getSupMoveCommands(mcLREAL* pos_cmd, mcLREAL* vel_cmd,
                                      mcLREAL* acc_cmd)
{
  if (sup_move_node_ != nullptr)
  {
    sup_move_node_->getCommands(pos_cmd, vel_cmd, acc_cmd);
  }
}

void MotionKernel::replanUnderlyingNode(mcLREAL sup_move_pos,
                                        mcLREAL current_pos,
                                        mcLREAL current_vel,
                                        mcLREAL current_acc)
{
  if (underlying_move_node_ != nullptr)
  {
    fb_axis_node_und_ = underlying_move_node_->getAxisNodeInstance();
    // refresh basic params
    underlying_move_node_->setBasicParams(
        underlying_move_node_->getAxisNodeInstance(),
        underlying_move_node_->getMotionMode(),
        fb_axis_node_und_->getPosition() + sup_move_pos - current_pos,
        fb_axis_node_und_->getVelocity(), fb_axis_node_und_->getAcceleration(),
        fb_axis_node_und_->getDeceleration(), fb_axis_node_und_->getJerk(),
        fb_axis_node_und_->getBufferMode(),
        underlying_move_node_->getPlannerType());

    // set other planner params
    underlying_move_node_->setReplan();
    underlying_move_node_->setStartPos(current_pos);
    underlying_move_node_->setStartVel(current_vel);
    underlying_move_node_->setStartAcc(current_acc);
    underlying_move_node_->setTerminateCondition(current_pos);
    fb_axis_node_und_ = nullptr;
  }
}

}  // namespace RTmotion
