// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file io.cpp
 *
 * Maintainer: Wu Xian <xian.wu@intel.com>
 *
 */

#include <fb/private/include/io.hpp>
#include <string.h>

namespace RTmotion
{
McIO::McIO()
  : error_code_(mcIONoError), input_info_(), output_info_(), device_addr_(0)
{
}

McIO::~McIO()
{
  freeInputOutputInfo(input_info_);
  freeInputOutputInfo(output_info_);
}

McIO::McIO(const McIO& other) : input_info_(), output_info_()
{
  error_code_  = other.error_code_;
  device_addr_ = other.device_addr_;
  cpyMcIOInfo(input_info_, other.input_info_);
  cpyMcIOInfo(output_info_, other.output_info_);
}

McIO& McIO::operator=(const McIO& other)
{
  if (this != &other)
  {
    error_code_  = other.error_code_;
    device_addr_ = other.device_addr_;
    cpyMcIOInfo(input_info_, other.input_info_);
    cpyMcIOInfo(output_info_, other.output_info_);
  }
  return *this;
}

void McIO::cpyMcIOInfo(MC_IO_INFO& des, const MC_IO_INFO& src)
{
  if (&des != &src)
  {
    if (src.pdo_info != nullptr)
    {
      des.n_pdo     = src.n_pdo;
      des.pdo_index = src.pdo_index;
      des.pdo_info =
          static_cast<PDO_INFO*>(malloc(sizeof(MC_IO_INFO) * src.n_pdo));
      if (des.pdo_info)
      {
        for (size_t i = 0; i < src.n_pdo; i++)
        {
          des.pdo_info[i].n_entries = src.pdo_info[i].n_entries;
          des.pdo_info[i].index     = src.pdo_info[i].index;
          if (src.pdo_info[i].pdo_entry_info != nullptr)
          {
            des.pdo_info[i].pdo_entry_info = static_cast<PDO_ENTRY_INFO*>(
                malloc(sizeof(PDO_ENTRY_INFO) * src.pdo_info[i].n_entries));
            if (des.pdo_info[i].pdo_entry_info)
            {
              for (size_t j = 0; j < src.pdo_info[i].n_entries; j++)
              {
                des.pdo_info[i].pdo_entry_info[j].bitlen =
                    src.pdo_info[i].pdo_entry_info[j].bitlen;
                des.pdo_info[i].pdo_entry_info[j].index =
                    src.pdo_info[i].pdo_entry_info[j].index;
                des.pdo_info[i].pdo_entry_info[j].subindex =
                    src.pdo_info[i].pdo_entry_info[j].subindex;
                des.pdo_info[i].pdo_entry_info[j].offset =
                    src.pdo_info[i].pdo_entry_info[j].offset;
                des.pdo_info[i].pdo_entry_info[j].value =
                    src.pdo_info[i].pdo_entry_info[j].value;
                size_t len = strlen(
                    (const char*)(src.pdo_info[i].pdo_entry_info[j].name));
                des.pdo_info[i].pdo_entry_info[j].name =
                    static_cast<mcUSINT*>(malloc(len + 1));
                if (des.pdo_info[i].pdo_entry_info[j].name)
                {
                  memcpy(des.pdo_info[i].pdo_entry_info[j].name,
                         src.pdo_info[i].pdo_entry_info[j].name, len);
                }
                else
                {
                  des.pdo_info[i].pdo_entry_info[j].name = nullptr;
                }
              }
            }
            else
            {
              des.pdo_info[i].pdo_entry_info = nullptr;
            }
          }
        }
      }
      else
      {
        des.pdo_info = nullptr;
      }
    }
  }
}

MC_IO_ERROR_CODE McIO::getErrorCode()
{
  return error_code_;
}

MC_ERROR_CODE McIO::readInputOutputData(mcUINT ioNum, mcUSINT bitNum,
                                        mcBOOL& io_data, IO_TYPE ioType)
{
  PDO_INFO pdo;
  PDO_ENTRY_INFO pdo_entry;
  mcUSINT bit_num_count = bitNum;
  /* check input/output type */
  if (ioType == typeInput)
  {
    pdo = input_info_.pdo_info[ioNum];
  }
  else if (ioType == typeOutput)
  {
    pdo = output_info_.pdo_info[ioNum];
  }
  else
  {
    return mcErrorCodeIOTypeError;
  }
  /* read operation */
  for (mcUINT i = 0; i < pdo.n_entries; i++)
  {
    if (bit_num_count < pdo.pdo_entry_info[i].bitlen)
    {
      pdo_entry = pdo.pdo_entry_info[i];
      MC_IO_ERROR_CODE op_error =
          getIOValueByEntry(pdo_entry, bit_num_count, io_data);
      return ioErrorToMcError(op_error);
    }
    else
    {
      if (i == pdo.n_entries - 1)
      {
        return mcErrorCodeIODataBitLengthError;
      }
      else
      {
        bit_num_count = bit_num_count - pdo.pdo_entry_info[i].bitlen;
      }
    }
  }
  return mcErrorCodeGood;
}

MC_IO_ERROR_CODE McIO::getIOValueByEntry(PDO_ENTRY_INFO pdo_entry,
                                         mcUSINT bitNum, mcBOOL& io_data)
{
  io_data = static_cast<mcBOOL>((pdo_entry.value >> bitNum) & 1);
  return mcIONoError;
}

MC_ERROR_CODE McIO::writeOutputData(mcUINT outputNum, mcUSINT bitNum,
                                    mcBOOL data)
{
  /* check IO object state */
  if (error_code_ != mcIONoError)
  {
    return ioErrorToMcError(error_code_);
  }
  /* validate pdoID */
  if (outputNum > output_info_.n_pdo - 1)
  {
    return mcErrorCodeIONumberError;
  }

  PDO_INFO pdo_info = output_info_.pdo_info[outputNum];
  PDO_ENTRY_INFO pdo_entry;
  mcUSINT bit_num_count = bitNum;

  for (mcUINT i = 0; i < pdo_info.n_entries; i++)
  {
    if (bit_num_count < pdo_info.pdo_entry_info[i].bitlen)
    {
      pdo_entry = pdo_info.pdo_entry_info[i];
      MC_IO_ERROR_CODE op_error =
          setIOValueByEntry(pdo_entry, bit_num_count, data);
      return ioErrorToMcError(op_error);
    }
    else
    {
      if (i == pdo_info.n_entries - 1)
      {
        return ioErrorToMcError(mcIODataBitLengthError);
      }
      else
      {
        bit_num_count = bit_num_count - pdo_info.pdo_entry_info[i].bitlen;
      }
    }
  }
  return mcErrorCodeGood;
}

MC_IO_ERROR_CODE McIO::setIOValueByEntry(PDO_ENTRY_INFO pdo_entry,
                                         mcUSINT bitNum, mcBOOL data)
{
  mcULINT value = pdo_entry.value;
  mcUDINT index = pdo_entry.index;
  if (data == mcTRUE)
  {
    output_info_.pdo_info[0].pdo_entry_info[index].value =
        (value | (1 << bitNum));
  }
  else
  {
    output_info_.pdo_info[0].pdo_entry_info[index].value =
        (value & (~(1 << bitNum)));
  }
  return mcIONoError;
}

mcBool McIO::initializeIO(mcUDINT slave_index)
{
  device_addr_ = slave_index;
  /* initialize input_info_ with one 8-bit input valued 0 */
  input_info_.n_pdo = 1;
  input_info_.pdo_info =
      static_cast<PDO_INFO*>(malloc(sizeof(PDO_INFO) * input_info_.n_pdo));
  if (input_info_.n_pdo)
  {
    memset(input_info_.pdo_info, 0, sizeof(PDO_INFO) * input_info_.n_pdo);
  }
  else
  {
    input_info_.pdo_info = nullptr;
  }
  // add input
  PDO_INFO input0;
  input0.index          = 0;
  input0.n_entries      = 1;
  input0.pdo_entry_info = static_cast<PDO_ENTRY_INFO*>(
      malloc(sizeof(PDO_ENTRY_INFO) * input0.n_entries));
  if (input0.pdo_entry_info)
  {
    memset(input0.pdo_entry_info, 0, sizeof(PDO_ENTRY_INFO) * input0.n_entries);
    input0.pdo_entry_info[0].bitlen   = 8;
    input0.pdo_entry_info[0].value    = 0;
    input0.pdo_entry_info[0].index    = 0;
    input0.pdo_entry_info[0].subindex = 0;
    input0.pdo_entry_info[0].offset   = 0;
    input0.pdo_entry_info[0].name =
        static_cast<mcUSINT*>(malloc(sizeof("input0")));
    if (input0.pdo_entry_info[0].name)
    {
      memcpy(input0.pdo_entry_info[0].name, "input0", sizeof("input0"));
    }
    else
    {
      input0.pdo_entry_info[0].name = nullptr;
    }
  }
  else
  {
    input0.pdo_entry_info = nullptr;
  }
  input_info_.pdo_info[0] = input0;

  /* initialize output_info_ with one 8-bit output valued 0 */
  output_info_.n_pdo = 1;
  output_info_.pdo_info =
      static_cast<PDO_INFO*>(malloc(sizeof(PDO_INFO) * output_info_.n_pdo));
  if (output_info_.n_pdo)
  {
    memset(output_info_.pdo_info, 0, sizeof(PDO_INFO) * output_info_.n_pdo);
  }
  else
  {
    output_info_.pdo_info = nullptr;
  }
  // add output
  PDO_INFO output0;
  output0.index          = 0;
  output0.n_entries      = 1;
  output0.pdo_entry_info = static_cast<PDO_ENTRY_INFO*>(
      malloc(sizeof(PDO_ENTRY_INFO) * output0.n_entries));
  if (output0.pdo_entry_info)
  {
    memset(output0.pdo_entry_info, 0,
           sizeof(PDO_ENTRY_INFO) * output0.n_entries);
    output0.pdo_entry_info[0].bitlen   = 8;
    output0.pdo_entry_info[0].value    = 0;
    output0.pdo_entry_info[0].index    = 0;
    output0.pdo_entry_info[0].subindex = 0;
    output0.pdo_entry_info[0].offset   = 0;
    output0.pdo_entry_info[0].name =
        static_cast<mcUSINT*>(malloc(sizeof("output0")));
    if (output0.pdo_entry_info[0].name)
    {
      memcpy(output0.pdo_entry_info[0].name, "output0", sizeof("output0"));
    }
    else
    {
      output0.pdo_entry_info[0].name = nullptr;
    }
  }
  else
  {
    output0.pdo_entry_info = nullptr;
  }
  output_info_.pdo_info[0] = output0;

  return mcTRUE;
}

MC_ERROR_CODE McIO::ioErrorToMcError(MC_IO_ERROR_CODE errorCode)
{
  if (errorCode == mcIONoError)
  {
    return mcErrorCodeGood;
  }
  return static_cast<MC_ERROR_CODE>(0xA0 + errorCode);
}

void McIO::runCycle()
{
  // update data
}

// Bubble Sort PDO Entry in an ascending order of subindex
void McIO::sortPDOEntry(PDO_INFO* pdo_info)
{
  for (mcUINT i = 0; i < pdo_info->n_entries - 1; i++)
  {
    for (mcUINT j = 0; j < pdo_info->n_entries - i - 1; j++)
    {
      if (pdo_info->pdo_entry_info[j].subindex >
          pdo_info->pdo_entry_info[j + 1].subindex)
      {
        PDO_ENTRY_INFO tmp              = pdo_info->pdo_entry_info[j];
        pdo_info->pdo_entry_info[j]     = pdo_info->pdo_entry_info[j + 1];
        pdo_info->pdo_entry_info[j + 1] = tmp;
      }
    }
  }
}

// Bubble Sort input/otuput PDO in an ascending order of index
void McIO::sortPDO()
{
  /* sort input */
  for (mcUINT i = 0; i < input_info_.n_pdo - 1; i++)
  {
    for (mcUINT j = 0; j < input_info_.n_pdo - i - 1; j++)
    {
      if (input_info_.pdo_info[j].index > input_info_.pdo_info[j + 1].index)
      {
        PDO_INFO tmp                = input_info_.pdo_info[j];
        input_info_.pdo_info[j]     = input_info_.pdo_info[j + 1];
        input_info_.pdo_info[j + 1] = tmp;
      }
    }
  }
  /* sort output */
  for (mcUINT i = 0; i < output_info_.n_pdo - 1; i++)
  {
    for (mcUINT j = 0; j < output_info_.n_pdo - i - 1; j++)
    {
      if (output_info_.pdo_info[j].index > output_info_.pdo_info[j + 1].index)
      {
        PDO_INFO tmp                 = output_info_.pdo_info[j];
        output_info_.pdo_info[j]     = output_info_.pdo_info[j + 1];
        output_info_.pdo_info[j + 1] = tmp;
      }
    }
  }
}

void McIO::freePdoEntry(PDO_ENTRY_INFO* pdo_entry)
{
  if (!pdo_entry)
  {
    return;
  }

  if (pdo_entry->name)
  {
    free(pdo_entry->name);
    pdo_entry->name = nullptr;
  }
  free(pdo_entry);
  pdo_entry = nullptr;
}

void McIO::freeInputOutputInfo(MC_IO_INFO& io_info)
{
  if (io_info.pdo_info)
  {
    for (size_t i = 0; i < io_info.n_pdo; i++)
    {
      if (!io_info.pdo_info[i].pdo_entry_info)
      {
        continue;
      }
      freePdoEntry(io_info.pdo_info[i].pdo_entry_info);
    }
    free(io_info.pdo_info);
    io_info.pdo_info = nullptr;
  }
}

}  // namespace RTmotion