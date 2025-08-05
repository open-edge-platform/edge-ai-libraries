// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file function_block_test.cpp
 *
 * Maintainer: Wu Xian <xian.wu@intel.com>
 *
 */

#include <thread>
#include "gtest/gtest.h"
#include <fb/common/include/global.hpp>
#include <fb/private/include/fb_read_digital_input.hpp>
#include <fb/private/include/fb_read_digital_output.hpp>
#include <fb/private/include/fb_write_digital_output.hpp>

#ifdef PLOT
#include <tool/fb_debug_tool.hpp>
#endif

using namespace RTmotion;

// IO set
mcBOOL flag;
mcUDINT input_id        = 0;
mcUDINT output_id       = 0;
mcUDINT input_bit_num   = 0;
mcUDINT output_bit_num  = 0;
mcBOOL write_output_val = mcTRUE;
mcBOOL result;

class FunctionBlockTest : public ::testing::Test
{
protected:
  // You can remove any or all of the following functions if their bodies would
  // be empty.

  FunctionBlockTest()
  {
    // You can do set-up work for each test here.
  }

  ~FunctionBlockTest() override
  {
    // You can do clean-up work that doesn't throw exceptions here.
  }

  // If the constructor and destructor are not enough for setting up
  // and cleaning up each test, you can define the following methods:

  void SetUp() override
  {
    // Code here will be called immediately after the constructor (right
    // before each test).
  }

  void TearDown() override
  {
    // Code here will be called immediately after each test (right
    // before the destructor).
  }
};

// Test MC_ReadDigitalInput
TEST_F(FunctionBlockTest, MC_ReadDigitalInput)
{
  McIO* my_io;
  my_io = new McIO();
  /* Initialize IO object */
  my_io->initializeIO(0);
  printf("IO object initialized.\n");

  /* Create motion function block */
  FbReadDigitalInput fb_read_digital_input;
  fb_read_digital_input.setIO(my_io);
  fb_read_digital_input.setInputNumber(input_id);
  fb_read_digital_input.setBitNumber(input_bit_num);
  printf("Function block MC_ReadDigitalInput initialized.\n");

  /* execute MC_ReadDigitalInput */
  fb_read_digital_input.setEnable(mcTRUE);

  double timeout = 0;
  while (timeout < 5)
  {
    my_io->runCycle();
    fb_read_digital_input.runCycle();
    timeout += 0.1;
  }
  /* Function Test */
  result = fb_read_digital_input.getValue();
  if (fb_read_digital_input.isValid() == mcTRUE)
  {
    printf("inputID:%d   bitNum:%d   value:%d\n", input_id, input_bit_num,
           static_cast<mcUSINT>(result));
  }
  else
  {
    printf("Read input error! ErrorID:%X\n",
           fb_read_digital_input.getErrorID());
  }

  /* Post processing */
  delete my_io;
  printf("FB test end. Delete io object.\n");
}

// Test MC_ReadDigitalOutput and MC_WriteDigitalOutput
TEST_F(FunctionBlockTest, DigitalOutputOperation)
{
  McIO* my_io;
  my_io = new McIO();
  /* Initialize IO object */
  my_io->initializeIO(0);
  printf("IO object initialized.\n");

  /* Create MC_ReadDigitalOutput function blocks */
  FbReadDigitalOutput fb_read_digital_output;
  fb_read_digital_output.setIO(my_io);
  fb_read_digital_output.setOutputNumber(output_id);
  fb_read_digital_output.setBitNumber(output_bit_num);
  printf("Function block MC_ReadDigitalOutput initialized.\n");

  /* Create MC_WriteDigitalOutput function blocks */
  FbWriteDigitalOutput fb_write_digital_output;
  fb_write_digital_output.setIO(my_io);
  fb_write_digital_output.setOutputNumber(output_id);
  fb_write_digital_output.setBitNumber(output_bit_num);
  fb_write_digital_output.setValue(
      write_output_val);  // need to set value before runCycle()
  printf("Function block MC_WriteDigitalOutput initialized.\n");

  /* execute MC_ReadDigitalOutput and MC_WriteDigitalOutput */
  fb_read_digital_output.setEnable(mcTRUE);
  fb_write_digital_output.setEnable(mcTRUE);

  double timeout = 0;
  while (timeout < 5)
  {
    my_io->runCycle();
    fb_read_digital_output.runCycle();
    fb_write_digital_output.runCycle();
    timeout += 0.1;
  }

  /* MC_WriteDigitalOutput Test */
  if (fb_write_digital_output.isDone() == mcFALSE)
  {
    printf("Write output error! ErrorID:%X\n",
           fb_write_digital_output.getErrorID());
  }
  else
  {
    printf("Write output(%d,%d) to %d.\n", output_id, output_bit_num,
           static_cast<mcUSINT>(write_output_val));
  }

  /* MC_ReadDigitalOutput Test */
  result = fb_read_digital_output.getValue();
  if (fb_read_digital_output.isValid() == mcFALSE)
  {
    printf("Read output error! ErrorID:%X\n",
           fb_read_digital_output.getErrorID());
  }
  else if (result != write_output_val)
  {
    printf("Read value is not equal to write value! ErrorID:%X\n",
           fb_write_digital_output.getErrorID());
  }
  else
  {
    printf("outputID:%d   bitNum:%d   value:%d\n", input_id, input_bit_num,
           static_cast<mcUSINT>(result));
  }

  /* Post processing */
  delete my_io;
  printf("FB test end. Delete io object.\n");
}