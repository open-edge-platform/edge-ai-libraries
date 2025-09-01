// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file execution_node.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <fb/common/include/execution_node.hpp>
#include <fb/common/include/logging.hpp>

namespace RTmotion
{
ExecutionNode::ExecutionNode()
  : done_(mcFALSE)
  , busy_(mcFALSE)
  , active_(mcFALSE)
  , command_aborted_(mcFALSE)
  , error_(mcFALSE)
  , error_id_(mcErrorCodeGood)
  , start_pos_(0)
  , end_pos_(0)
  , start_vel_(0)
  , end_vel_(0)
  , start_acc_(0)
  , end_acc_(0)
  , duration_(1000000.0)
  , need_plan_(mcFALSE)
  , node_freq_(1000)
  , node_delta_time_(0.001)
  , node_active_time_(0)
  , planner_()
  , planner_type_(mcOffLine)
{
  pos_cmd_ = 0;
  vel_cmd_ = 0;
  acc_cmd_ = 0;
  pos_tmp_ = 0;
  vel_tmp_ = 0;
  acc_tmp_ = 0;

  pos_done_factor_ = 0.0001;
  vel_done_factor_ = 0.0001;

  fb_           = nullptr;
  motion_mode_  = mcNoMoveType;
  position_     = 0;
  velocity_     = 0;
  acceleration_ = 0;
  deceleration_ = 0;
  jerk_         = 0;
  buffer_mode_  = mcAborting;

  override_factors_.vel           = 1;
  override_factors_.acc           = 1;
  override_factors_.jerk          = 1;
  override_factors_.override_flag = mcFALSE;

#ifdef ADDR_CHECK
  printf("ExecutionNode::this: %p\n", (void*)this);
  printf("ExecutionNode::planner_: %p\n", (void*)&planner_);
#endif
}

ExecutionNode::ExecutionNode(const ExecutionNode& node)
{
  copyMemberVar(node);
}

ExecutionNode& ExecutionNode::operator=(const ExecutionNode& node)
{
  copyMemberVar(node);
  return *this;
}

void ExecutionNode::copyMemberVar(const ExecutionNode& node)
{
  if (this != &node)
  {
    position_     = node.position_;
    velocity_     = node.velocity_;
    acceleration_ = node.acceleration_;
    deceleration_ = node.deceleration_;
    jerk_         = node.jerk_;
    buffer_mode_  = node.buffer_mode_;

    done_            = node.done_;
    busy_            = node.busy_;
    active_          = node.active_;
    command_aborted_ = node.command_aborted_;
    error_           = node.error_;
    error_id_        = node.error_id_;

    fb_ = node.fb_;

    start_pos_       = node.start_pos_;
    end_pos_         = node.end_pos_;
    start_vel_       = node.start_vel_;
    end_vel_         = node.end_vel_;
    start_acc_       = node.start_acc_;
    end_acc_         = node.end_acc_;
    duration_        = node.duration_;
    pos_cmd_         = node.pos_cmd_;
    vel_cmd_         = node.vel_cmd_;
    acc_cmd_         = node.acc_cmd_;
    pos_tmp_         = node.pos_tmp_;
    vel_tmp_         = node.vel_tmp_;
    acc_tmp_         = node.acc_tmp_;
    need_plan_       = node.need_plan_;
    pos_done_factor_ = node.pos_done_factor_;
    vel_done_factor_ = node.vel_done_factor_;
    motion_mode_     = node.motion_mode_;

    override_factors_.vel           = node.override_factors_.vel;
    override_factors_.acc           = node.override_factors_.acc;
    override_factors_.jerk          = node.override_factors_.jerk;
    override_factors_.override_flag = node.override_factors_.override_flag;

    node_freq_        = node.node_freq_;
    node_delta_time_  = node.node_delta_time_;
    node_active_time_ = node.node_active_time_;

    planner_      = node.planner_;
    planner_type_ = node.planner_type_;
  }
}

ExecutionNode::~ExecutionNode()
{
  fb_ = nullptr;
}

void ExecutionNode::setBasicParams(FbAxisNode* fb, MC_MOTION_MODE mode,
                                   mcLREAL position, mcLREAL velocity,
                                   mcLREAL acceleration, mcLREAL deceleration,
                                   mcLREAL jerk, MC_BUFFER_MODE buffer_mode,
                                   PLANNER_TYPE planner_type)
{
  fb_           = fb;
  motion_mode_  = mode;
  position_     = position;
  velocity_     = velocity;
  acceleration_ = acceleration;
  deceleration_ = deceleration;
  jerk_         = jerk;
  duration_     = 1000000.0;
  buffer_mode_  = buffer_mode;
  planner_type_ = planner_type;
}

void ExecutionNode::setAdvancedParams(mcLREAL duration, mcLREAL start_pos,
                                      mcLREAL start_vel, mcLREAL start_acc,
                                      mcLREAL end_pos, mcLREAL end_vel,
                                      mcLREAL end_acc)
{
  if (duration == 0)
    onError(mcErrorCodeDurationSetValueError);
  else
    duration_ = duration;

  start_pos_ = start_pos;
  start_vel_ = start_vel;
  start_acc_ = start_acc;
  end_pos_   = end_pos;
  end_vel_   = end_vel;
  end_acc_   = end_acc;
}

void ExecutionNode::setFrequency(mcLREAL f)
{
  planner_.setFrequency(f);
  node_freq_       = f;
  node_delta_time_ = 1 / f;
}

void ExecutionNode::reset()
{
  done_            = mcFALSE;
  busy_            = mcFALSE;
  active_          = mcFALSE;
  command_aborted_ = mcFALSE;
  error_           = mcFALSE;
  error_id_        = mcErrorCodeGood;

  start_pos_       = 0;
  end_pos_         = 0;
  start_vel_       = 0;
  end_vel_         = 0;
  start_acc_       = 0;
  end_acc_         = 0;
  duration_        = 1000000.0;
  pos_cmd_         = 0;
  vel_cmd_         = 0;
  acc_cmd_         = 0;
  pos_tmp_         = 0;
  vel_tmp_         = 0;
  acc_tmp_         = 0;
  need_plan_       = mcFALSE;
  motion_mode_     = mcNoMoveType;
  node_freq_       = 1000;
  node_delta_time_ = 0.001;

  fb_           = nullptr;
  position_     = 0;
  velocity_     = 0;
  acceleration_ = 0;
  deceleration_ = 0;
  jerk_         = 0;
  buffer_mode_  = mcAborting;
}

void ExecutionNode::restart()
{
  active_          = mcFALSE;
  done_            = mcFALSE;
  busy_            = mcFALSE;
  command_aborted_ = mcFALSE;
  error_           = mcFALSE;
  error_id_        = mcErrorCodeGood;
}

void ExecutionNode::setStartPos(mcLREAL pos)
{
  start_pos_ = pos;
  pos_tmp_   = pos;
  pos_cmd_   = pos;
}

void ExecutionNode::setStartVel(mcLREAL vel)
{
  start_vel_ = vel;
  vel_tmp_   = vel;
  vel_cmd_   = vel;
}

void ExecutionNode::setStartAcc(mcLREAL acc)
{
  start_acc_ = acc;
  acc_tmp_   = acc;
  acc_cmd_   = acc;
}

void ExecutionNode::setEndAcc(mcLREAL acc)
{
  end_acc_ = acc;
}

void ExecutionNode::setTerminateCondition(mcLREAL ref_pos)
{
  switch (motion_mode_)
  {
    case mcMoveAbsoluteMode: {
      end_pos_ = position_;
      end_vel_ = 0.0;
    }
    break;
    case mcMoveRelativeMode: {
      end_pos_ = start_pos_ + position_;
      end_vel_ = 0.0;
      // printf("start_pos_: %f, end_pos_: %f\n", start_pos_, end_pos_);
    }
    break;
    case mcMoveAdditiveMode: {
      end_pos_ = ref_pos + position_;
      end_vel_ = 0.0;
    }
    break;
    case mcMoveChaseMode: {
      end_pos_ = fb_->getTargetPosition();
      end_vel_ = fb_->getTargetVelocity();
    }
    break;
    case mcHaltMode:
    case mcStopMode: {
      end_pos_ = NAN;
      end_vel_ = 0.0;
    }
    break;
    case mcGearInMode:
    case mcSyncOutMode:
    case mcMoveVelocityMode: {
      end_pos_ = NAN;
      end_vel_ = velocity_;
    }
    break;
    case mcHomingMode: {
      end_pos_ = position_;
      end_vel_ = isnan(position_) ? velocity_ : 0.0;
    }
    break;
    case mcCamInMode:
    case mcGearInPosMode:
      break;
    case mcMoveSupMode:
      end_pos_ = position_;
      break;
    default:
      break;
  }
}

void ExecutionNode::setEndVel(mcLREAL vel)
{
  end_vel_ = vel;
}

void ExecutionNode::setEndPos(mcLREAL pos)
{
  end_pos_ = pos;
}

void ExecutionNode::setReplan()
{
  need_plan_ = mcTRUE;
}

void ExecutionNode::setVelocity(mcLREAL velocity)
{
  velocity_ = velocity;
}

void ExecutionNode::offsetFB(mcLREAL home_pos)
{
  start_pos_ = pos_cmd_;
  start_vel_ = vel_cmd_;
  start_acc_ = acc_cmd_;
  end_pos_   = end_pos_ + home_pos;
}

void ExecutionNode::setPosDoneFactor(mcLREAL factor)
{
  pos_done_factor_ = factor;
}

void ExecutionNode::setVelDoneFactor(mcLREAL factor)
{
  vel_done_factor_ = factor;
}

MC_BUFFER_MODE ExecutionNode::getBufferMode()
{
  return buffer_mode_;
}

MC_MOTION_MODE ExecutionNode::getMotionMode()
{
  return motion_mode_;
}

mcLREAL ExecutionNode::getEndPos()
{
  return end_pos_;
}

mcLREAL ExecutionNode::getEndVel()
{
  return end_vel_;
}

mcLREAL ExecutionNode::getEndAcc()
{
  return end_acc_;
}

mcLREAL ExecutionNode::getVelocity()
{
  return velocity_;
}

void ExecutionNode::getCommands(mcLREAL* pos_cmd, mcLREAL* vel_cmd,
                                mcLREAL* acc_cmd)
{
  switch (motion_mode_)
  {
    case mcMoveSupMode:
    case mcMoveAbsoluteMode:
    case mcMoveAdditiveMode:
    case mcMoveRelativeMode:
    case mcMoveChaseMode:
    case mcCamInMode:
    case mcGearInPosMode: {
      pos_cmd_ = pos_tmp_;
      if (done_ == mcTRUE)
        vel_cmd_ = 0.0;
      else
        vel_cmd_ = vel_tmp_;
    }
    break;
    case mcHaltMode:
    case mcStopMode:
    case mcGearInMode:
    case mcSyncOutMode:
    case mcMoveVelocityMode: {
      vel_cmd_ = vel_tmp_;
      pos_cmd_ += vel_tmp_ * node_delta_time_;
    }
    break;
    case mcHomingMode: {
      if (isnan(position_))
      {
        vel_cmd_ = vel_tmp_;
        pos_cmd_ += vel_tmp_ * node_delta_time_;
      }
      else
      {
        pos_cmd_ = pos_tmp_;
        vel_cmd_ = vel_tmp_;
      }
    }
    break;
    default:
      break;
  }
  *pos_cmd = pos_cmd_;
  *vel_cmd = vel_cmd_;
  *acc_cmd = acc_tmp_;
}

mcBOOL ExecutionNode::isActive()
{
  return active_;
}

mcBOOL ExecutionNode::isDone()
{
  return done_;
}

mcBOOL ExecutionNode::isAborted()
{
  return command_aborted_;
}

mcBOOL ExecutionNode::isError()
{
  return error_;
}

void ExecutionNode::onActive(MC_AXIS_STATES* current_state)
{
  setPlannerStartTime(0);
  node_active_time_ = 0;
  MC_ERROR_CODE res = mcErrorCodeGood;
  switch (motion_mode_)
  {
    case mcHaltMode:
    case mcMoveAbsoluteMode:
    case mcMoveAdditiveMode:
    case mcMoveRelativeMode: {
      res = changeAxisStates(current_state, mcDiscreteMotion);
    }
    break;
    case mcMoveVelocityMode: {
      res = changeAxisStates(current_state, mcContinuousMotion);
      DEBUG_PRINT("ExecutionNode::onActive %d\n", res);
    }
    break;
    case mcStopMode: {
      res = changeAxisStates(current_state, mcStopping);
    }
    break;
    case mcHomingMode: {
      res = changeAxisStates(current_state, mcHoming);
    }
    break;
    case mcCamInMode:
    case mcGearInMode:
    case mcMoveChaseMode:
    case mcGearInPosMode: {
      res = changeAxisStates(current_state, mcSynchronizedMotion);
    }
    break;
    case mcSyncOutMode: {
      res = changeAxisStates(current_state, mcContinuousMotion);
    }
    break;
    default:
      break;
  }

  if (res)
    onError(mcErrorCodeAxisStateViolation);
  else
  {
    active_ = busy_ = mcTRUE;
    done_ = command_aborted_ = error_ = mcFALSE;
    fb_->syncStatus(done_, busy_, active_, command_aborted_, error_, error_id_);
  }
}

void ExecutionNode::onExecution(mcLREAL master_ref_pos, mcLREAL master_ref_vel)
{
  node_active_time_ += node_delta_time_;
  // Replan trajectory
  if (need_plan_ == mcTRUE)
  {
    need_plan_ = mcFALSE;
    planner_.setCondition(
        start_pos_, end_pos_, start_vel_, end_vel_ * override_factors_.vel,
        start_acc_, end_acc_, duration_, velocity_ * override_factors_.vel,
        acceleration_ * override_factors_.acc, jerk_ * override_factors_.jerk,
        planner_type_);
    DEBUG_PRINT(
        "ExecutionNode::onExecution:"
        "start_pos_ %f, end_pos_ %f, start_vel_ %f, end_vel_ %f,"
        "velocity_ %f, acceleration_ %f, jerk_ %f\n",
        start_pos_, end_pos_, start_vel_, end_vel_ * override_factors_.vel,
        velocity_ * override_factors_.vel,
        acceleration_ * override_factors_.acc, jerk_ * override_factors_.jerk);
    MC_ERROR_CODE res = planner_.onReplan();
    if (res)
      onError(res);
  }

  // Compute waypoint
  if (planner_.getType() == mcPoly5 || planner_.getType() == mcLine)
    error_id_ =
        planner_.onExecution(master_ref_pos, &pos_tmp_, &vel_tmp_, &acc_tmp_);
  else
    error_id_ = planner_.onExecution(node_active_time_, &pos_tmp_, &vel_tmp_,
                                     &acc_tmp_);

  DEBUG_PRINT("ExecutionNode::onExecution: pos: %f, vel: %f, acc: %f\n",
              pos_tmp_, vel_tmp_, acc_tmp_);

  if ((planner_.getType() == mcPoly5 || planner_.getType() == mcLine) &&
      (abs(vel_tmp_ * master_ref_vel) > velocity_ * 1.01 ||
       abs(acc_tmp_ * master_ref_vel * master_ref_vel) > acceleration_ * 1.01))
  {
    DEBUG_PRINT("Axis command exceed limitation. vel_cmd : %f, acc_cmd: %f, "
                "v_max: %f, a_max: %f\n",
                vel_tmp_ * master_ref_vel,
                acc_tmp_ * master_ref_vel * master_ref_vel, velocity_,
                acceleration_);
    error_id_ = mcErrorCodeSlaveExceedLimit;
  }

  if (error_id_)
    onError(error_id_);
  else
    fb_->syncStatus(done_, busy_, active_, command_aborted_, error_, error_id_);
}

void ExecutionNode::onDone(MC_AXIS_STATES* current_state)
{
  MC_ERROR_CODE res = mcErrorCodeGood;
  switch (motion_mode_)
  {
    case mcMoveAbsoluteMode:
    case mcMoveAdditiveMode:
    case mcMoveRelativeMode:
    case mcHaltMode:
    case mcHomingMode: {
      res = changeAxisStates(current_state, mcStandstill);
    }
    break;
    case mcMoveVelocityMode:
    case mcSyncOutMode:
      break;  // MoveVelocity will remain mcContinuousMotion state onDone.
    case mcStopMode: {
      if (fb_->isEnabled() == mcTRUE)
        res = changeAxisStates(current_state, mcStopping);
      else
        res = changeAxisStates(current_state, mcStandstill);
    }
    break;
    default:
      break;
  }

  if (res)
    onError(res);
  else
  {
    done_   = mcTRUE;
    active_ = busy_ = command_aborted_ = error_ = mcFALSE;
    fb_->syncStatus(done_, busy_, active_, command_aborted_, error_, error_id_);
  }
  DEBUG_PRINT("ExecutionNode::onDone %s, mode %d\n",
              fb_->isDone() == mcTRUE ? "mcTRUE" : "mcFALSE", motion_mode_);
}

void ExecutionNode::onCommandAborted()
{
  command_aborted_ = mcTRUE;
  active_ = busy_ = done_ = error_ = mcFALSE;
  fb_->syncStatus(done_, busy_, active_, command_aborted_, error_, error_id_);
}

void ExecutionNode::onError(MC_ERROR_CODE error_code)
{
  error_  = mcTRUE;
  active_ = busy_ = done_ = command_aborted_ = mcFALSE;
  error_id_                                  = error_code;
  fb_->syncStatus(done_, busy_, active_, command_aborted_, error_, error_id_);
  DEBUG_PRINT("ExecutionNode::onError %s\n",
              fb_->isError() == mcTRUE ? "mcTRUE" : "mcFALSE");
}

mcBOOL ExecutionNode::checkMissionDone(const mcLREAL axis_pos,
                                       const mcLREAL axis_vel)
{
  mcBOOL res = mcFALSE;
  switch (motion_mode_)
  {
    case mcMoveAbsoluteMode:
    case mcMoveAdditiveMode:
    case mcMoveRelativeMode: {
      if (fabs(axis_pos - end_pos_) <= pos_done_factor_ &&
          fabs(axis_vel - end_vel_ * override_factors_.vel) <= vel_done_factor_)
        res = mcTRUE;
      DEBUG_PRINT("ExecutionNode::checkMissionDone: \n"
                  "\tfabs(axis_pos - end_pos_): %f, pos_done_factor_: %f, \n"
                  "\tfabs(axis_vel - end_vel_): %f, vel_done_factor_: %f\n",
                  fabs(axis_pos - end_pos_), pos_done_factor_,
                  fabs(axis_vel - end_vel_ * override_factors_.vel),
                  vel_done_factor_);
    }
    break;
    case mcHaltMode:
    case mcStopMode:
    case mcGearInMode:
    case mcSyncOutMode:
    case mcMoveVelocityMode: {
      if (fabs(axis_vel - end_vel_ * override_factors_.vel) <= vel_done_factor_)
        res = mcTRUE;
    }
    break;
    case mcHomingMode: {
      if (isnan(position_))
      {
        if (fabs(axis_vel - end_vel_ * override_factors_.vel) <=
            vel_done_factor_)
          res = mcTRUE;
      }
      else
      {
        if (fabs(axis_pos - end_pos_) <= pos_done_factor_ &&
            fabs(axis_vel - end_vel_ * override_factors_.vel) <=
                vel_done_factor_)
          res = mcTRUE;
        DEBUG_PRINT("ExecutionNode::checkMissionDone: \n"
                    "\tfabs(axis_pos - end_pos_): %f, fabs(start_pos_ -  "
                    "end_pos_) * 0.015: %f, \n"
                    "\tfabs(axis_vel - end_vel_): %f, __EPSILON: %f\n",
                    fabs(axis_pos - end_pos_), pos_done_factor_,
                    fabs(axis_vel - end_vel_ * override_factors_.vel),
                    vel_done_factor_);
      }
    }
    break;
    default:
      break;
  }
  return res;
}

void ExecutionNode::updateOverrideFactors(OverrideFactors& override_factors)
{
  override_factors_.vel           = override_factors.vel;
  override_factors_.acc           = override_factors.acc;
  override_factors_.jerk          = override_factors.jerk;
  override_factors_.override_flag = override_factors.override_flag;
  switch (motion_mode_)
  {
    case mcStopMode:
    case mcHomingMode:
    case mcCamInMode:
    case mcGearInMode:
    case mcMoveChaseMode:
    case mcGearInPosMode:
    case mcSyncOutMode: {
      override_factors_.vel = override_factors_.acc = override_factors_.jerk =
          1;
    }
    break;
    default:
      break;
  }
}

void ExecutionNode::setPlannerStartTime(mcLREAL t)
{
  planner_.setStartTime(t);
}

MC_ERROR_CODE ExecutionNode::changeAxisStates(MC_AXIS_STATES* current_state,
                                              MC_AXIS_STATES set_state)
{
  switch (*current_state)
  {
    case mcDisabled:
    case mcErrorStop: {
      return mcErrorCodeAxisStateViolation;
    }
    break;
    case mcStandstill:
      switch (set_state)
      {
        case mcErrorStop:
        case mcStandstill:
        case mcHoming:
        case mcStopping:
        case mcDiscreteMotion:
        case mcContinuousMotion:
        case mcSynchronizedMotion: {
          *current_state = set_state;
          return mcErrorCodeGood;
        }
        break;
        default:
          return mcErrorCodeAxisStateViolation;
          break;
      }
      break;
    case mcHoming:
      switch (set_state)
      {
        case mcErrorStop:
        case mcHoming:
        case mcStopping:
        case mcStandstill: {
          *current_state = set_state;
          return mcErrorCodeGood;
        }
        break;
        default:
          return mcErrorCodeAxisStateViolation;
          break;
      }
      break;
    case mcStopping:
      switch (set_state)
      {
        case mcErrorStop:
        case mcStopping:
        case mcStandstill: {
          *current_state = set_state;
          return mcErrorCodeGood;
        }
        break;
        default:
          return mcErrorCodeAxisStateViolation;
          break;
      }
      break;
    case mcDiscreteMotion:
      switch (set_state)
      {
        case mcErrorStop:
        case mcStopping:
        case mcStandstill:
        case mcDiscreteMotion:
        case mcContinuousMotion:
        case mcSynchronizedMotion: {
          *current_state = set_state;
          return mcErrorCodeGood;
        }
        break;
        default:
          return mcErrorCodeAxisStateViolation;
          break;
      }
      break;
    case mcContinuousMotion:
      switch (set_state)
      {
        case mcErrorStop:
        case mcStopping:
        case mcContinuousMotion:
        case mcDiscreteMotion:
        case mcSynchronizedMotion: {
          *current_state = set_state;
          return mcErrorCodeGood;
        }
        break;
        default:
          return mcErrorCodeAxisStateViolation;
          break;
      }
      break;
    case mcSynchronizedMotion:
      switch (set_state)
      {
        case mcErrorStop:
        case mcStopping:
        case mcContinuousMotion:
        case mcDiscreteMotion:
        case mcSynchronizedMotion: {
          *current_state = set_state;
          return mcErrorCodeGood;
        }
        break;
        default:
          return mcErrorCodeAxisStateViolation;
          break;
      }
      break;
    default:
      break;
  }
  return mcErrorCodeGood;
}

FbAxisNode* ExecutionNode::getAxisNodeInstance()
{
  return fb_;
}

PLANNER_TYPE ExecutionNode::getPlannerType()
{
  return planner_type_;
}

}  // namespace RTmotion
