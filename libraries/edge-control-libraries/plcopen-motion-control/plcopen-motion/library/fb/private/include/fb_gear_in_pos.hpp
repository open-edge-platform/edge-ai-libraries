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
 * @brief Function block MC_MoveVelocity
 */
class FbGearInPos : public FbAxisMotion
{
public:
  FbGearInPos();
  ~FbGearInPos() override;
  FbGearInPos(const FbGearInPos& other);
  FbGearInPos& operator=(const FbGearInPos& other);

  MC_ERROR_CODE onRisingEdgeExecution() override;
  MC_ERROR_CODE onExecution() override;
  MC_ERROR_CODE afterFallingEdgeExecution() override;

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

  VAR_OUTPUT mcBOOL start_sync_;
  VAR_OUTPUT mcBOOL in_sync_;

private:
  MC_ERROR_CODE startGearProcess();
  mcLREAL master_pos_;
  mcLREAL last_master_pos_;
  mcLREAL master_vel_;
  mcLREAL master_start_position_;
  mcLREAL pos_sync_factor_;
  mcLREAL vel_sync_factor_;
  mcBOOL slave_standby_;
};
}  // namespace RTmotion