// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_io_operation.hpp
 *
 * Maintainer: Wu Xian <xian.wu@intel.com>
 *
 */

#pragma once

#include <fb/common/include/fb_axis_admin.hpp>
#include <fb/private/include/io.hpp>

namespace RTmotion
{
/**
 * @brief Function block base for IO operation
 */
class FbIoOperation : public FbAxisAdmin
{
public:
  FbIoOperation();
  ~FbIoOperation() override = default;

  // Functions for addressing inputs
  void setIO(IO_REF mcIO);
  void setBitNumber(mcUSINT bitNum);

  // Functions for initialization
  MC_ERROR_CODE onRisingEdgeExecution() override;
  MC_ERROR_CODE onExecution() override;
  MC_ERROR_CODE onFallingEdgeExecution() override;

  // Functions for getting outputs
  mcBOOL isError() override;
  MC_ERROR_CODE getErrorID() override;

protected:
  // IO_REF
  VAR_IN_OUT IO_REF io_;

  VAR_INPUT mcUINT io_num_;
  VAR_INPUT mcUSINT bit_num_;

  mcBOOL io_data_;
  IO_TYPE io_type_;
  mcBOOL is_write_;
  mcBOOL set_value_;
};
}  // namespace RTmotion