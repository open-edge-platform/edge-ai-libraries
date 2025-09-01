// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_cam_table_select.hpp
 *
 * Maintainer: Yichong Tang <yichong.tang@intel.com>
 *
 */

#pragma once

#include <fb/common/include/global.hpp>
#include <fb/common/include/fb_axis_admin.hpp>
#include <fb/private/include/fb_cam_ref.hpp>

#define MAX_CAM_TABLE_ELEMENT_NUM 10000

namespace RTmotion
{
/**
 * @brief MC_CamTableSelect
 */

struct McCamId
{
  AXIS_REF slave_;
  mcBYTE* pointer_to_element_;  // Pointer to Cam Table elements
  mcDINT element_num_;
  mcBOOL periodic_;
  mcBOOL master_absolute_;
  mcBOOL slave_absolute_;
  mcLREAL start_master_;
  mcLREAL end_master_;
  mcLREAL start_slave_;
  mcLREAL end_slave_;
};

void copyMcCamId(McCamId& des, McCamId src);

class FbCamTableSelect : public FbAxisAdmin
{
public:
  FbCamTableSelect();
  ~FbCamTableSelect() override;
  FbCamTableSelect(const FbCamTableSelect& other);
  FbCamTableSelect& operator=(const FbCamTableSelect& other);

  MC_ERROR_CODE onExecution() override;
  MC_ERROR_CODE onRisingEdgeExecution() override;
  MC_ERROR_CODE onFallingEdgeExecution() override;

  void setMaster(AXIS_REF master);
  void setSlave(AXIS_REF slave);
  void setCamTable(MC_CAM_REF cam_table);
  void setPeriodic(mcBOOL periodic);
  void setMasterAbsolute(mcBOOL masterAbsolute);
  void setSlaveAbsolute(mcBOOL slaveAbsolute);

  AXIS_REF getMaster();
  AXIS_REF getSlave();
  MC_CAM_REF getCamTable();
  McCamId* getCamTableID();

protected:
  // In_Out
  VAR_IN_OUT AXIS_REF master_;
  VAR_IN_OUT AXIS_REF slave_;
  VAR_IN_OUT MC_CAM_REF cam_table_;
  // Inputs
  VAR_INPUT mcBOOL periodic_;
  VAR_INPUT mcBOOL master_absolute_;
  VAR_INPUT mcBOOL slave_absolute_;
  // Outputs
  VAR_OUTPUT McCamId cam_table_id_;

  mcBOOL cam_table_valid_;

private:
  void copyMemberVar(const FbCamTableSelect& other);
  McCamXYVA* iterator_;
};
}  // namespace RTmotion