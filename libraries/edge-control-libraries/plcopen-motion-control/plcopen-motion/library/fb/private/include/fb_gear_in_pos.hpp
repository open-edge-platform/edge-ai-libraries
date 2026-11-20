// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_gear_in_pos.hpp
 *
 * Maintainer: Yichong Tang <yichong.tang@intel.com>
 *
 */

#pragma once

#include <fb/common/include/global.hpp>
#include <fb/common/include/fb_axis_motion.hpp>

#include <chrono>

namespace RTmotion
{
/**
 * @brief Position-synchronized electronic gearing
 *
 * Acquisition uses current master displacement; position following continues
 * in the same execution node without aborting the function block.
 * During acquisition, a waypoint exceeding the velocity, acceleration,
 * deceleration, or jerk limits is rejected. The FB reports Error while its
 * node stops the slave with bounded deceleration and jerk; queued successors
 * and existing superimposed motion are aborted. The stop starts from the
 * effective commanded state. The master and sync distance are not changed.
 * A busy retrigger retains the current relationship until the new start
 * boundary replaces it. Synchronization coordinates and ratio are latched;
 * changing inputs alone does not change the active relationship.
 */
class FbGearInPos : public FbAxisMotion
{
public:
  FbGearInPos();
  ~FbGearInPos() override;
  FbGearInPos(const FbGearInPos& other);
  FbGearInPos& operator=(const FbGearInPos& other);

  void runCycle() override;
  MC_ERROR_CODE onRisingEdgeExecution() override;
  MC_ERROR_CODE onExecution() override;
  MC_ERROR_CODE onFallingEdgeExecution() override;
  MC_ERROR_CODE afterFallingEdgeExecution() override;
  void onError(MC_ERROR_CODE error_code) override;
  mcBOOL isPositionCoupled() override;
  void getMasterReference(mcLREAL& position, mcLREAL& velocity,
                          mcLREAL& acceleration) override;
  mcBOOL isReadyForBufferedHandoff() override;
  mcLREAL getTargetPosition() override;
  mcLREAL getTargetVelocity() override;
  mcLREAL getTargetAcceleration() override;

  void setMaster(AXIS_REF master);
  void setSlave(AXIS_REF slave);
  void setRatioNumerator(mcINT ratio_numerator);
  void setRatioDenominator(mcUINT ratio_denominator);
  void setMasterSyncPosition(mcLREAL master_sync_position);
  void setSlaveSyncPosition(mcLREAL slave_sync_position);
  void setMasterStartDistance(mcLREAL master_start_distance);
  void setPosSyncFactor(mcLREAL pos_sync_factor);
  void setVelSyncFactor(mcLREAL vel_sync_factor);

  AXIS_REF getMaster();
  AXIS_REF getSlave();
  mcBOOL getStartSync();
  mcBOOL getInSync();

protected:
  VAR_IN_OUT AXIS_REF master_;
  VAR_IN_OUT AXIS_REF slave_;

  VAR_INPUT mcINT ratio_numerator_;
  VAR_INPUT mcUINT ratio_denominator_;
  VAR_INPUT mcLREAL master_sync_position_;
  VAR_INPUT mcLREAL slave_sync_position_;
  VAR_INPUT mcLREAL master_start_distance_;

  // Acquisition indicator; cleared on synchronization, abort, or error.
  VAR_OUTPUT mcBOOL start_sync_;
  VAR_OUTPUT mcBOOL in_sync_;

private:
  struct Synchronization
  {
    mcLREAL ratio                 = 0;
    mcLREAL master_sync_position  = 0;
    mcLREAL slave_sync_position   = 0;
    mcLREAL master_start_position = 0;
  };

  MC_ERROR_CODE startGearProcess();
  mcLREAL master_pos_;
  mcLREAL last_master_pos_;
  mcLREAL master_vel_;
  Synchronization synchronization_;
  Synchronization pending_synchronization_;
  mcLREAL pos_sync_factor_;
  mcLREAL vel_sync_factor_;
  mcBOOL slave_standby_;
  mcBOOL position_locked_ = mcFALSE;
};
}  // namespace RTmotion