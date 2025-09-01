// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

#include <chrono>
#include <ecrt_io.hpp>
#include <iostream>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define DOMAIN_INVAILD_OFFSET (0xFFFFFFFF)

EcrtIO::EcrtIO()
  : position_(0)
  , alias_(0)
  , domain1_(nullptr)
  , master_(nullptr)
  , master_state_()
{
}

mcUINT EcrtIO::deviceAddr()
{
  return (alias_ + position_);
}

void EcrtIO::runCycle()
{
  /* check slave state */
  if (master_ && master_->master)
  {
    mcSINT ret = motion_servo_get_master_state(master_->master, &master_state_);
    if (ret == ECAT_FAIL || !master_state_.m_state.slaves_responding)
    {
      error_code_ = mcIOEtherCATConfigError;
#ifdef DEBUG_PRINT_ENABLE
      printf("Slave states error!\n");
#endif
    }
  }
}

void EcrtIO::printIOInfo()
{
  // check error code
  if (error_code_ != mcIONoError)
  {
    printf("IO initialization failed! ErrorCode:%d", error_code_);
    return;
  }
  printf("\nslave position:%d slave alias:%d\n", position_, alias_);
  /* print intput PDO info */
  printf("input  num:%d\n", input_info_.n_pdo);
  for (size_t i = 0; i < input_info_.n_pdo; i++)
  {
    for (size_t j = 0; j < input_info_.pdo_info[i].n_entries; j++)
    {
      PDO_ENTRY_INFO tmp = input_info_.pdo_info[i].pdo_entry_info[j];
      printf("%ld  index:#x%X  subindex:%d  name:%s  bitLen:%d\n", i, tmp.index,
             tmp.subindex, tmp.name, tmp.bitlen);
    }
  }
  /* print output PDO info  */
  printf("output num:%d\n", output_info_.n_pdo);
  for (size_t i = 0; i < output_info_.n_pdo; i++)
  {
    for (size_t j = 0; j < output_info_.pdo_info[i].n_entries; j++)
    {
      PDO_ENTRY_INFO tmp = output_info_.pdo_info[i].pdo_entry_info[j];
      printf("%ld  index:#x%X  subindex:%d  name:%s  bitLen:%d\n", i, tmp.index,
             tmp.subindex, tmp.name, tmp.bitlen);
    }
  }
  printf("\n");
}

mcBOOL EcrtIO::initializeIO(mcUDINT slave_index)
{
  servo_sm_info_t slave_sm_info;
  mcUINT input_num  = 0;
  mcUINT output_num = 0;

  /* call the enablekit function to get position and alias */
  servo_slave_info_t* slave_info;
  slave_info = motion_servo_get_slave_info(master_, slave_index);
  alias_     = slave_info->alias;
  position_  = slave_info->position;

  /* check sm_info */
  if (slave_info->sm_size == 0 || !slave_info->sm_info)
  {
    error_code_ = mcIOEtherCATConfigError;
    printf("Unable to get sm info!\n");
    return mcFALSE;
  }

  /* loop slave_info to get input and output number */
  for (size_t i = 0; i < slave_info->sm_size; i++)
  {
    if (slave_info->sm_info[i].sm_type == typeInput)
    {
      input_num += slave_info->sm_info[i].n_pdos;
    }
    else if (slave_info->sm_info[i].sm_type == typeOutput)
    {
      output_num += slave_info->sm_info[i].n_pdos;
    }
  }

  /* initialization input_info_ */
  input_info_.n_pdo     = input_num;
  input_info_.pdo_index = 0;
  input_info_.pdo_info  = (PDO_INFO*)malloc(sizeof(PDO_INFO) * input_num);
  if (!input_info_.pdo_info)
  {
    printf("input_info_ malloc failed\n");
    error_code_ = mcIOSegmentationError;
    return mcFALSE;
  }
  memset(input_info_.pdo_info, 0, sizeof(PDO_INFO) * input_num);

  /* initialization output_info_ */
  output_info_.n_pdo     = output_num;
  output_info_.pdo_index = 0;
  output_info_.pdo_info  = (PDO_INFO*)malloc(sizeof(PDO_INFO) * output_num);
  if (!output_info_.pdo_info)
  {
    printf("output_info_ malloc failed\n");
    error_code_ = mcIOSegmentationError;
    return mcFALSE;
  }
  memset(output_info_.pdo_info, 0, sizeof(PDO_INFO) * output_num);

  /* Dump enablekit sm_info into input_info_ and output_info_ */
  for (size_t loop_sm = 0; loop_sm < slave_info->sm_size; loop_sm++)
  {
    slave_sm_info = slave_info->sm_info[loop_sm];
    /* get PDO list and initialize IO table */
    if (slave_sm_info.pdo_info)
    {
      mcBOOL ret = getInputOutputInfo(slave_sm_info);
      if (ret == mcFALSE)
      {
        return mcFALSE;
      }
    }
  }

  motion_servo_free_slave_info(slave_info);

  if (error_code_ == mcIONoError)
  {
    sortPDO();
  }
  else
  {
    return mcFALSE;
  }

  return mcTRUE;
}

MC_IO_ERROR_CODE EcrtIO::getIOValueByEntry(PDO_ENTRY_INFO pdo_entry,
                                           mcUSINT bitNum, mcBOOL& io_data)
{
  switch (pdo_entry.bitlen)
  {
    case 8:
      io_data = static_cast<mcBOOL>(
          (MOTION_DOMAIN_READ_U8(domain1_ + pdo_entry.offset) >> bitNum) & 1);
      break;
    case 16:
      io_data = static_cast<mcBOOL>(
          (MOTION_DOMAIN_READ_U16(domain1_ + pdo_entry.offset) >> bitNum) & 1);
      break;
    case 32:
      io_data = static_cast<mcBOOL>(
          (MOTION_DOMAIN_READ_U32(domain1_ + pdo_entry.offset) >> bitNum) & 1);
      break;
    case 64:
      io_data = static_cast<mcBOOL>(
          (MOTION_DOMAIN_READ_U64(domain1_ + pdo_entry.offset) >> bitNum) & 1);
      break;
    default:
      printf("Invalid bitlength %d for EtherCAT IO\n", pdo_entry.bitlen);
      return mcIODataBitLengthError;
  }

  return mcIONoError;
}

MC_IO_ERROR_CODE EcrtIO::setIOValueByEntry(PDO_ENTRY_INFO pdo_entry,
                                           mcUSINT bitNum, mcBOOL data)
{
  switch (pdo_entry.bitlen)
  {
    case 8: {
      mcUSINT value_u8 = MOTION_DOMAIN_READ_U8(domain1_ + pdo_entry.offset);
      if (data == mcTRUE)
      {
        MOTION_DOMAIN_WRITE_U8(domain1_ + pdo_entry.offset,
                               value_u8 | (1 << bitNum));
      }
      else
      {
        MOTION_DOMAIN_WRITE_U8(domain1_ + pdo_entry.offset,
                               value_u8 & (~(1 << bitNum)));
      }
      break;
    }

    case 16: {
      mcUINT value_u16 = MOTION_DOMAIN_READ_U16(domain1_ + pdo_entry.offset);
      if (data == mcTRUE)
      {
        MOTION_DOMAIN_WRITE_U16(domain1_ + pdo_entry.offset,
                                value_u16 | (1 << bitNum));
      }
      else
      {
        MOTION_DOMAIN_WRITE_U16(domain1_ + pdo_entry.offset,
                                value_u16 & (~(1 << bitNum)));
      }
      break;
    }

    case 32: {
      mcUDINT value_u32 = MOTION_DOMAIN_READ_U32(domain1_ + pdo_entry.offset);
      if (data == mcTRUE)
      {
        MOTION_DOMAIN_WRITE_U32(domain1_ + pdo_entry.offset,
                                value_u32 | (1 << bitNum));
      }
      else
      {
        MOTION_DOMAIN_WRITE_U32(domain1_ + pdo_entry.offset,
                                value_u32 & (~(1 << bitNum)));
      }
      break;
    }

    case 64: {
      mcULINT value_u64 = MOTION_DOMAIN_READ_U64(domain1_ + pdo_entry.offset);
      if (data == mcTRUE)
      {
        MOTION_DOMAIN_WRITE_U64(domain1_ + pdo_entry.offset,
                                value_u64 | (1 << bitNum));
      }
      else
      {
        MOTION_DOMAIN_WRITE_U64(domain1_ + pdo_entry.offset,
                                value_u64 & (~(1 << bitNum)));
      }
      break;
    }

    default:
      printf("Invalid bitlength for EtherCAT IO\n");
      return mcIODataBitLengthError;
  }

  return mcIONoError;
}

PDO_ENTRY_INFO
EcrtIO::getPDOEntryInfo(servo_pdo_entry_info_t slave_pdo_entry_info)
{
  PDO_ENTRY_INFO results = { 0, 0, 0, 0, nullptr, 0 };

  results.index    = slave_pdo_entry_info.index;
  results.subindex = slave_pdo_entry_info.subindex;
  results.bitlen   = slave_pdo_entry_info.bit_length;

  // get pdo entry name
  if (slave_pdo_entry_info.name)
  {
    size_t len   = strlen((const char*)slave_pdo_entry_info.name);
    results.name = static_cast<mcUSINT*>(malloc(len + 1));
    memset(results.name, 0, len + 1);
    if (slave_pdo_entry_info.name)
    {
      memcpy(results.name, slave_pdo_entry_info.name, len);
    }
  }
  else
  {
    results.name = nullptr;
  }

  results.offset = motion_servo_get_domain_offset(
      master_->master, alias_, position_, results.index, results.subindex);
  if (results.offset == DOMAIN_INVAILD_OFFSET)
  {
    printf("Invalid offset for EtherCAT IO\n");
    error_code_ = mcIOInvalidOffsetError;
  }

  return results;
}

mcBOOL EcrtIO::getInputOutputInfo(servo_sm_info_t servo_sm_info)
{
  servo_pdo_info_t servo_pdo_info;

  for (size_t i = 0; i < servo_sm_info.n_pdos; i++)
  {
    // check whether data type is valid
    if (servo_sm_info.sm_type == typeInvalid)
    {
      return mcTRUE;
    }

    servo_pdo_info = servo_sm_info.pdo_info[i];
    PDO_INFO results;
    results.index     = servo_pdo_info.index;
    results.n_entries = servo_pdo_info.n_entries;
    // malloc pdo entries
    results.pdo_entry_info = (PDO_ENTRY_INFO*)malloc(sizeof(PDO_ENTRY_INFO) *
                                                     servo_pdo_info.n_entries);
    if (!results.pdo_entry_info)
    {
      printf("pdo entry info malloc failed\n");
      error_code_ = mcIOSegmentationError;
      return mcFALSE;
    }
    memset(results.pdo_entry_info, 0,
           sizeof(PDO_ENTRY_INFO) * servo_pdo_info.n_entries);
    for (size_t loop = 0; loop < servo_pdo_info.n_entries; loop++)
    {
      PDO_ENTRY_INFO pdo_entry_info;
      pdo_entry_info = getPDOEntryInfo(servo_pdo_info.pdo_entry_info[loop]);
      results.pdo_entry_info[loop] = pdo_entry_info;
    }
    sortPDOEntry(&results);
    // add results to input_info/output_info
    if (servo_sm_info.sm_type == typeOutput)
    {
      output_info_.pdo_info[output_info_.pdo_index] = results;
      output_info_.pdo_index++;
    }
    else if (servo_sm_info.sm_type == typeInput)
    {
      input_info_.pdo_info[input_info_.pdo_index] = results;
      input_info_.pdo_index++;
    }
  }
  return mcTRUE;
}