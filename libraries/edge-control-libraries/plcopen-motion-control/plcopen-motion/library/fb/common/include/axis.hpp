// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file axis.hpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#pragma once

#include <fb/common/include/global.hpp>
#include <fb/common/include/servo.hpp>
#include <queue>
#include <fb/common/include/motion_kernel.hpp>

#define NODE_BUFFER_MAX_SIZE 10

namespace RTmotion
{
class FbAxisMotion;
class MotionKernel;

struct AxisCheckDoneFactor
{
  mcLREAL pos_ = 0.0001;
  mcLREAL vel_ = 0.0001;
};

struct AxisParamInfo
{
  mcUINT index_;         // The parameter object index, e.g. 0x6061
  mcUSINT sub_index_;    // The parameter object sub-index, e.g. 0x00
  mcUSINT data_length_;  // The data length in bytes (1, 2, or 4).
};

struct AxisConfig
{
  mcLWORD encoder_count_per_unit_ = 1000000;
  mcBOOL sw_vel_limit_            = mcFALSE;
  mcLREAL vel_limit_              = 5000.0;
  mcBOOL sw_acc_limit_            = mcFALSE;
  mcLREAL acc_limit_              = 5000.0;
  mcBOOL sw_range_limit_          = mcFALSE;
  mcLREAL pos_positive_limit_     = 5000.0;
  mcLREAL pos_negative_limit_     = 5000.0;
  mcLREAL frequency_              = 1000.0;
  AxisParamInfo* param_table_     = nullptr;
  mcUINT param_table_num_         = 0;
  AxisCheckDoneFactor factor_;
};

class Axis
{
public:
  Axis();

  Axis(const Axis& axis);

  virtual Axis& operator=(const Axis& other);

  virtual ~Axis();

  void deleteServo();
  void deleteConfig();

  mcSINT axisId();

  void setAxisId(mcUSINT id);

  Servo* getServo();

  virtual void setServo(Servo* servo);

  virtual void setAxisConfig(AxisConfig* config);

  virtual void setNodeQueueSize(mcUSINT size);

  virtual void runCycle();
  virtual void runCycle(double pos, double vel);

  virtual mcLREAL getHomePos();
  virtual mcLREAL getPos();
  virtual mcLREAL toUserPos();
  virtual mcLREAL toUserVel();
  virtual mcUSINT getControllerMode();
  virtual mcBOOL getHomeState();
  virtual mcLREAL toUserAcc();
  virtual mcLREAL toUserTorque();
  virtual void setTorqueCmd(mcLREAL torque);
  virtual void setMaxProfileVelCmd(mcLREAL vel);
  virtual void setHomeEnableCmd(mcBOOL enable);
  virtual mcLREAL getPosCmd();
  virtual mcLREAL toUserPosCmd();
  virtual mcLREAL toUserVelCmd();
  virtual mcLREAL toUserAccCmd();
  virtual mcLREAL getDeltaTime();

  virtual mcLREAL toUserUnit(mcLREAL x);
  virtual mcDINT toEncoderUnit(mcLREAL x);

  virtual void addFBToQueue(FbAxisNode* fb, MC_MOTION_MODE mode);

  virtual mcBOOL statusHealthy();

  virtual void powerProcess();

  virtual mcBOOL cmdsProcessing();

  virtual void syncMotionKernelResultsToAxis();

  virtual void updateMotionCmdsToServo();

  virtual void statusSync();

  mcLREAL fixOverFlow(mcLREAL x);

  MC_AXIS_STATES getAxisState();

  MC_ERROR_CODE setAxisState(MC_AXIS_STATES set_state);

  void setPower(mcBOOL power_on, mcBOOL enable_positive,
                mcBOOL enable_negative);

  void resetError(mcBOOL reset);

  mcBOOL powerOn();
  mcBOOL powerTriggered();

  mcBOOL setHomePositionOffset(mcLREAL offset);
  mcBOOL setHomePositionOffset();

  void setAxisOverrideFactors(mcREAL vel_factor, mcREAL acc_factor,
                              mcREAL jerk_factor, mcREAL threshold);

  MC_ERROR_CODE setControllerMode(MC_SERVO_CONTROL_MODE mode);

  void setMasterRefPos(mcLREAL master_ref_pos);
  void setMasterRefVel(mcLREAL master_ref_vel);

  MC_ERROR_CODE getAxisError();
  mcBOOL isAxisHomeAbsSwitchActive();
  void setAxisHomeAbsSwitch(mcBOOL signal);
  mcBOOL isAxisLimitSwitchPosActive();
  void setAxisLimitSwitchPos(mcBOOL signal);
  mcBOOL isAxisLimitSwitchNegActive();
  void setAxisLimitSwitchNeg(mcBOOL signal);
  mcBOOL isAxisInSimulationMode();
  mcBOOL isAxisCommunicationReady();
  mcBOOL isAxisReadyForPowerOn();
  mcBOOL getAxisWarning();

  virtual MC_ERROR_CODE servoErrorToAxisError(MC_SERVO_ERROR_CODE error_id);
  mcBOOL setAxisParamInit(mcUINT number, AxisParamInfo* table);
  mcBOOL writeAxisParam(mcUINT number, mcUDINT value);
  mcBOOL readAxisParam(mcUINT number, mcUDINT& value);

  void addMoveSupFB(FbAxisNode* fb, mcLREAL pos, mcLREAL vel);
  void setAxisSuperimposedState(mcBOOL value);
  mcBOOL getAxisSuperimposedState();
  mcLREAL getMoveSupCoveredDistance();
  void replanUnderlyingMotion();

private:
  mcUSINT axis_id_;
  mcLREAL axis_pos_;
  mcLREAL axis_vel_;
  mcLREAL axis_torque_;
  MC_SERVO_CONTROL_MODE axis_mode_;
  mcBOOL axis_home_state_;
  mcLREAL axis_acc_;
  mcLREAL axis_jerk_;
  mcLREAL axis_pos_home_;
  mcLREAL axis_pos_cmd_;
  mcLREAL axis_vel_cmd_;
  mcLREAL axis_torque_cmd_;
  mcLREAL axis_max_profile_vel_cmd_;
  mcBOOL axis_home_enable_cmd_;
  mcSINT axis_mode_cmd_;
  mcLREAL axis_acc_cmd_;
  mcLREAL axis_tor_cmd_;
  mcLREAL overflow_count_;
  mcLREAL master_ref_pos_;
  mcLREAL master_ref_vel_;
  MC_AXIS_STATES axis_state_;
  OverrideFactors axis_override_factors_;
  Servo* servo_;
  mcLREAL axis_underlying_pos_cmd_;
  mcLREAL axis_underlying_vel_cmd_;
  mcLREAL axis_underlying_acc_cmd_;
  mcBOOL axis_superimposed_enable_;
  mcLREAL axis_sup_pos_cmd_;
  mcLREAL axis_sup_vel_cmd_;
  mcLREAL axis_sup_acc_cmd_;
  mcLREAL axis_sup_move_covered_pos_;
  mcLREAL axis_sup_move_total_covered_pos_;

  MotionKernel motion_kernel_;

  AxisConfig* config_;

  mcLREAL stamp_;
  mcLREAL delta_time_;

  mcBOOL power_on_;
  mcBOOL power_status_;
  mcBOOL reset_;
  mcBOOL enable_positive_;
  mcBOOL enable_negative_;

  mcBOOL add_fb_              = mcFALSE;
  mcDWORD count_              = 0;
  mcDWORD add_count_          = 0;
  mcSINT servo_mode_          = mcServoDriveModeNULL;
  MC_MODE_SWITCH mode_switch_ = mcNoModeSwitch;

  MC_ERROR_CODE axis_error_;

  mcUSINT node_num_;  // size of execution node queue in motion kernel
  ExecutionNode node_buffer_[NODE_BUFFER_MAX_SIZE];  // execution node pool
  ExecutionNode* it_;

  mcBOOL axis_home_abs_switch_active_;
  mcBOOL axis_limit_switch_pos_active_;
  mcBOOL axis_limit_switch_neg_active_;
  mcBOOL axis_in_simulation_;
  mcBOOL axis_has_warning_;
  // ExecutionNode of move superimposed FB
  ExecutionNode* superimposed_node_ptr_ = nullptr;
};

typedef Axis* AXIS_REF;

}  // namespace RTmotion
