// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

#pragma once

#include <fb/common/include/global.hpp>
#include <fb/private/include/io.hpp>
#include <cstddef>
#include <cstdint>
#include <motionentry.h>

using namespace RTmotion;

class EcrtIO : public McIO
{
public:
  EcrtIO();
  ~EcrtIO() override = default;

  mcUINT deviceAddr();
  // cyclic update
  void runCycle() override;
  // print IO info
  void printIOInfo();
  mcBOOL initializeIO(
      mcUDINT slave_index) override;  // 1. get PDO list from enablekit 2.
                                      // initialize Input info and Output Info
  void setMaster(servo_master* master)
  {
    master_ = master;
  }
  void setDomain(mcUSINT* domain)
  {
    domain1_ = domain;
  }

private:
  // read operation
  MC_IO_ERROR_CODE getIOValueByEntry(PDO_ENTRY_INFO pdo_entry, mcUSINT bitNum,
                                     mcBOOL& io_data) override;
  // write operation
  MC_IO_ERROR_CODE setIOValueByEntry(PDO_ENTRY_INFO pdo_entry, mcUSINT bitNum,
                                     mcBOOL data) override;
  /* Dump enablekit object into plcopen object */
  PDO_ENTRY_INFO getPDOEntryInfo(servo_pdo_entry_info_t slave_pdo_entry_info);
  mcBOOL getInputOutputInfo(servo_sm_info_t servo_sm_info);

  mcUINT position_;
  mcUINT alias_;
  mcUSINT* domain1_;
  servo_master* master_;
  servo_master_state_t master_state_;
};