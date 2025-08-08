// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_cam_table_select.cpp
 *
 * Maintainer: Yichong Tang <yichong.tang@intel.com>
 *
 */

#include <fb/private/include/fb_cam_table_select.hpp>

namespace RTmotion
{
void copyMcCamId(McCamId& des, McCamId src)
{
  des.slave_              = src.slave_;
  des.pointer_to_element_ = src.pointer_to_element_;
  des.periodic_           = src.periodic_;
  des.master_absolute_    = src.master_absolute_;
  des.slave_absolute_     = src.slave_absolute_;
  des.start_master_       = src.start_master_;
  des.start_master_       = src.start_master_;
  des.end_master_         = src.end_master_;
  des.start_slave_        = src.start_slave_;
  des.end_slave_          = src.end_slave_;
}

FbCamTableSelect::FbCamTableSelect()
  : master_(nullptr)
  , slave_(nullptr)
  , cam_table_(nullptr)
  , periodic_(mcFALSE)
  , master_absolute_(mcFALSE)
  , slave_absolute_(mcFALSE)
  , cam_table_id_()
  , cam_table_valid_(mcFALSE)
  , iterator_(nullptr)
{
  cam_table_id_.pointer_to_element_ = nullptr;
}

FbCamTableSelect::~FbCamTableSelect()
{
  master_    = nullptr;
  slave_     = nullptr;
  cam_table_ = nullptr;
  iterator_  = nullptr;

  if (cam_table_id_.pointer_to_element_ != nullptr)
    delete[] cam_table_id_.pointer_to_element_;
  cam_table_id_.pointer_to_element_ = nullptr;
}

FbCamTableSelect::FbCamTableSelect(const FbCamTableSelect& other)
  : cam_table_id_()
{
  copyMemberVar(other);
}

FbCamTableSelect& FbCamTableSelect::operator=(const FbCamTableSelect& other)
{
  if (this != &other)
  {
    copyMemberVar(other);
  }
  return *this;
}

void FbCamTableSelect::copyMemberVar(const FbCamTableSelect& other)
{
  master_          = other.master_;
  slave_           = other.slave_;
  cam_table_       = other.cam_table_;
  periodic_        = other.periodic_;
  master_absolute_ = other.master_absolute_;
  slave_absolute_  = other.slave_absolute_;
  cam_table_valid_ = other.cam_table_valid_;
  iterator_        = other.iterator_;
  copyMcCamId(cam_table_id_, other.cam_table_id_);
}

MC_ERROR_CODE FbCamTableSelect::onRisingEdgeExecution()
{
  iterator_ = (McCamXYVA*)cam_table_->getPointerToElements();

  // Check if element_num_ from CAM table id is valid
  mcDINT iterator_num = 0;
  mcDINT i            = 0;
  while (iterator_ + i != nullptr && i < MAX_CAM_TABLE_ELEMENT_NUM)
  {
    if (iterator_[i].type == noNextSegment)
    {
      iterator_num = i + 1;
      break;
    }
    else
    {
      i++;
    }
  }

  if (i == MAX_CAM_TABLE_ELEMENT_NUM)
  {
    return mcErrorCodeCamTableElementNumberOverLimit;
  }
  else if (iterator_num != i + 1)
  {
    return mcErrorCodeCamTableEndPointTypeError;
  }
  else if (iterator_num != cam_table_->getElementNum())
  {
    return mcErrorCodeCamTableWrongNumber;
  }

  cam_table_id_.element_num_     = iterator_num;
  cam_table_id_.slave_           = slave_;
  cam_table_id_.periodic_        = periodic_;
  cam_table_id_.master_absolute_ = master_absolute_;
  cam_table_id_.slave_absolute_  = slave_absolute_;

  cam_table_id_.start_master_ = iterator_[0].x;
  cam_table_id_.start_slave_  = iterator_[0].y;
  cam_table_id_.end_master_   = iterator_[cam_table_->getElementNum() - 1].x;
  cam_table_id_.end_slave_    = iterator_[cam_table_->getElementNum() - 1].y;

  iterator_ = new McCamXYVA[cam_table_id_.element_num_];
  for (i = 0; i < cam_table_id_.element_num_; i++)
  {
    iterator_[i] = ((McCamXYVA*)cam_table_->getPointerToElements())[i];
  }

  if (cam_table_id_.pointer_to_element_ != nullptr)
    delete[] cam_table_id_.pointer_to_element_;
  cam_table_id_.pointer_to_element_ = (mcBYTE*)iterator_;
  cam_table_valid_                  = mcTRUE;
  return mcErrorCodeGood;
}

MC_ERROR_CODE FbCamTableSelect::onFallingEdgeExecution()
{
  cam_table_valid_ = mcFALSE;
  return mcErrorCodeGood;
}

MC_ERROR_CODE FbCamTableSelect::onExecution()
{
  if (cam_table_valid_ == mcTRUE)
    done_ = mcTRUE;
  else
    done_ = mcFALSE;

  return mcErrorCodeGood;
}

void FbCamTableSelect::setMaster(AXIS_REF master)
{
  master_ = master;
}

void FbCamTableSelect::setSlave(AXIS_REF slave)
{
  slave_ = slave;
  axis_  = slave_;
}

void FbCamTableSelect::setCamTable(MC_CAM_REF cam_table)
{
  cam_table_ = cam_table;
}

void FbCamTableSelect::setPeriodic(mcBOOL periodic)
{
  periodic_ = periodic;
}

void FbCamTableSelect::setMasterAbsolute(mcBOOL masterAbsolute)
{
  master_absolute_ = masterAbsolute;
}

void FbCamTableSelect::setSlaveAbsolute(mcBOOL slaveAbsolute)
{
  slave_absolute_ = slaveAbsolute;
}

AXIS_REF FbCamTableSelect::getMaster()
{
  return master_;
}

AXIS_REF FbCamTableSelect::getSlave()
{
  return slave_;
}

MC_CAM_REF FbCamTableSelect::getCamTable()
{
  return cam_table_;
}

McCamId* FbCamTableSelect::getCamTableID()
{
  return &cam_table_id_;
}

}  // namespace RTmotion