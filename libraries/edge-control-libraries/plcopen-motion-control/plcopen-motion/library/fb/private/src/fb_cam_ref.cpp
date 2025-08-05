// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_cam_ref.cpp
 *
 * Maintainer: Yichong Tang <yichong.tang@intel.com>
 *
 */

#include <fb/private/include/fb_cam_ref.hpp>

namespace RTmotion
{
FbCamRef::FbCamRef()
  : type_(xyva)
  , element_num_(0)
  , x_start_(0.0)
  , x_end_(0.0)
  , pointer_to_elements_(nullptr)
{
}

FbCamRef::FbCamRef(mcDINT nElement, mcLREAL xStart, mcLREAL xEnd,
                   McCamXYVA* pce)
{
  type_                = xyva;
  element_num_         = nElement;
  x_start_             = xStart;
  x_end_               = xEnd;
  pointer_to_elements_ = (mcBYTE*)pce;
}

FbCamRef::~FbCamRef()
{
  pointer_to_elements_ = nullptr;
}

FbCamRef::FbCamRef(const FbCamRef& other)
{
  copyMemberVar(other);
}

FbCamRef& FbCamRef::operator=(const FbCamRef& other)
{
  if (this != &other)
  {
    copyMemberVar(other);
  }
  return *this;
}

void FbCamRef::copyMemberVar(const FbCamRef& other)
{
  type_                = other.type_;
  element_num_         = other.element_num_;
  x_start_             = other.x_start_;
  x_end_               = other.x_end_;
  pointer_to_elements_ = other.pointer_to_elements_;
}

void FbCamRef::setType(MC_CAM_TYPE type)
{
  type_ = type;
}

void FbCamRef::setElementNum(mcDINT element_num)
{
  element_num_ = element_num;
}

void FbCamRef::setMasterRangeStart(mcLREAL range_start)
{
  x_start_ = range_start;
}

void FbCamRef::setMasterRangeEnd(mcLREAL range_end)
{
  x_end_ = range_end;
}

void FbCamRef::setElements(mcBYTE* pointer_to_elements)
{
  pointer_to_elements_ = pointer_to_elements;
}

MC_CAM_TYPE FbCamRef::getType()
{
  return type_;
}

mcDINT FbCamRef::getElementNum()
{
  return element_num_;
}

mcBYTE* FbCamRef::getPointerToElements()
{
  return pointer_to_elements_;
}

}  // namespace RTmotion