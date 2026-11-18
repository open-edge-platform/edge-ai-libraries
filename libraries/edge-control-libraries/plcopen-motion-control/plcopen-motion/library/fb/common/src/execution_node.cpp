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
  , blend_replan_position_(NAN)
  , blend_resume_position_(NAN)
  , blend_resume_velocity_(0)
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

    node_freq_             = node.node_freq_;
    node_delta_time_       = node.node_delta_time_;
    node_active_time_      = node.node_active_time_;
    gear_synchronized_     = node.gear_synchronized_;
    stopping_on_error_     = node.stopping_on_error_;
    last_master_ref_acc_   = node.last_master_ref_acc_;
    blend_replan_position_ = node.blend_replan_position_;
    blend_resume_position_ = node.blend_resume_position_;
    blend_resume_velocity_ = node.blend_resume_velocity_;

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
  // Reset motion state, retaining the axis-configured cycle time.
  gear_synchronized_   = mcFALSE;
  stopping_on_error_   = mcFALSE;
  last_master_ref_acc_ = 0;
  done_                = mcFALSE;
  busy_                = mcFALSE;
  active_              = mcFALSE;
  command_aborted_     = mcFALSE;
  error_               = mcFALSE;
  error_id_            = mcErrorCodeGood;

  start_pos_             = 0;
  end_pos_               = 0;
  start_vel_             = 0;
  end_vel_               = 0;
  start_acc_             = 0;
  end_acc_               = 0;
  duration_              = 1000000.0;
  pos_cmd_               = 0;
  vel_cmd_               = 0;
  acc_cmd_               = 0;
  pos_tmp_               = 0;
  vel_tmp_               = 0;
  acc_tmp_               = 0;
  need_plan_             = mcFALSE;
  motion_mode_           = mcNoMoveType;
  blend_replan_position_ = NAN;
  blend_resume_position_ = NAN;
  blend_resume_velocity_ = 0;

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

void ExecutionNode::prepareBlendEntry(mcLREAL position, mcLREAL velocity,
                                      mcLREAL acceleration)
{
  if (motion_mode_ == mcGearInPosMode)
  {
    // Keep the polynomial's displacement derivatives separate from axis state.
    pos_cmd_ = pos_tmp_ = position;
    vel_cmd_ = vel_tmp_ = velocity;
    acc_cmd_ = acc_tmp_ = acceleration;
    return;
  }
  setStartPos(position);
  setStartVel(velocity);
  setStartAcc(acceleration);

  const mcLREAL velocity_delta = fabs(velocity) - fabs(velocity_);
  if (planner_type_ != mcRuckig || isnan(end_pos_) || velocity_delta <= 0.0)
    return;

  // First decelerate to the commanded cruise velocity. Planning directly to
  // the final target with a lower velocity limit can undershoot that velocity.
  const mcLREAL ramp_velocity = acceleration_ * acceleration_ / jerk_;
  const mcLREAL transition_duration =
      velocity_delta >= ramp_velocity ?
          velocity_delta / acceleration_ + acceleration_ / jerk_ :
          2.0 * sqrt(velocity_delta / jerk_);
  const mcLREAL cruise_velocity = copysign(fabs(velocity_), velocity);
  const mcLREAL transition_distance =
      (fabs(velocity) + fabs(cruise_velocity)) * 0.5 * transition_duration;
  const mcLREAL direction = end_pos_ >= position ? 1.0 : -1.0;

  blend_resume_position_ = end_pos_;
  blend_resume_velocity_ = end_vel_;
  velocity_              = fabs(velocity);
  // Leave one command cycle after the theoretical transition distance so the
  // temporary trajectory reaches a stable cruise velocity before resuming.
  end_pos_ = position + direction * (transition_distance +
                                     fabs(cruise_velocity) * node_delta_time_);
  end_vel_ = cruise_velocity;
}

void ExecutionNode::scheduleBlendReplan(mcLREAL current_position,
                                        mcLREAL current_velocity,
                                        mcLREAL end_velocity)
{
  // Delay acceleration until the last jerk-limited transition that can reach
  // the requested blend velocity at the existing endpoint.
  const mcLREAL velocity_delta = fabs(end_velocity) - fabs(current_velocity);
  const mcLREAL ramp_velocity  = acceleration_ * acceleration_ / jerk_;
  const mcLREAL transition_duration =
      velocity_delta >= ramp_velocity ?
          velocity_delta / acceleration_ + acceleration_ / jerk_ :
          2.0 * sqrt(velocity_delta / jerk_);
  const mcLREAL transition_distance =
      (fabs(current_velocity) + fabs(end_velocity)) * 0.5 * transition_duration;
  const mcLREAL direction = end_pos_ >= current_position ? 1.0 : -1.0;
  blend_replan_position_ =
      end_pos_ -
      direction * (transition_distance + fabs(end_velocity) * node_delta_time_);
  end_vel_  = end_velocity;
  velocity_ = std::max(velocity_, fabs(end_velocity));
}

void ExecutionNode::applyBlendReplanIfDue(mcLREAL position, mcLREAL velocity,
                                          mcLREAL acceleration)
{
  if (!isnan(blend_resume_position_))
  {
    const bool entry_complete = start_pos_ <= end_pos_ ? position >= end_pos_ :
                                                         position <= end_pos_;
    if (entry_complete)
    {
      // Continue from the measured state to the original final target.
      velocity_              = fabs(end_vel_);
      end_pos_               = blend_resume_position_;
      end_vel_               = blend_resume_velocity_;
      blend_resume_position_ = NAN;
      setStartPos(position);
      setStartVel(velocity);
      setStartAcc(acceleration);
      setReplan();
    }
  }

  if (isnan(blend_replan_position_))
    return;
  const bool position_reached = start_pos_ <= end_pos_ ?
                                    position >= blend_replan_position_ :
                                    position <= blend_replan_position_;
  if (!position_reached)
    return;
  // Start the outgoing blend from the measured state at the deferred trigger.
  blend_replan_position_ = NAN;
  setStartPos(position);
  setStartVel(velocity);
  setStartAcc(acceleration);
  setReplan();
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
      if ((motion_mode_ == mcMoveVelocityMode && done_ == mcFALSE) ||
          motion_mode_ == mcStopMode ||
          (motion_mode_ == mcGearInMode && fb_->isPositionCoupled() == mcTRUE))
        pos_cmd_ = pos_tmp_;
      else
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
  if (motion_mode_ == mcGearInPosMode)
    acc_cmd_ = acc_tmp_;
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

mcBOOL ExecutionNode::isStoppingOnError() const
{
  return stopping_on_error_;
}

mcBOOL ExecutionNode::isGearSynchronized() const
{
  return motion_mode_ == mcGearInMode && gear_synchronized_ == mcTRUE &&
                 active_ == mcTRUE && error_ == mcFALSE &&
                 command_aborted_ == mcFALSE &&
                 fb_->isReadyForBufferedHandoff() == mcTRUE ?
             mcTRUE :
             mcFALSE;
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
  if (stopping_on_error_ == mcTRUE)
  {
    runErrorStop();
    return;
  }
  if (motion_mode_ == mcMoveVelocityMode || motion_mode_ == mcStopMode)
  {
    need_plan_                    = mcFALSE;
    planner_type_                 = mcRuckig;
    const mcLREAL target_velocity = end_vel_ * override_factors_.vel;
    const bool reversing          = vel_cmd_ * target_velocity < 0;
    const mcLREAL direction       = vel_cmd_ != 0 ? vel_cmd_ : target_velocity;
    const mcLREAL acceleration    = acceleration_ * override_factors_.acc;
    const mcLREAL deceleration    = motion_mode_ == mcStopMode ?
                                        acceleration :
                                        deceleration_ * override_factors_.acc;
    const mcLREAL upper = direction >= 0 ? acceleration : deceleration;
    const mcLREAL lower = direction >= 0 ? -deceleration : -acceleration;
    // Brake to rest before swapping directional acceleration limits.
    planner_.setCondition(pos_cmd_, NAN, vel_cmd_,
                          reversing ? 0 : target_velocity, acc_tmp_, 0,
                          duration_, target_velocity, upper,
                          jerk_ * override_factors_.jerk, mcRuckig);
    const MC_ERROR_CODE result = planner_.onVelocityTracking(
        node_delta_time_, &pos_tmp_, &vel_tmp_, &acc_tmp_, lower);
    if (result != mcErrorCodeGood)
      onError(result);
    else if (reversing && fabs(vel_tmp_) < 1e-12 && fabs(acc_tmp_) < 1e-12)
      vel_tmp_ = acc_tmp_ = 0;
    return;
  }
  if (motion_mode_ == mcGearInPosMode && fb_->isPositionCoupled() == mcTRUE)
  {
    // Acquisition and following are phases of the same command, not an abort.
    motion_mode_ = mcGearInMode;
  }
  if (motion_mode_ == mcGearInMode)
  {
    if (fb_->isError() != mcFALSE)
    {
      onError(fb_->getErrorID());
      return;
    }
    if (fb_->isPositionCoupled() == mcTRUE)
    {
      pos_tmp_           = fb_->getTargetPosition();
      vel_tmp_           = fb_->getTargetVelocity();
      acc_tmp_           = fb_->getTargetAcceleration();
      gear_synchronized_ = mcTRUE;
      fb_->syncStatus(done_, busy_, active_, command_aborted_, error_,
                      error_id_);
      return;
    }
    const mcLREAL target_velocity = fb_->getVelocity();
    const mcLREAL following_acceleration =
        (target_velocity - vel_cmd_) / node_delta_time_;
    const mcLREAL target_acceleration =
        (target_velocity - end_vel_) / node_delta_time_;
    // A moving target needs a velocity/acceleration match, not equality with
    // its previous sample. Check both entry jerk and the target's trend so a
    // near-target ramp cannot be truncated into an acceleration spike.
    const mcLREAL direction        = vel_cmd_ != 0 ? vel_cmd_ : target_velocity;
    const mcLREAL max_acceleration = direction >= 0 ? acceleration_ :
                                                      deceleration_;
    const mcLREAL min_acceleration = direction >= 0 ? -deceleration_ :
                                                      -acceleration_;
    const bool reversing           = vel_cmd_ * target_velocity < 0;
    const mcLREAL acceleration_step = jerk_ * node_delta_time_;
    if (!reversing && following_acceleration <= max_acceleration &&
        following_acceleration >= min_acceleration &&
        fabs(following_acceleration - acc_tmp_) <= acceleration_step &&
        fabs(following_acceleration - target_acceleration) <= acceleration_step)
      gear_synchronized_ = mcTRUE;
    if (gear_synchronized_ == mcTRUE)
    {
      // Engagement limits no longer shape the coupled velocity. Axis safety
      // checks still apply; distance lost during engagement is not recovered.
      acc_tmp_ = (target_velocity - vel_cmd_) / node_delta_time_;
      vel_tmp_ = target_velocity;
      fb_->syncStatus(done_, busy_, active_, command_aborted_, error_,
                      error_id_);
      return;
    }
    end_vel_ = velocity_ = target_velocity;
    planner_type_        = mcRuckig;
    need_plan_           = mcFALSE;
    // Bound the requested terminal acceleration when the master exceeds the
    // slave's engagement capability; the planner still preserves continuity.
    // Finish braking at zero acceleration before swapping directional limits.
    const mcLREAL ramp_velocity = reversing ? 0 : target_velocity;
    const mcLREAL end_acceleration =
        reversing || ramp_velocity == 0 ?
            0 :
            std::max(min_acceleration,
                     std::min(target_acceleration, max_acceleration));
    planner_.setCondition(pos_cmd_, NAN, vel_cmd_, ramp_velocity, acc_tmp_,
                          end_acceleration, duration_, target_velocity,
                          max_acceleration, jerk_, planner_type_);
    const MC_ERROR_CODE result = planner_.onVelocityTracking(
        node_delta_time_, &pos_tmp_, &vel_tmp_, &acc_tmp_, min_acceleration);
    if (result != mcErrorCodeGood)
      onError(result);
    else
    {
      // Remove roundoff at the zero-speed reversal boundary.
      if (reversing && fabs(vel_tmp_) < 1e-12 && fabs(acc_tmp_) < 1e-12)
        vel_tmp_ = acc_tmp_ = 0;
      fb_->syncStatus(done_, busy_, active_, command_aborted_, error_,
                      error_id_);
    }
    return;
  }
  mcLREAL master_ref_acc = 0;
  if (motion_mode_ == mcGearInPosMode)
  {
    if (fb_->isError() != mcFALSE)
    {
      startGearInPosErrorStop(fb_->getErrorID());
      return;
    }
    // Sample at slave execution time, not from the previous FB cycle.
    fb_->getMasterReference(master_ref_pos, master_ref_vel, master_ref_acc);
    if (need_plan_ == mcTRUE)
      last_master_ref_acc_ = master_ref_acc;
  }
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
    {
      if (motion_mode_ == mcGearInPosMode)
      {
        startGearInPosErrorStop(res);
        return;
      }
      onError(res);
    }
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

  if (motion_mode_ == mcGearInPosMode)
  {
    mcLREAL displacement_jerk =
        planner_.getTrajectoryPoint(master_ref_pos)[mcJerkId];
    if (master_ref_pos >= duration_)
    {
      // Extend the terminal tangent when a sample crosses the sync point.
      pos_tmp_          = end_pos_ + end_vel_ * (master_ref_pos - duration_);
      vel_tmp_          = end_vel_;
      acc_tmp_          = end_acc_;
      displacement_jerk = 0;
    }
    const mcLREAL master_jerk =
        (master_ref_acc - last_master_ref_acc_) / node_delta_time_;
    const mcLREAL slave_jerk =
        displacement_jerk * master_ref_vel * master_ref_vel * master_ref_vel +
        3 * acc_tmp_ * master_ref_vel * master_ref_acc + vel_tmp_ * master_jerk;
    acc_tmp_ =
        acc_tmp_ * master_ref_vel * master_ref_vel + vel_tmp_ * master_ref_acc;
    vel_tmp_ *= master_ref_vel;
    const mcLREAL acceleration_limit = vel_tmp_ * acc_tmp_ < 0 ? deceleration_ :
                                                                 acceleration_;
    const mcLREAL sampled_acceleration =
        (vel_tmp_ - vel_cmd_) / node_delta_time_;
    const mcLREAL sampled_limit =
        vel_cmd_ * sampled_acceleration < 0 ? deceleration_ : acceleration_;
    const mcLREAL sampled_jerk = (acc_tmp_ - acc_cmd_) / node_delta_time_;
    // Leave enough velocity headroom to remove outward acceleration with
    // bounded jerk if the following sample requires an error stop.
    const mcLREAL outward_acceleration =
        vel_tmp_ * acc_tmp_ > 0 ? fabs(acc_tmp_) : 0;
    const mcLREAL braking_peak_velocity =
        fabs(vel_tmp_) +
        outward_acceleration * outward_acceleration / (2 * jerk_);
    const mcLREAL tolerance = 1e-9;
    if (!std::isfinite(pos_tmp_) || !std::isfinite(vel_tmp_) ||
        !std::isfinite(acc_tmp_) || !std::isfinite(slave_jerk) ||
        braking_peak_velocity > velocity_ + tolerance ||
        fabs(acc_tmp_) > acceleration_limit + tolerance ||
        fabs(sampled_acceleration) > sampled_limit + tolerance ||
        fabs(slave_jerk) > jerk_ + tolerance ||
        fabs(sampled_jerk) > jerk_ + tolerance)
      error_id_ = mcErrorCodeSlaveExceedLimit;
    if (error_id_ != mcErrorCodeGood)
    {
      startGearInPosErrorStop(error_id_);
      return;
    }
    last_master_ref_acc_ = master_ref_acc;
  }
  else if ((planner_.getType() == mcPoly5 || planner_.getType() == mcLine) &&
           (abs(vel_tmp_ * master_ref_vel) > velocity_ * 1.01 ||
            abs(acc_tmp_ * master_ref_vel * master_ref_vel) >
                acceleration_ * 1.01))
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

void ExecutionNode::startGearInPosErrorStop(MC_ERROR_CODE error_code)
{
  stopping_on_error_ = mcTRUE;
  error_             = mcTRUE;
  error_id_          = error_code;
  active_ = busy_ = mcTRUE;
  done_ = command_aborted_ = mcFALSE;
  need_plan_               = mcFALSE;
  // Discard the rejected waypoint before computing this cycle's stop command.
  pos_tmp_ = pos_cmd_;
  vel_tmp_ = vel_cmd_;
  acc_tmp_ = acc_cmd_;
  runErrorStop();
}

void ExecutionNode::runErrorStop()
{
  planner_.setCondition(pos_cmd_, NAN, vel_cmd_, 0, acc_cmd_, 0, duration_,
                        velocity_, deceleration_, jerk_, mcRuckig);
  const MC_ERROR_CODE result = planner_.onVelocityTracking(
      node_delta_time_, &pos_tmp_, &vel_tmp_, &acc_tmp_);
  if (result != mcErrorCodeGood)
  {
    DEBUG_PRINT("GearInPos controlled stop failed: %d\n", result);
    onError(result);
    return;
  }
  if (fabs(vel_tmp_) < 1e-12 && fabs(acc_tmp_) < 1e-12)
  {
    vel_tmp_ = acc_tmp_ = 0;
    done_               = mcTRUE;
  }
  // Error terminates the user's command; the node owns the stop internally.
  fb_->syncStatus(mcFALSE, mcFALSE, mcFALSE, mcFALSE, mcTRUE, error_id_);
}

void ExecutionNode::rebaseErrorStop(mcLREAL position, mcLREAL velocity,
                                    mcLREAL acceleration)
{
  pos_cmd_ = position;
  vel_cmd_ = velocity;
  acc_cmd_ = acceleration;
  done_    = mcFALSE;
  active_ = busy_ = mcTRUE;
  runErrorStop();
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
      // The ramp has finished; hold the exact target rather than feedback
      // accepted within the completion tolerance.
      vel_tmp_ = end_vel_ * override_factors_.vel;
      acc_tmp_ = 0;
      break;
    case mcSyncOutMode:
      break;  // GearOut keeps its captured velocity and continuous-motion
              // state.
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
  // Done ends finite motions, but velocity-mode completion only ends the ramp.
  if (done_ == mcTRUE && motion_mode_ != mcMoveVelocityMode &&
      motion_mode_ != mcSyncOutMode &&
      !(motion_mode_ == mcHomingMode && isnan(position_)))
    return;

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
      const bool position_reached =
          start_pos_ <= end_pos_ ? axis_pos >= end_pos_ - pos_done_factor_ :
                                   axis_pos <= end_pos_ + pos_done_factor_;
      if (position_reached &&
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
    case mcSyncOutMode: {
      if (fabs(axis_vel - end_vel_ * override_factors_.vel) <= vel_done_factor_)
        res = mcTRUE;
    }
    break;
    case mcMoveVelocityMode:
    case mcStopMode: {
      // Feedback tolerance must not truncate the final jerk-limited samples.
      if (need_plan_ == mcFALSE &&
          fabs(vel_tmp_ - end_vel_ * override_factors_.vel) < 1e-12 &&
          fabs(acc_tmp_) < 1e-12 &&
          fabs(axis_vel - end_vel_ * override_factors_.vel) <= vel_done_factor_)
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
