// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file io.hpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#pragma once

#include <fb/common/include/global.hpp>
#include <vector>

typedef enum
{
  typeInvalid     = 0,
  typeOutput      = 1,
  typeInput       = 2,
  typeInputOutput = 3
} IO_TYPE;

namespace RTmotion
{
// PDO entry
typedef struct
{
  mcUDINT index;
  mcUDINT subindex;
  mcUDINT bitlen;
  mcULINT value;
  mcUSINT* name;
  mcUDINT offset;
} PDO_ENTRY_INFO;

// PDO
typedef struct
{
  PDO_ENTRY_INFO* pdo_entry_info;
  mcUINT n_entries;
  mcUSINT index;
} PDO_INFO;

// IO object
typedef struct
{
  PDO_INFO* pdo_info;
  mcUINT pdo_index;  // record how many pdos have been dumped
  mcUINT n_pdo;
} MC_IO_INFO;

class McIO
{
public:
  McIO();
  virtual ~McIO();
  McIO(const McIO& other);
  virtual McIO& operator=(const McIO& other);
  virtual void cpyMcIOInfo(MC_IO_INFO& des, const MC_IO_INFO& src);

  // get parameters
  virtual MC_IO_ERROR_CODE getErrorCode();

  /* read IO value */
  virtual MC_ERROR_CODE readInputOutputData(
      mcUINT ioNum, mcUSINT bitNum, mcBOOL& io_data,
      IO_TYPE ioType);  // bitNum starts from 0, write input data in io_data
  virtual MC_IO_ERROR_CODE getIOValueByEntry(PDO_ENTRY_INFO pdo_entry,
                                             mcUSINT bitNum, mcBOOL& io_data);

  /* write IO value */
  virtual MC_ERROR_CODE writeOutputData(mcUINT pdoID, mcUSINT bitNum,
                                        mcBOOL data);  // bitNum starts from 0
  virtual MC_IO_ERROR_CODE setIOValueByEntry(PDO_ENTRY_INFO pdo_entry,
                                             mcUSINT bitNum, mcBOOL data);

  virtual mcBOOL initializeIO(mcUDINT slave_index);  // initialize IO class as
                                                     // one 8-bit input with a
                                                     // value of 0 and one 8-bit
                                                     // output with a value of 0
  MC_ERROR_CODE
  ioErrorToMcError(MC_IO_ERROR_CODE errorCode);  // transfer MC_IO_ERROR_CODE to
                                                 // MC_ERROR_CODE

  /* IO sorting */
  void sortPDOEntry(PDO_INFO* pdo_info);  // sort entries of each PDO in an
                                          // ascending order of subindex
  void sortPDO();  // sort input/output PDOs in an ascending order of index

  void freePdoEntry(PDO_ENTRY_INFO* pdo_entry);
  void freeInputOutputInfo(MC_IO_INFO& io_info);
  virtual void runCycle();

protected:
  MC_IO_ERROR_CODE error_code_;
  MC_IO_INFO input_info_;   // store all input PDOs of this slave
  MC_IO_INFO output_info_;  // store all output PDOs of this slave

private:
  mcUINT device_addr_;
};

typedef McIO* IO_REF;

}  // namespace RTmotion
