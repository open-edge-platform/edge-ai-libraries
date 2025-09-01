// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_io_operation.cpp
 *
 * Maintainer: Wu Xian <xian.wu@intel.com>
 *
 */

#include <fb/private/include/fb_io_operation.hpp>

namespace RTmotion
{
FbIoOperation::FbIoOperation()
  : io_(nullptr)
  , io_num_(0)
  , bit_num_(0)
  , io_data_(mcFALSE)
  , io_type_(typeInvalid)
  , is_write_(mcFALSE)
  , set_value_(mcFALSE)
{
}

void FbIoOperation::setIO(IO_REF mcIO)
{
  io_ = mcIO;
}

void FbIoOperation::setBitNumber(mcUSINT bitNum)
{
  bit_num_ = bitNum;
}

MC_ERROR_CODE FbIoOperation::onRisingEdgeExecution()
{
  // check IO object errorCode
  if (io_->getErrorCode() != mcIONoError)
  {
    busy_     = mcFALSE;
    valid_    = mcFALSE;
    done_     = mcFALSE;
    error_    = mcTRUE;
    error_id_ = io_->ioErrorToMcError(io_->getErrorCode());
  }

  return error_id_;
}

MC_ERROR_CODE FbIoOperation::onExecution()
{
  MC_ERROR_CODE op_error = mcErrorCodeGood;
  /* check IO object errorCode */
  if (io_->getErrorCode() != mcIONoError)
  {
    busy_     = mcFALSE;
    valid_    = mcFALSE;
    error_    = mcTRUE;
    error_id_ = io_->ioErrorToMcError(io_->getErrorCode());
    return error_id_;
  }

  /* read operation */
  op_error = io_->readInputOutputData(io_num_, bit_num_, io_data_, io_type_);
  /* write operation */
  if (is_write_ == mcTRUE)
  {
    op_error = io_->writeOutputData(io_num_, bit_num_, set_value_);
  }

  /* check operation return */
  if (op_error != mcErrorCodeGood)
  {
    busy_     = mcFALSE;
    valid_    = mcFALSE;
    error_    = mcTRUE;
    error_id_ = op_error;
    return error_id_;
  }

  /* check write results */
  if ((is_write_ == mcTRUE) && (io_data_ == set_value_))
  {
    done_ = mcTRUE;
  }
  valid_ = mcTRUE;

  return error_id_;
}

MC_ERROR_CODE FbIoOperation::onFallingEdgeExecution()
{
  io_data_ = mcFALSE;
  return io_->ioErrorToMcError(io_->getErrorCode());
}

mcBOOL FbIoOperation::isError()
{
  return error_;
}

MC_ERROR_CODE FbIoOperation::getErrorID()
{
  return error_id_;
}

}  // namespace RTmotion