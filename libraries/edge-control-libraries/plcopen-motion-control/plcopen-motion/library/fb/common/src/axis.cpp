// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file axis.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <fb/common/include/axis.hpp>
#include <algorithm>
#include <fb/common/include/logging.hpp>

namespace RTmotion
{
Axis::Axis()
  : axis_id_(0)
  , axis_pos_(0)
  , axis_vel_(0)
  , axis_torque_(0)
  , axis_mode_(mcServoControlModePosition)
  , axis_home_state_(mcFALSE)
  , axis_acc_(0)
  , axis_jerk_(0)
  , axis_pos_home_(0)
  , axis_pos_cmd_(0)
  , axis_vel_cmd_(0)
  , axis_torque_cmd_(0)
  , axis_max_profile_vel_cmd_(0)
  , axis_home_enable_cmd_(mcFALSE)
  , axis_mode_cmd_(0)
  , axis_acc_cmd_(0)
  , axis_tor_cmd_(0)
  , overflow_count_(0)
  , master_ref_pos_(0)
  , master_ref_vel_(0)
  , axis_state_(mcStandstill)
  , servo_(nullptr)
  , axis_underlying_pos_cmd_(0)
  , axis_underlying_vel_cmd_(0)
  , axis_underlying_acc_cmd_(0)
  , axis_superimposed_enable_(mcFALSE)
  , axis_sup_pos_cmd_(0)
  , axis_sup_vel_cmd_(0)
  , axis_sup_acc_cmd_(0)
  , axis_sup_move_covered_pos_(0)
  , axis_sup_move_total_covered_pos_(0)
  , motion_kernel_()
  , config_(nullptr)
  , stamp_(0)
  , power_on_(mcFALSE)
  , power_status_(mcFALSE)
  , reset_(mcFALSE)
  , enable_positive_(mcFALSE)
  , enable_negative_(mcFALSE)
  , axis_error_(mcErrorCodeGood)
  , node_num_(2)
  , it_(nullptr)
  , axis_home_abs_switch_active_(mcFALSE)
  , axis_limit_switch_pos_active_(mcFALSE)
  , axis_limit_switch_neg_active_(mcFALSE)
  , axis_in_simulation_(mcFALSE)
  , axis_has_warning_(mcFALSE)
{
  delta_time_                          = 0.001;
  axis_override_factors_.vel           = 1;
  axis_override_factors_.acc           = 1;
  axis_override_factors_.jerk          = 1;
  axis_override_factors_.override_flag = mcFALSE;
  superimposed_node_ptr_         = node_buffer_ + NODE_BUFFER_MAX_SIZE - 1;
  superimposed_node_ptr_->taken_ = mcTRUE;
#ifdef ADDR_CHECK
  printf("Axis::axis_id_: %p\n", (void*)&axis_id_);
  printf("Axis::axis_pos_: %p\n", (void*)&axis_pos_);
  printf("Axis::axis_vel_: %p\n", (void*)&axis_vel_);
  printf("Axis::axis_acc_: %p\n", (void*)&axis_acc_);
  printf("Axis::axis_jerk_: %p\n", (void*)&axis_jerk_);
  printf("Axis::axis_pos_cmd_: %p\n", (void*)&axis_pos_cmd_);
  printf("Axis::axis_vel_cmd_: %p\n", (void*)&axis_vel_cmd_);
  printf("Axis::axis_acc_cmd_: %p\n", (void*)&axis_acc_cmd_);
  printf("Axis::axis_tor_cmd_: %p\n", (void*)&axis_tor_cmd_);
  printf("Axis::overflow_count_: %p\n", (void*)&overflow_count_);
  printf("Axis::servo_: %p\n", (void*)servo_);
  printf("Axis::motion_kernel_: %p\n", (void*)&motion_kernel_);
  printf("Axis::config_: %p\n", (void*)&config_);
  printf("Axis::time_start_: %p\n", (void*)&time_start_);
  printf("Axis::time_prev_: %p\n", (void*)&time_prev_);
  printf("Axis::power_on_: %p\n", (void*)&power_on_);
  printf("Axis::power_status_: %p\n", (void*)&power_status_);
  printf("Axis::reset_: %p\n", (void*)&reset_);
  printf("Axis::enable_positive_: %p\n", (void*)&enable_positive_);
  printf("Axis::enable_negative_: %p\n", (void*)&enable_negative_);
  for (size_t i = 0; i < node_num_; i++)
    printf("Axis::node: %p\n", (void*)&node_buffer_[i]);
  printf("Axis::it_: %p\n", (void*)&it_);
#endif
}

Axis::Axis(const Axis& axis)
{
  *this = axis;
}

Axis& Axis::operator=(const Axis& other)
{
  if (this != &other)
  {
    axis_id_                  = other.axis_id_;
    axis_pos_                 = other.axis_pos_;
    axis_vel_                 = other.axis_vel_;
    axis_torque_              = other.axis_torque_;
    axis_mode_                = other.axis_mode_;
    axis_home_state_          = other.axis_home_state_;
    axis_acc_                 = other.axis_acc_;
    axis_jerk_                = other.axis_jerk_;
    axis_pos_home_            = other.axis_pos_home_;
    axis_pos_cmd_             = other.axis_pos_cmd_;
    axis_vel_cmd_             = other.axis_vel_cmd_;
    axis_torque_cmd_          = other.axis_tor_cmd_;
    axis_max_profile_vel_cmd_ = other.axis_max_profile_vel_cmd_;
    axis_home_enable_cmd_     = other.axis_home_enable_cmd_;
    axis_mode_cmd_            = other.axis_mode_cmd_;
    axis_acc_cmd_             = other.axis_acc_cmd_;
    axis_tor_cmd_             = other.axis_tor_cmd_;
    overflow_count_           = other.overflow_count_;
    master_ref_pos_           = other.master_ref_pos_;
    master_ref_vel_           = other.master_ref_vel_;
    axis_state_               = other.axis_state_;
    servo_                    = other.servo_;

    config_ = other.config_;

    stamp_      = other.stamp_;
    delta_time_ = other.delta_time_;

    power_on_        = other.power_on_;
    power_status_    = other.power_status_;
    reset_           = other.reset_;
    enable_positive_ = other.enable_positive_;
    enable_negative_ = other.enable_negative_;

    add_fb_      = other.add_fb_;
    count_       = other.count_;
    add_count_   = other.add_count_;
    servo_mode_  = other.servo_mode_;
    mode_switch_ = other.mode_switch_;

    axis_error_ = other.axis_error_;

    node_num_ =
        other.node_num_;  // size of execution node queue in motion kernel
    it_ = node_buffer_;
  }

  return *this;
}

Axis::~Axis()
{
  // delete servo_; // This object is deleted in other source
  // delete config_; // This object is deleted in other source
  servo_  = nullptr;
  config_ = nullptr;
}

void Axis::deleteServo()
{
  if (servo_ != nullptr)
  {
    delete servo_;
    servo_ = nullptr;
  }
}

void Axis::deleteConfig()
{
  if (config_ != nullptr)
  {
    delete config_;
    config_ = nullptr;
  }
}

mcSINT Axis::axisId()
{
  return axis_id_;
}

void Axis::setAxisId(mcUSINT id)
{
  axis_id_ = id;
}

void Axis::setServo(Servo* servo)
{
  servo_ = servo;
}

Servo* Axis::getServo()
{
  return servo_;
}

void Axis::setAxisConfig(AxisConfig* config)
{
  if (!config)
  {
    printf("Axis::setAxisConfig: config input is null pointer.\n");
    return;
  }

  config_ = config;

  if (config_->frequency_ != 0)
  {
    delta_time_ = 1 / config_->frequency_;
    for (size_t i = 0; i < node_num_; i++)
      node_buffer_[i].setFrequency(config_->frequency_);
  }
}

void Axis::setNodeQueueSize(mcUSINT size)
{
  if (size > NODE_BUFFER_MAX_SIZE)
  {
    INFO_PRINT("Axis::setNodeQueueSize Buffer size cannot be larger than %d.\n",
               NODE_BUFFER_MAX_SIZE);
    return;
  }
  node_num_ = size;
}

void Axis::runCycle()
{
  // Make power operations
  powerProcess();

  // If axis status ok, then do motion calculation
  if (statusHealthy() == mcTRUE)
  {
    // Motion kernel update
    motion_kernel_.runCycle(master_ref_pos_, master_ref_vel_,
                            axis_pos_ - axis_sup_pos_cmd_,
                            axis_vel_cmd_ - axis_sup_vel_cmd_, axis_acc_cmd_,
                            &axis_state_, axis_override_factors_);

    // Sync motion kernel results to axis
    syncMotionKernelResultsToAxis();

    // Axis commands processing
    cmdsProcessing();

    // Update motion commands to servo
    updateMotionCmdsToServo();
  }

  // Servo updates
  servo_->runCycle(config_->frequency_);

  // Sync servo status to axis
  statusSync();

  // Update time stamps
  stamp_ += delta_time_;
  count_++;

  if (add_fb_ == mcTRUE)
    add_count_++;
  if (add_count_ == 100)
  {
    add_fb_    = mcFALSE;
    add_count_ = 0;
  }
}

void Axis::runCycle(double pos, double vel)
{
  // Make power operations
  powerProcess();

  // If axis status ok, then do motion calculation
  if (statusHealthy() == mcTRUE)
  {
    // Sync motion commands
    axis_pos_cmd_ = pos;
    axis_vel_cmd_ = vel;

    // Axis commands processing
    cmdsProcessing();

    // Update motion commands to servo
    updateMotionCmdsToServo();
  }

  // Servo updates
  servo_->runCycle(config_->frequency_);

  // Sync servo status to axis
  statusSync();

  // Update time stamps
  stamp_ += delta_time_;
  count_++;

  if (add_fb_ == mcTRUE)
    add_count_++;
  if (add_count_ == 100)
  {
    add_fb_    = mcFALSE;
    add_count_ = 0;
  }
}

mcLREAL Axis::getPos()
{
  return axis_pos_;
}

mcLREAL Axis::toUserPos()
{
  return axis_pos_ - axis_pos_home_;
}

mcLREAL Axis::getHomePos()
{
  return axis_pos_home_;
}

mcLREAL Axis::toUserVel()
{
  return axis_vel_;
}

mcUSINT Axis::getControllerMode()
{
  return axis_mode_;
}

mcBOOL Axis::getHomeState()
{
  return axis_home_state_;
}

mcLREAL Axis::toUserAcc()
{
  return axis_acc_;
}

mcLREAL Axis::toUserTorque()
{
  return axis_torque_;
}

void Axis::setTorqueCmd(mcLREAL torque)
{
  axis_torque_cmd_ = torque;
}

void Axis::setMaxProfileVelCmd(mcLREAL vel)
{
  axis_max_profile_vel_cmd_ = vel;
}

void Axis::setHomeEnableCmd(mcBOOL enable)
{
  axis_home_enable_cmd_ = enable;
}

mcLREAL Axis::getPosCmd()
{
  return axis_pos_cmd_;
}

mcLREAL Axis::toUserPosCmd()
{
  return axis_pos_cmd_ - axis_pos_home_;
}

mcLREAL Axis::toUserVelCmd()
{
  return axis_vel_cmd_;
}

mcLREAL Axis::toUserAccCmd()
{
  return axis_acc_cmd_;
}

mcLREAL Axis::toUserUnit(mcLREAL x)
{
  DEBUG_PRINT("Axis::toUserUnit: %f\n", x);
  return x / config_->encoder_count_per_unit_;
}

mcDINT Axis::toEncoderUnit(mcLREAL x)
{
  return (mcDINT)fixOverFlow(x * config_->encoder_count_per_unit_);
}

void Axis::addFBToQueue(FbAxisNode* fb, MC_MOTION_MODE mode)
{
  add_fb_ = mcTRUE;
  it_     = nullptr;
  for (size_t i = 0; i < node_num_; i++)
  {
    if (node_buffer_[i].taken_ == mcFALSE)
    {
      it_ = node_buffer_ + i;
      break;
    }
  }

  if (!it_)
  {
    setAxisState(mcErrorStop);
    axis_error_ = mcErrorCodeExceedNodeQueueSize;
    DEBUG_PRINT("All buffer node are occupied, cannot add new FB.\n");
    return;
  }

  DEBUG_PRINT("Debug %ld\n", it_ - node_buffer_);
  (*it_).reset();

  switch (mode)
  {
    case mcMoveAbsoluteMode:
    case mcMoveChaseMode:
      (*it_).setBasicParams(fb, mode, fb->getPosition() + axis_pos_home_,
                            fb->getVelocity(), fb->getAcceleration(),
                            fb->getDeceleration(), fb->getJerk(),
                            fb->getBufferMode(), mcRuckig);
      break;
    case mcMoveAdditiveMode:
    case mcMoveRelativeMode:
      (*it_).setBasicParams(fb, mode, fb->getPosition(), fb->getVelocity(),
                            fb->getAcceleration(), fb->getDeceleration(),
                            fb->getJerk(), fb->getBufferMode(), mcRuckig);
      break;
    case mcMoveVelocityMode:
    case mcGearInMode:
    case mcSyncOutMode:
    case mcHaltMode:
    case mcStopMode:
      (*it_).setBasicParams(fb, mode, NAN, fb->getVelocity(),
                            fb->getAcceleration(), fb->getDeceleration(),
                            fb->getJerk(), fb->getBufferMode(), mcOffLine);
      break;
    case mcHomingMode: {
      if (isnan(fb->getPosition()))
      {
        switch (fb->getDirection())
        {
          case mcPositiveDirection:
            (*it_).setBasicParams(fb, mode, NAN, fabs(fb->getVelocity()),
                                  fb->getAcceleration(), fb->getDeceleration(),
                                  fb->getJerk(), fb->getBufferMode(),
                                  mcOffLine);
            break;
          case mcNegativeDirection:
            (*it_).setBasicParams(fb, mode, NAN, -fabs(fb->getVelocity()),
                                  fb->getAcceleration(), fb->getDeceleration(),
                                  fb->getJerk(), fb->getBufferMode(),
                                  mcOffLine);
            break;
          default:
            break;
        }
      }
      else
      {
        (*it_).setBasicParams(fb, mode, fb->getPosition() + axis_pos_home_,
                              fb->getVelocity(), fb->getAcceleration(),
                              fb->getDeceleration(), fb->getJerk(),
                              fb->getBufferMode(), mcRuckig);
      }
    }
    break;
    case mcCamInMode:
    case mcGearInPosMode: {
      (*it_).setBasicParams(fb, mode, fb->getPosition() + axis_pos_home_,
                            fb->getVelocity(), fb->getAcceleration(),
                            fb->getDeceleration(), fb->getJerk(),
                            fb->getBufferMode(), fb->getPlannerType());

      (*it_).setAdvancedParams(
          fb->getDuration(), fb->getStartPosition() + axis_pos_home_,
          fb->getStartVelocity(), fb->getStartAcceleration(),
          fb->getTargetPosition() + axis_pos_home_, fb->getTargetVelocity(),
          fb->getTargetAcceleration());
    }
    break;
    default:
      break;
  }
  (*it_).taken_ = mcTRUE;
  (*it_).setPosDoneFactor(config_->factor_.pos_);
  (*it_).setVelDoneFactor(config_->factor_.vel_);

  motion_kernel_.addFBToQueue(it_, getPosCmd(), toUserVelCmd(), toUserAccCmd(),
                              fb->getTargetAcceleration());
}

mcBOOL Axis::statusHealthy()
{
  // Check axis error and power status
  if (axis_error_ || power_status_ == mcFALSE)
  {
    motion_kernel_.setAllFBsAborted();
    DEBUG_PRINT("Axis::statusHealthy axis_error_: 0x%X\n", axis_error_);
    return mcFALSE;
  }

  return mcTRUE;
}

void Axis::powerProcess()
{
  if (axis_error_)  // If there is axis error
  {
    setAxisState(mcErrorStop);  // Set axis state to Error Stop
    if (reset_ == mcTRUE)
    {
      mcBOOL is_done = mcFALSE;
      servo_->resetError(is_done);
      if (is_done ==
          mcTRUE)  // If servo reset successfully, i.e. no servo error,
                   // reset error code, power state and axis state
      {
        axis_error_   = mcErrorCodeGood;
        power_status_ = mcFALSE;
        setAxisState(mcDisabled);
        reset_ = mcFALSE;
      }
    }
    return;
  }

  // If there is no axis error, process servo power status
  mcBOOL is_done = mcFALSE;
  MC_ERROR_CODE servo_res =
      servoErrorToAxisError(servo_->setPower(power_on_, is_done));

  // Power On
  if (power_on_ == mcTRUE && power_status_ == mcFALSE)
  {
    // Error happen when powering on
    if (servo_res != mcErrorCodeServoNoError)
    {
      power_status_ = mcFALSE;
      axis_error_   = servo_res;
      DEBUG_PRINT("axis_state_ 01: %d\n", axis_state_);
      setAxisState(mcErrorStop);
      DEBUG_PRINT("axis_state_ 02: %d\n", axis_state_);
      DEBUG_PRINT("Powering on error 0x%X\n", servo_res);
      return;
    }
    // Powered on successfully
    if (is_done == mcTRUE)
    {
      power_status_ = mcTRUE;
      axis_vel_cmd_ = axis_vel_ = 0.0;
      axis_tor_cmd_ = axis_acc_cmd_ = axis_acc_ = 0.0;
      axis_pos_cmd_ = axis_pos_        = toUserUnit(servo_->pos());
      axis_underlying_pos_cmd_         = axis_pos_cmd_;
      axis_sup_move_total_covered_pos_ = 0;
      if (axis_home_state_ == mcFALSE)
        axis_pos_home_ = axis_pos_;
      DEBUG_PRINT("Axis #%d powered on, axis_pos_ = %f\n, axis_pos_home_%f\n",
                  axis_id_, toUserUnit(servo_->pos()), axis_pos_home_);
      MC_ERROR_CODE res = setAxisState(mcStandstill);
      if (res != mcErrorCodeGood)
        axis_error_ = res;
      return;
    }
  }

  // When powered on
  if (power_on_ == mcTRUE && power_status_ == mcTRUE)
  {
    // Error happen when powered on
    if (servo_res != mcErrorCodeServoNoError)
    {
      power_status_ = mcFALSE;
      axis_error_   = servo_res;
      DEBUG_PRINT("axis_state_ 01: %d\n", axis_state_);
      setAxisState(mcErrorStop);
      DEBUG_PRINT("axis_state_ 02: %d\n", axis_state_);
      DEBUG_PRINT("Powered on error 0x%X\n", servo_res);
      return;
    }
  }

  // Power Off
  if (power_on_ == mcFALSE && power_status_ == mcTRUE)
  {
    // Error happen when powering off
    if (servo_res != mcErrorCodeServoNoError)
    {
      power_status_ = mcFALSE;
      axis_error_   = servo_res;
      DEBUG_PRINT("axis_state_ 01: %d\n", axis_state_);
      setAxisState(mcErrorStop);
      DEBUG_PRINT("axis_state_ 02: %d\n", axis_state_);
      DEBUG_PRINT("Powering off error 0x%X\n", servo_res);
      return;
    }

    // Powered off successfully
    if (is_done == mcTRUE)
    {
      MC_ERROR_CODE res = setAxisState(mcDisabled);
      if (res != mcErrorCodeGood)
      {
        axis_error_ = res;
        return;
      }
      power_status_ = mcFALSE;
      axis_vel_cmd_ = axis_vel_ = 0.0;
      axis_tor_cmd_ = axis_acc_cmd_ = axis_acc_ = 0.0;
      axis_pos_cmd_ = axis_pos_ = toUserUnit(servo_->pos());
      DEBUG_PRINT("Powered Off axis_pos_cmd_ = axis_pos_ = %f\n",
                  toUserUnit(servo_->pos()));
      return;
    }
  }
}

mcBOOL Axis::cmdsProcessing()
{
  // Check motion direction and limits
  mcLREAL vel_cmd = (axis_pos_cmd_ - axis_pos_) * config_->frequency_;
  mcLREAL acc_cmd = (axis_vel_cmd_ - axis_vel_) * config_->frequency_;
  DEBUG_PRINT("Axis::cmdsProcessing: axis_pos_ %f, axis_vel_ %f\n", axis_pos_,
              axis_vel_);
  DEBUG_PRINT("Axis::cmdsProcessing: axis_pos_cmd_ %f, axis_vel_cmd_ %f\n",
              axis_pos_cmd_, axis_vel_cmd_);
  DEBUG_PRINT("Axis::cmdsProcessing: vel_cmd %f, acc_cmd %f\n", vel_cmd,
              acc_cmd);

  if (vel_cmd > 0 && enable_positive_ == mcFALSE)
  {
    axis_error_ = mcErrorCodeInvalidDirectionPositive;
    return mcFALSE;
  }
  else if (vel_cmd < 0 && enable_negative_ == mcFALSE)
  {
    axis_error_ = mcErrorCodeInvalidDirectionNegative;
    return mcFALSE;
  }

  if (config_->sw_vel_limit_ == mcTRUE && fabs(vel_cmd) > config_->vel_limit_)
  {
    axis_error_ = mcErrorCodeVelocityOverLimit;
    return mcFALSE;
  }

  if (config_->sw_acc_limit_ == mcTRUE && fabs(acc_cmd) > config_->acc_limit_)
  {
    axis_error_ = mcErrorCodeAccelerationOverLimit;
    return mcFALSE;
  }

  if (config_->sw_range_limit_ == mcTRUE &&
      axis_pos_cmd_ > config_->pos_positive_limit_ && vel_cmd > 0)
  {
    axis_error_ = mcErrorCodePositionOverPositiveLimit;
    return mcFALSE;
  }

  if (config_->sw_range_limit_ == mcTRUE &&
      axis_pos_cmd_ < config_->pos_negative_limit_ && vel_cmd < 0)
  {
    axis_error_ = mcErrorCodePositionOverNegativeLimit;
    return mcFALSE;
  }

  // Process home position offset

  return mcTRUE;
}

void Axis::syncMotionKernelResultsToAxis()
{
  if ((axis_mode_ == mcServoControlModeTorque) ||
      (axis_mode_ == mcServoControlModeHomeServo))
  {
    axis_pos_cmd_ = axis_pos_;
    axis_vel_cmd_ = axis_vel_;
  }
  else
  {
    motion_kernel_.getCommands(&axis_underlying_pos_cmd_,
                               &axis_underlying_vel_cmd_,
                               &axis_underlying_acc_cmd_);
    if (axis_superimposed_enable_ == mcTRUE)
    {
      // calculate sup var
      motion_kernel_.getSupMoveCommands(&axis_sup_pos_cmd_, &axis_sup_vel_cmd_,
                                        &axis_sup_acc_cmd_);
      // update sup-move covered distance
      axis_sup_move_covered_pos_ = axis_sup_pos_cmd_ - axis_underlying_pos_cmd_;
      // update axis cmd
      axis_pos_cmd_ = axis_sup_pos_cmd_;
      axis_vel_cmd_ = axis_sup_vel_cmd_;
      axis_acc_cmd_ = axis_sup_acc_cmd_;
    }
    else
    {
      // update axis cmd
      axis_pos_cmd_ = axis_underlying_pos_cmd_;
      axis_vel_cmd_ = axis_underlying_vel_cmd_;
      axis_acc_cmd_ = axis_underlying_acc_cmd_;
      // clear sup cmd
      axis_sup_pos_cmd_ = 0;
      axis_sup_vel_cmd_ = 0;
      axis_sup_acc_cmd_ = 0;
    }
  }
  DEBUG_PRINT("Axis::syncMotionKernelResultsToAxis: axis_pos_cmd_: %f, "
              "axis_vel_cmd_: %f, axis_acc_cmd_: %f, axis_torque_cmd_: %f, "
              "axis_max_profile_vel_cmd_: %f \n",
              axis_pos_cmd_, axis_vel_cmd_, axis_acc_cmd_, axis_torque_cmd_,
              axis_max_profile_vel_cmd_);
}

void Axis::updateMotionCmdsToServo()
{
  switch (axis_mode_)
  {
    case mcServoControlModePosition:
      servo_->setPos(toEncoderUnit(axis_pos_cmd_));
      break;
    case mcServoControlModeVelocity:
      servo_->setVel(toEncoderUnit(axis_vel_cmd_));
      break;
    case mcServoControlModeTorque:
      servo_->setTorque(axis_torque_cmd_);
      servo_->setMaxProfileVel(toEncoderUnit(axis_max_profile_vel_cmd_));
      break;
    case mcServoControlModeHomeServo:
      servo_->setHomeEnable(axis_home_enable_cmd_);
      break;
    default:
      servo_->setPos(0);
      servo_->setVel(0);
      servo_->setTorque(0);
      axis_error_ = mcErrorCodeSetControllerModeInvalid;
      break;
  }
  if (add_fb_ == mcTRUE && add_count_ < 100)
    DEBUG_PRINT("T: %f, C: %u, Axis::updateMotionCmdsToServo: axis_pos_cmd_: "
                "%f, toEncoderUnit(axis_pos_cmd_): %d\n",
                stamp_, count_, axis_pos_cmd_, toEncoderUnit(axis_pos_cmd_));
}

void Axis::statusSync()
{
  // Update servo state to axis
  axis_pos_ = toUserUnit(servo_->pos() - overflow_count_ * __INT32_MAX__ * 2);
  axis_vel_ = toUserUnit(servo_->vel());
  axis_acc_ = toUserUnit(servo_->acc());
  axis_torque_ = servo_->torque();
  // Update axis current mode
  servo_mode_ = servo_->mode();
  switch (servo_mode_)
  {
    case mcServoDriveModePP:
    case mcServoDriveModeCSP:
      axis_mode_ = mcServoControlModePosition;
      break;
    case mcServoDriveModePV:
    case mcServoDriveModeCSV:
      axis_mode_ = mcServoControlModeVelocity;
      break;
    case mcServoDriveModePT:
    case mcServoDriveModeCST:
      axis_mode_ = mcServoControlModeTorque;
      break;
    case mcServoDriveModeHM:
      axis_mode_ = mcServoControlModeHomeServo;
      break;
    default:
      break;
  }
  axis_acc_ = toUserUnit(servo_->acc());
  // Update axis_home_state
  if (axis_mode_ == mcServoControlModeHomeServo)
    axis_home_state_ = servo_->getHomeState();
  if (add_fb_ == mcTRUE && add_count_ < 100)
    DEBUG_PRINT("T: %f, C: %u, Axis::statusSync: axis_pos_: %f, axis_vel_: %f, "
                "axis_acc_: %f \n",
                stamp_, count_, axis_pos_, axis_vel_, axis_acc_);
}

mcLREAL Axis::fixOverFlow(mcLREAL x)
{
  x += overflow_count_ * __INT32_MAX__ * 2;
  if (x >= __INT32_MAX__)
  {
    x -= (mcLREAL)__INT32_MAX__ * 2;
    overflow_count_--;
  }
  else if (x <= -__INT32_MAX__)
  {
    x += (mcLREAL)__INT32_MAX__ * 2;
    overflow_count_++;
  }

  return x;
}

MC_AXIS_STATES Axis::getAxisState()
{
  return axis_state_;
}

MC_ERROR_CODE Axis::setAxisState(MC_AXIS_STATES set_state)
{
  switch (axis_state_)
  {
    case mcStandstill:
    case mcDiscreteMotion:
    case mcContinuousMotion: {
      switch (set_state)
      {
        case mcDisabled:
        case mcErrorStop:
        case mcSynchronizedMotion: {
          axis_state_ = set_state;
          return mcErrorCodeGood;
        }
        break;
        default:
          break;
      }
    }
    break;
    case mcHoming: {
      switch (set_state)
      {
        case mcDisabled:
        case mcStandstill:
        case mcStopping:
        case mcErrorStop: {
          axis_state_ = set_state;
          return mcErrorCodeGood;
        }
        break;
        default:
          return mcErrorCodeInvalidStateFromHoming;
          break;
      }
    }
    case mcStopping: {
      switch (set_state)
      {
        case mcStopping:
        case mcDisabled:
        case mcErrorStop:
        case mcStandstill: {
          axis_state_ = set_state;
          return mcErrorCodeGood;
        }
        break;
        default:
          return mcErrorCodeInvalidStateFromStopping;
          break;
      }
    }
    break;
    case mcErrorStop: {
      switch (set_state)
      {
        case mcErrorStop:
        case mcDisabled:
        case mcStandstill: {
          axis_state_ = set_state;
          return mcErrorCodeGood;
        }
        break;
        default:
          return mcErrorCodeInvalidStateFromErrorStop;
          break;
      }
    }
    break;
    case mcDisabled: {
      switch (set_state)
      {
        case mcDisabled:
        case mcErrorStop:
        case mcStandstill: {
          axis_state_ = set_state;
          return mcErrorCodeGood;
        }
        break;
        default:
          return mcErrorCodeInvalidStateFromDisabled;
          break;
      }
    }
    break;
    case mcSynchronizedMotion: {
      switch (set_state)
      {
        case mcDisabled:
        case mcErrorStop:
        case mcDiscreteMotion:
        case mcContinuousMotion:
        case mcStopping: {
          axis_state_ = set_state;
          return mcErrorCodeGood;
        }
        break;
        default:
          break;
      }
    }
    default:
      break;
  }
  return mcErrorCodeGood;
}

void Axis::setPower(mcBOOL power_on, mcBOOL enable_positive,
                    mcBOOL enable_negative)
{
  power_on_        = power_on;
  enable_positive_ = enable_positive;
  enable_negative_ = enable_negative;
}

void Axis::resetError(mcBOOL reset)
{
  reset_ = reset;
}

mcBOOL Axis::powerOn()
{
  return power_status_;
}

mcBOOL Axis::powerTriggered()
{
  return power_on_;
}

mcBOOL Axis::setHomePositionOffset(mcLREAL offset)
{
  axis_pos_home_ = axis_pos_home_ + offset;

  switch (axis_state_)
  {
    case mcDisabled:
    case mcErrorStop:
      axis_error_ = mcErrorCodeSetPositionInvalidState;
      return mcFALSE;
      break;
    case mcHoming:
    case mcDiscreteMotion:
    case mcContinuousMotion:
    case mcSynchronizedMotion:
    case mcStopping:
    case mcStandstill:
      motion_kernel_.offsetAllFBs(axis_pos_home_);
      // Some FB call setHomePositionOffset() API to update axis_home_state
      // Such as MC_Homing / MC_SetPosition
      axis_home_state_ = mcTRUE;
      return mcTRUE;
    default:
      return mcTRUE;
      break;
  }
}

mcBOOL Axis::setHomePositionOffset()
{
  return this->setHomePositionOffset(axis_pos_ - axis_pos_home_);
}

void Axis::setAxisOverrideFactors(mcREAL vel_factor, mcREAL acc_factor,
                                  mcREAL jerk_factor, mcREAL threshold)
{
  // check if all factors are not updated
  if (abs(axis_override_factors_.vel - vel_factor) > threshold ||
      abs(axis_override_factors_.acc - acc_factor) > threshold ||
      abs(axis_override_factors_.jerk - jerk_factor) > threshold)
  {
    axis_override_factors_.vel           = vel_factor;
    axis_override_factors_.acc           = acc_factor;
    axis_override_factors_.jerk          = jerk_factor;
    axis_override_factors_.override_flag = mcTRUE;
  }
  return;
}

MC_ERROR_CODE Axis::setControllerMode(MC_SERVO_CONTROL_MODE mode)
{
  /* mcStopping/mcErrorStop/mcHoming can't set mode */
  if ((axis_state_ == mcStopping) || (axis_state_ == mcErrorStop) ||
      (axis_state_ == mcHoming))
    return mcErrorCodeSetControllerModeInvalidState;

  /* set mode to servo */
  switch (mode)
  {
    case mcServoControlModePosition: {
      axis_mode_cmd_ = mcServoDriveModeCSP;
      if (axis_mode_ == mcServoControlModeVelocity)
        mode_switch_ = mcVelToPos;
      else if (axis_mode_ == mcServoControlModeTorque)
        mode_switch_ = mcToqToPos;
      else if (axis_mode_ == mcServoControlModeHomeServo)
        mode_switch_ = mcHomeToPos;
    }
    break;
    case mcServoControlModeVelocity: {
      axis_mode_cmd_ = mcServoDriveModeCSV;
      if (axis_mode_ == mcServoControlModePosition)
        mode_switch_ = mcPosToVel;
      else if (axis_mode_ == mcServoControlModeTorque)
        mode_switch_ = mcToqToVel;
      else if (axis_mode_ == mcServoControlModeHomeServo)
        mode_switch_ = mcHomeToVel;
    }
    break;
    case mcServoControlModeTorque: {
      axis_mode_cmd_ = mcServoDriveModeCST;
      if (axis_mode_ == mcServoControlModePosition)
        mode_switch_ = mcPosToToq;
      else if (axis_mode_ == mcServoControlModeVelocity)
        mode_switch_ = mcVelToToq;
      else if (axis_mode_ == mcServoControlModeHomeServo)
        mode_switch_ = mcHomeToToq;
    }
    break;
    case mcServoControlModeHomeServo: {
      axis_mode_cmd_ = mcServoDriveModeHM;
      if (axis_mode_ == mcServoControlModePosition)
        mode_switch_ = mcPosToHome;
      else if (axis_mode_ == mcServoControlModeVelocity)
        mode_switch_ = mcVelToHome;
      else if (axis_mode_ == mcServoControlModeTorque)
        mode_switch_ = mcToqToHome;
    }
    break;
    default:
      axis_mode_cmd_ = mcServoDriveModeNULL;
      return mcErrorCodeSetControllerModeInvalid;
  }
  servo_->setMode(axis_mode_cmd_);

  /* set mode done */
  if (axis_mode_ == mode)
  {
    /* All Fbs should be aborted when the mode is changed from high level
    to the low level. (high level: position & velocity; low level: torque).
    Switch home to other mode also need to abort all FBs. */
    if ((mode_switch_ == mcPosToToq) || (mode_switch_ == mcVelToToq) ||
        (mode_switch_ == mcHomeToToq) || (mode_switch_ == mcHomeToVel) ||
        (mode_switch_ == mcHomeToPos) || (mode_switch_ == mcPosToHome) ||
        (mode_switch_ == mcVelToHome))
      motion_kernel_.setAllFBsAborted();
    return mcErrorCodeSetControllerModeSuccess;
  }
  else
    return mcErrorCodeGood;
}

void Axis::setMasterRefPos(mcLREAL master_ref_pos)
{
  master_ref_pos_ = master_ref_pos;
}

void Axis::setMasterRefVel(mcLREAL master_ref_vel)
{
  master_ref_vel_ = master_ref_vel;
}

MC_ERROR_CODE Axis::getAxisError()
{
  return axis_error_;
}

mcBOOL Axis::isAxisHomeAbsSwitchActive()
{
  return axis_home_abs_switch_active_;
}

void Axis::setAxisHomeAbsSwitch(mcBOOL signal)
{
  axis_home_abs_switch_active_ = signal;
}

mcBOOL Axis::isAxisLimitSwitchPosActive()
{
  return axis_limit_switch_pos_active_;
}

void Axis::setAxisLimitSwitchPos(mcBOOL signal)
{
  axis_limit_switch_pos_active_ = signal;
}

mcBOOL Axis::isAxisLimitSwitchNegActive()
{
  return axis_limit_switch_neg_active_;
}

void Axis::setAxisLimitSwitchNeg(mcBOOL signal)
{
  axis_limit_switch_neg_active_ = signal;
}

mcBOOL Axis::isAxisInSimulationMode()
{
  if (servo_ != nullptr)
    return servo_->isServoInSimulation();
  else
    return mcTRUE;
}

mcBOOL Axis::isAxisCommunicationReady()
{
  return servo_->getCommunicationReady();
}

mcBOOL Axis::isAxisReadyForPowerOn()
{
  return servo_->getReadyForPowerOn();
}

mcBOOL Axis::getAxisWarning()
{
  return axis_has_warning_;
}

MC_ERROR_CODE Axis::servoErrorToAxisError(MC_SERVO_ERROR_CODE error_id)
{
  return static_cast<MC_ERROR_CODE>(0x60 + error_id);
}

mcBOOL Axis::setAxisParamInit(mcUINT number, AxisParamInfo* table)
{
  if ((!config_) || (!table) || (!number))
    return mcFALSE;
  config_->param_table_num_ = number;
  config_->param_table_     = table;
  return mcTRUE;
}

mcBOOL Axis::writeAxisParam(mcUINT number, mcUDINT value)
{
  if ((!config_) || (!servo_))
    return mcFALSE;
  if ((number >= config_->param_table_num_))
    return mcFALSE;
  return servo_->writeVal(config_->param_table_[number].index_,
                          config_->param_table_[number].sub_index_,
                          config_->param_table_[number].data_length_, value);
}

mcBOOL Axis::readAxisParam(mcUINT number, mcUDINT& value)
{
  if ((!config_) || (!servo_))
    return mcFALSE;
  if ((number >= config_->param_table_num_) || (!value))
    return mcFALSE;
  return servo_->readVal(config_->param_table_[number].index_,
                         config_->param_table_[number].sub_index_,
                         config_->param_table_[number].data_length_, value);
}

void Axis::addMoveSupFB(FbAxisNode* fb, mcLREAL pos, mcLREAL vel)
{
  // new MC_MoveSuperimposed FB will abort the on-going one
  if (axis_superimposed_enable_ == mcTRUE)
  {
    motion_kernel_.abortCurSupMoveFB();
    replanUnderlyingMotion();
  }

  // reset sup move node
  superimposed_node_ptr_->reset();

  // init value
  superimposed_node_ptr_->setPosDoneFactor(config_->factor_.pos_);
  superimposed_node_ptr_->setVelDoneFactor(config_->factor_.vel_);

  // set basic params
  superimposed_node_ptr_->setBasicParams(
      fb, mcMoveSupMode, pos, vel, fb->getAcceleration(), fb->getDeceleration(),
      fb->getJerk(), fb->getBufferMode(), mcRuckig);

  // add to motion kernel
  motion_kernel_.addSupMoveFB(superimposed_node_ptr_, getPosCmd(),
                              toUserVelCmd(), toUserAccCmd(),
                              fb->getTargetAcceleration());
}

void Axis::setAxisSuperimposedState(mcBOOL value)
{
  axis_superimposed_enable_ = value;
}

mcBOOL Axis::getAxisSuperimposedState()
{
  return axis_superimposed_enable_;
}

mcLREAL Axis::getMoveSupCoveredDistance()
{
  return axis_sup_move_covered_pos_;
}

void Axis::replanUnderlyingMotion()
{
  // update total superimposed move pos after superimposed FB triggered
  axis_sup_move_total_covered_pos_ += axis_sup_move_covered_pos_;
  // update superimposed get_commands to underlying get_commands
  axis_underlying_pos_cmd_ = axis_sup_pos_cmd_;
  axis_underlying_vel_cmd_ = axis_sup_vel_cmd_;
  axis_underlying_acc_cmd_ = axis_sup_acc_cmd_;
  // replan underlying node
  motion_kernel_.replanUnderlyingNode(axis_sup_move_total_covered_pos_,
                                      getPosCmd(), toUserVelCmd(),
                                      toUserAccCmd());
}

mcLREAL Axis::getDeltaTime()
{
  return delta_time_;
}

}  // namespace RTmotion
