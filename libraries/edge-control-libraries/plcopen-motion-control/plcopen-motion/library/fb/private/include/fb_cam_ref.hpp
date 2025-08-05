// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_cam_ref.hpp
 *
 * Maintainer: Yichong Tang <yichong.tang@intel.com>
 *
 */

#pragma once

#include <fb/common/include/fb_base.hpp>

namespace RTmotion
{
/**
 * @brief MC_CamRef
 */

typedef enum
{
  xyva = 0,
} MC_CAM_TYPE;

typedef enum
{
  line          = 0,
  polyFive      = 1,
  noNextSegment = 2,  // Last point in cam table
} MC_SEGMENT_TYPE;

struct McCamXYVA
{
  mcLREAL x;             // Master position.
  mcLREAL y;             // Slave position.
  mcLREAL v = NAN;       // First derivative dy/dx. Default: NAN
  mcLREAL a = NAN;       // Second derivative d²Y/dX². Default: NAN
  MC_SEGMENT_TYPE type;  // Segment type.
};

class FbCamRef
{
public:
  FbCamRef();
  FbCamRef(mcDINT nElement, mcLREAL xStart, mcLREAL xEnd, McCamXYVA* pce);
  ~FbCamRef();
  FbCamRef(const FbCamRef& other);
  FbCamRef& operator=(const FbCamRef& other);

  void setType(MC_CAM_TYPE type);
  void setElementNum(mcDINT element_num);
  void setMasterRangeStart(mcLREAL range_start);
  void setMasterRangeEnd(mcLREAL range_end);
  void setElements(mcBYTE* pointer_to_elements);

  MC_CAM_TYPE getType();
  mcDINT getElementNum();
  mcBYTE* getPointerToElements();

protected:
  // Inputs
  VAR_IN_OUT MC_CAM_TYPE type_;
  VAR_IN_OUT mcDINT element_num_;
  VAR_IN_OUT mcLREAL x_start_;
  VAR_IN_OUT mcLREAL x_end_;
  VAR_IN_OUT mcBYTE* pointer_to_elements_;  // Pointer to cam table elements

private:
  void copyMemberVar(const FbCamRef& other);
};

typedef FbCamRef* MC_CAM_REF;

}  // namespace RTmotion