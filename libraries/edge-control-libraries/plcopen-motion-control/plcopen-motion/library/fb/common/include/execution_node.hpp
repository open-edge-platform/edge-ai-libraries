// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file execution_node.hpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#pragma once

#include <fb/common/include/planner.hpp>
#include <fb/common/include/fb_axis_node.hpp>

namespace RTmotion
{
struct OverrideFactors
{
  mcREAL vel;
  mcREAL acc;
  mcREAL jerk;
  mcBOOL override_flag;
};

class ExecutionNode
{
public:
  ExecutionNode();

  ExecutionNode(const ExecutionNode& node);

  virtual ExecutionNode& operator=(const ExecutionNode& node);

  virtual ~ExecutionNode();

  void setBasicParams(FbAxisNode* fb, MC_MOTION_MODE mode, mcLREAL position,
                      mcLREAL velocity, mcLREAL acceleration,
                      mcLREAL deceleration, mcLREAL jerk,
                      MC_BUFFER_MODE buffer_mode, PLANNER_TYPE planner_type);
  void setAdvancedParams(mcLREAL duration, mcLREAL start_pos, mcLREAL start_vel,
                         mcLREAL start_acc, mcLREAL end_pos, mcLREAL end_vel,
                         mcLREAL end_acc);

  void setFrequency(mcLREAL f);

  void reset();
  void restart();

  // Functions to address inputs
  void setStartPos(mcLREAL pos);
  void setStartVel(mcLREAL vel);
  void setStartAcc(mcLREAL acc);
  void setEndAcc(mcLREAL acc);
  void setTerminateCondition(mcLREAL ref_pos);
  void setEndVel(mcLREAL vel);
  void setEndPos(mcLREAL pos);
  void setReplan();
  void setVelocity(mcLREAL velocity);
  void offsetFB(mcLREAL home_pos);
  void setPosDoneFactor(mcLREAL factor);
  void setVelDoneFactor(mcLREAL factor);

  // Functions to address outputs
  MC_BUFFER_MODE getBufferMode();
  MC_MOTION_MODE getMotionMode();
  mcLREAL getEndPos();
  mcLREAL getEndVel();
  mcLREAL getEndAcc();
  mcLREAL getVelocity();

  void getCommands(mcLREAL* pos_cmd, mcLREAL* vel_cmd, mcLREAL* acc_cmd);

  mcBOOL isActive();
  mcBOOL isDone();
  mcBOOL isAborted();
  mcBOOL isError();

  // Functions for working on different status
  virtual void onActive(MC_AXIS_STATES* current_state);
  virtual void onExecution(mcLREAL master_ref_pos, mcLREAL master_ref_vel);
  virtual void onDone(MC_AXIS_STATES* current_state);
  virtual void onCommandAborted();
  virtual void onError(MC_ERROR_CODE error_code);

  // Function for checking mission done
  virtual mcBOOL checkMissionDone(const mcLREAL axis_pos,
                                  const mcLREAL axis_vel);

  virtual void updateOverrideFactors(OverrideFactors& override_factors);

  void setPlannerStartTime(mcLREAL t);

  MC_ERROR_CODE changeAxisStates(MC_AXIS_STATES* current_state,
                                 MC_AXIS_STATES set_state);

  FbAxisNode* getAxisNodeInstance();
  PLANNER_TYPE getPlannerType();

  mcBOOL taken_ = mcFALSE;

protected:
  VAR_INPUT mcLREAL position_;
  VAR_INPUT mcLREAL velocity_;
  VAR_INPUT mcLREAL acceleration_;
  VAR_INPUT mcLREAL deceleration_;
  VAR_INPUT mcLREAL jerk_;
  VAR_INPUT MC_BUFFER_MODE buffer_mode_;

  VAR_OUTPUT mcBOOL done_;
  VAR_OUTPUT mcBOOL busy_;
  VAR_OUTPUT mcBOOL active_;
  VAR_OUTPUT mcBOOL command_aborted_;
  VAR_OUTPUT mcBOOL error_;
  VAR_OUTPUT MC_ERROR_CODE error_id_;

  FbAxisNode* fb_;

  // Variables for trajectory planning
  mcLREAL start_pos_;
  mcLREAL end_pos_;
  mcLREAL start_vel_;
  mcLREAL end_vel_;
  mcLREAL start_acc_;
  mcLREAL end_acc_;
  mcLREAL duration_;
  mcLREAL pos_cmd_;
  mcLREAL vel_cmd_;
  mcLREAL acc_cmd_;
  mcLREAL pos_tmp_;
  mcLREAL vel_tmp_;
  mcLREAL acc_tmp_;
  mcBOOL need_plan_;
  mcLREAL pos_done_factor_;
  mcLREAL vel_done_factor_;
  MC_MOTION_MODE motion_mode_;
  OverrideFactors override_factors_ = {};

  mcLREAL node_freq_;
  mcLREAL node_delta_time_;
  mcLREAL node_active_time_;

  // Trajectory generator variables
  trajectory_processing::AxisPlanner planner_;
  PLANNER_TYPE planner_type_;

private:
  void copyMemberVar(const ExecutionNode& node);
};

}  // namespace RTmotion
