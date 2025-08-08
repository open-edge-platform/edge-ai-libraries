// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

#include "ecrt_io.hpp"
#include <fb/private/include/fb_read_digital_input.hpp>
#include <fb/private/include/fb_read_digital_output.hpp>
#include <fb/private/include/fb_write_digital_output.hpp>
#include <getopt.h>
#include <iostream>
#include <limits.h>
#include <motionentry.h>
#include <pthread.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

using namespace RTmotion;

#define CYCLE_US (1000)
#define PERIOD_NS (CYCLE_US * 1000)
#define NSEC_PER_SEC (1000000000L)
#define DIFF_NS(A, B)                                                          \
  (((B).tv_sec - (A).tv_sec) * NSEC_PER_SEC + ((B).tv_nsec) - (A).tv_nsec)
#define CYCLE_COUNTER_PERSEC (NSEC_PER_SEC / PERIOD_NS)

// Thread related
static pthread_t cyclic_thread;
static volatile int run = 1;
mcBOOL flag;
// Ethercat related
static servo_master* master = nullptr;
static mcUSINT* domain1;
void* domain;
// Command line arguments
static mcBOOL verbose_flag = mcFALSE;
static mcBOOL log_flag     = mcFALSE;
static char* tmp;
static char* res;
static char* eni_file;
static mcULINT light_tick;
static mcULINT repeat_times = 10;
// IO set
static EcrtIO* my_io;
mcBOOL input_data;
mcBOOL output_data;
mcUDINT slave_id        = 0;
mcUDINT input_id        = 0;
mcUDINT output_id       = 0;
mcUDINT input_bit_num   = 0;
mcUDINT output_bit_num  = 0;
mcBOOL write_output_val = mcFALSE;
mcUSINT result;
// RTmotion related
static FbReadDigitalInput fb_read_digital_input;
static FbReadDigitalOutput fb_read_digital_output;
static FbWriteDigitalOutput fb_write_digital_output;
// log data
static char column_string[] = "FbReadDigitalInput.Enable,\
              FbReadDigitalInput.Valid,\
              FbReadDigitalInput.Busy,\
              FbReadDigitalInput.Error,\
              FbReadDigitalInput.Value,\
              FbReadDigitalOutput.Enable,\
              FbReadDigitalOutput.Valid,\
              FbReadDigitalOutput.Busy,\
              FbReadDigitalOutput.Error,\
              FbReadDigitalOutput.Value,\
              FbWriteDigitalOutput.Enable,\
              FbWriteDigitalOutput.Done,\
              FbWriteDigitalOutput.Busy,\
              FbWriteDigitalOutput.Error,\
              FbWriteDigitalOutput.Value";
static char log_file_name[] = "ethercat_io_demo_test_results.csv";
static FILE* log_fptr       = nullptr;
typedef struct
{
  mcBOOL enable;
  mcBOOL valid;
  mcBOOL busy;
  mcBOOL error;
  mcBOOL value;
} fb_io_operation_signal;
static fb_io_operation_signal* fb_read_digital_input_signal   = nullptr;
static fb_io_operation_signal* fb_read_digital_output_signal  = nullptr;
static fb_io_operation_signal* fb_write_digital_output_signal = nullptr;
mcBOOL enable_flag                                            = mcFALSE;
mcULINT record_cycle                                          = 15000;
mcULINT record_cycle_count                                    = 0;

// RT thread function
void* my_thread(void* /*arg*/)
{
  struct timespec next_period;
  unsigned int cycle_count = 0;

  struct sched_param param = {};
  param.sched_priority     = 99;
  pthread_setschedparam(pthread_self(), SCHED_FIFO, &param);
  clock_gettime(CLOCK_MONOTONIC, &next_period);

  while (run != 0)
  {
    next_period.tv_nsec += CYCLE_US * 1000;
    while (next_period.tv_nsec >= NSEC_PER_SEC)
    {
      next_period.tv_nsec -= NSEC_PER_SEC;
      next_period.tv_sec++;
    }
    clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &next_period, nullptr);
    cycle_count++;

    /* enable fbs */
    if (cycle_count == 500)
    {
      enable_flag = mcTRUE;
      fb_read_digital_input.setEnable(mcTRUE);
      fb_read_digital_output.setEnable(mcTRUE);
      fb_write_digital_output.setEnable(mcTRUE);
    }
    /* check repeat times */
    if (cycle_count / light_tick > repeat_times && enable_flag == mcTRUE)
    {
      /* disable fbs */
      fb_read_digital_input.setEnable(mcFALSE);
      fb_read_digital_output.setEnable(mcFALSE);
      fb_write_digital_output.setEnable(mcFALSE);
      printf("Disable Fbs after repeating %ld times.\n", repeat_times);
      enable_flag = mcFALSE;
    }

    motion_servo_recv_process(master->master, domain);
    my_io->runCycle();
    fb_read_digital_input.runCycle();
    fb_read_digital_output.runCycle();
    fb_write_digital_output.runCycle();

    /* update and get IO value */
    if (cycle_count % light_tick == 0)
    {
      write_output_val = mcTRUE;

      /* fb_read_digital_input test */
      result = static_cast<mcUSINT>(fb_read_digital_input.getValue());
      if (verbose_flag == mcTRUE && fb_read_digital_input.isValid() == mcTRUE)
      {
        printf("slave:%d   inputID:%d   bitNum:%d   value:%d\n", slave_id,
               input_id, input_bit_num, result);
      }
      else if (fb_read_digital_input.isError() == mcTRUE)
      {
        printf("Read input error!ErrorID:%X\n",
               fb_read_digital_input.getErrorID());
        break;
      }

      /* fb_write_digital_output test */
      fb_write_digital_output.setValue(write_output_val);
      if (fb_write_digital_output.isError() == mcTRUE)
      {
        printf("Write output error!ErrorID:%X\n",
               fb_write_digital_output.getErrorID());
        break;
      }
      /* fb_read_digital_output test */
      result = static_cast<mcUSINT>(fb_read_digital_output.getValue());
      if (verbose_flag == mcTRUE && fb_read_digital_output.isValid() == mcTRUE)
      {
        printf("slave:%d  outputID:%d   bitNum:%d   value:%d\n\n", slave_id,
               output_id, output_bit_num, result);
      }
      else if (fb_read_digital_output.isError() == mcTRUE)
      {
        printf("Read output error!ErrorID:%X\n",
               fb_read_digital_output.getErrorID());
        break;
      }
    }
    else if (cycle_count % light_tick == light_tick / 2)
    {
      write_output_val = mcFALSE;

      /* fb_read_digital_input test */
      result = static_cast<mcUSINT>(fb_read_digital_input.getValue());
      if (verbose_flag == mcTRUE && fb_read_digital_input.isValid() == mcTRUE)
      {
        printf("slave:%d   inputID:%d   bitNum:%d   value:%d\n", slave_id,
               input_id, input_bit_num, result);
      }
      else if (fb_read_digital_input.isError() == mcTRUE)
      {
        printf("Read input error!ErrorID:%X\n",
               fb_read_digital_input.getErrorID());
        break;
      }

      /* fb_write_digital_output test */
      fb_write_digital_output.setValue(write_output_val);
      if (fb_write_digital_output.isError() == mcTRUE)
      {
        printf("Write output error!ErrorID:%X\n",
               fb_write_digital_output.getErrorID());
        break;
      }
      /* fb_read_digital_output test */
      result = static_cast<mcUSINT>(fb_read_digital_output.getValue());
      if (verbose_flag == mcTRUE && fb_read_digital_output.isValid() == mcTRUE)
      {
        printf("slave:%d  outputID:%d   bitNum:%d   value:%d\n\n", slave_id,
               output_id, output_bit_num, result);
      }
      else if (fb_read_digital_output.isError() == mcTRUE)
      {
        printf("Read output error!ErrorID:%X\n",
               fb_read_digital_output.getErrorID());
        break;
      }
    }

    motion_servo_send_process(master->master, domain);

    /* Write fb inputs and outputs to .cvs file*/
    if (log_flag == mcTRUE)
    {
      /* Save RT data to memory array */
      if (cycle_count < record_cycle)
      {
        /* IO signals of fb_read_digital_input */
        fb_read_digital_input_signal[record_cycle_count].enable =
            fb_read_digital_input.isEnabled();
        fb_read_digital_input_signal[record_cycle_count].valid =
            fb_read_digital_input.isValid();
        fb_read_digital_input_signal[record_cycle_count].busy =
            fb_read_digital_input.isBusy();
        fb_read_digital_input_signal[record_cycle_count].error =
            fb_read_digital_input.isError();
        fb_read_digital_input_signal[record_cycle_count].value =
            fb_read_digital_input.getValue();
        /* IO signals of fb_read_digital_output */
        fb_read_digital_output_signal[record_cycle_count].enable =
            fb_read_digital_output.isEnabled();
        fb_read_digital_output_signal[record_cycle_count].valid =
            fb_read_digital_output.isValid();
        fb_read_digital_output_signal[record_cycle_count].busy =
            fb_read_digital_output.isBusy();
        fb_read_digital_output_signal[record_cycle_count].error =
            fb_read_digital_output.isError();
        fb_read_digital_output_signal[record_cycle_count].value =
            fb_read_digital_output.getValue();
        /* IO signals of fb_write_digital_output */
        fb_write_digital_output_signal[record_cycle_count].enable =
            fb_write_digital_output.isEnabled();
        fb_write_digital_output_signal[record_cycle_count].valid =
            fb_write_digital_output.isDone();
        fb_write_digital_output_signal[record_cycle_count].busy =
            fb_write_digital_output.isBusy();
        fb_write_digital_output_signal[record_cycle_count].error =
            fb_write_digital_output.isError();
        fb_write_digital_output_signal[record_cycle_count].value =
            write_output_val;
        record_cycle_count++;
      }
    }
  }
  return nullptr;
}

static void getOptions(int argc, char** argv)
{
  int index;
  static struct option long_options[] = {
    // name		has_arg				flag	val
    { "tick", required_argument, nullptr, 't' },
    { "repeat", required_argument, nullptr, 'r' },
    { "slave", required_argument, nullptr, 's' },
    { "input", required_argument, nullptr, 'i' },
    { "output", required_argument, nullptr, 'o' },
    { "eni", required_argument, nullptr, 'n' },
    { "verbose", no_argument, nullptr, 'v' },
    { "log", no_argument, nullptr, 'l' },
    { "help", no_argument, nullptr, 'h' },
    {}
  };
  light_tick = 1000;
  do
  {
    index = getopt_long(argc, argv, "t:r:s:i:o:n:vlh", long_options, nullptr);
    switch (index)
    {
      case 't':
        light_tick = atoi(optarg);
        printf("Set tick:%ld ms \n", light_tick);
        break;
      case 'r':
        repeat_times = atoi(optarg);
        printf("Set repeat:%ld times \n", repeat_times);
        break;
      case 's':
        slave_id = atoi(optarg);
        printf("Set slave:%d \n", slave_id);
        break;
      case 'i':
        tmp           = strtok_r(optarg, ",", &res);
        input_id      = atoi(tmp);
        input_bit_num = atoi(res);
        printf("Set input:(%d,%d) \n", input_id, input_bit_num);
        break;
      case 'o':
        tmp            = strtok_r(optarg, ",", &res);
        output_id      = atoi(tmp);
        output_bit_num = atoi(res);
        printf("Set output:(%d,%d) \n", output_id, output_bit_num);
        break;
      case 'n':
        if (eni_file)
        {
          free(eni_file);
          eni_file = nullptr;
        }
        eni_file = static_cast<char*>(malloc(strlen(optarg) + 1));
        if (eni_file != nullptr)
        {
          memset(eni_file, 0, strlen(optarg) + 1);
          memmove(eni_file, optarg, strlen(optarg) + 1);
          printf("Using %s\n", eni_file);
        }
        break;
      case 'v':
        verbose_flag = mcTRUE;
        printf("verbose: print pos and vel values.\n");
        break;
      case 'l':
        log_flag = mcTRUE;
        printf("Log FB IO signals in a csv file.\n");
        break;
      case 'h':
        printf("Global options:\n");
        printf("    --tick      -t  Set cycle tick, default: %ld ms\n",
               light_tick);
        printf("    --repeat    -r  Set repeat times, default: %ld times\n",
               repeat_times);
        printf("    --slave     -s  Set slave number, default: %d \n",
               slave_id);
        printf("    --input     -i  Set input number and its bit number (start "
               "from 0), default:%d,%d \n",
               input_id, input_bit_num);
        printf(
            "    --output    -o  Set output number and its bit number (start "
            "from 0), default:%d,%d \n",
            output_id, output_bit_num);
        printf("    --eni       -n  Specify ENI/XML file\n");
        printf("    --ver       -v  Specify verbose print\n");
        printf("    --log       -l  Enable data log.\n");
        printf("    --help      -h  Show this help.\n");
        if (eni_file)
        {
          free(eni_file);
          eni_file = nullptr;
        }
        exit(0);
        break;
    }
  } while (index != -1);
}

int main(int argc, char* argv[])
{
  auto signal_handler = [](int /*unused*/) { run = 0; };
  getOptions(argc, argv);
  signal(SIGTERM, signal_handler);
  signal(SIGINT, signal_handler);

  mlockall(MCL_CURRENT | MCL_FUTURE);

  /* Create master by ENI*/
  if (!eni_file)
  {
    printf("Error: Unspecify ENI/XML file\n");
    exit(0);
  }
  master = motion_servo_master_create(eni_file);
  free(eni_file);
  eni_file = nullptr;
  if (master == nullptr)
  {
    return -1;
  }
  /* Motion domain create */
  if (motion_servo_domain_entry_register(master, &domain))
  {
    delete my_io;
    motion_servo_master_release(master);
    return -1;
  }
  if (!motion_servo_driver_register(master, domain))
  {
    delete my_io;
    motion_servo_master_release(master);
    return -1;
  }

  motion_servo_set_send_interval(master);

  if (motion_servo_master_activate(master->master))
  {
    printf("fail to activate master\n");
    delete my_io;
    motion_servo_master_release(master);
    return -1;
  }
  domain1 = motion_servo_domain_data(domain);
  if (!domain1)
  {
    printf("fail to get domain data\n");
    delete my_io;
    motion_servo_master_release(master);
    return -1;
  }

  /* Create Ecrt IO object */
  my_io = new EcrtIO();
  if (my_io == nullptr)
  {
    printf("fail to create IO class\n");
    return -1;
  }
  my_io->setMaster(master);
  my_io->setDomain(domain1);

  // specify the slave
  flag = my_io->initializeIO(slave_id);
  // check initialization results
  if (flag == mcFALSE)
  {
    printf("IO class initialization failed\n");
    printf("%d\n", my_io->getErrorCode());
    delete my_io;
    motion_servo_master_release(master);
    return -1;
  }
  // check initialization results and print IO info
  my_io->printIOInfo();

  /* Create motion function blocks */
  fb_read_digital_input.setIO(my_io);
  fb_read_digital_input.setInputNumber(input_id);
  fb_read_digital_input.setBitNumber(input_bit_num);

  fb_read_digital_output.setIO(my_io);
  fb_read_digital_output.setOutputNumber(output_id);
  fb_read_digital_output.setBitNumber(output_bit_num);

  fb_write_digital_output.setIO(my_io);
  fb_write_digital_output.setOutputNumber(output_id);
  fb_write_digital_output.setBitNumber(output_bit_num);
  fb_write_digital_output.setValue(
      write_output_val);  // need to set value before runCycle()

  /* Initialize csv output */
  if (log_flag == mcTRUE)
  {
    record_cycle                 = light_tick * (repeat_times + 5);
    fb_read_digital_input_signal = (fb_io_operation_signal*)malloc(
        sizeof(fb_io_operation_signal) * record_cycle);
    memset(fb_read_digital_input_signal, 0,
           sizeof(fb_io_operation_signal) * record_cycle);
    fb_read_digital_output_signal = (fb_io_operation_signal*)malloc(
        sizeof(fb_io_operation_signal) * record_cycle);
    memset(fb_read_digital_output_signal, 0,
           sizeof(fb_io_operation_signal) * record_cycle);
    fb_write_digital_output_signal = (fb_io_operation_signal*)malloc(
        sizeof(fb_io_operation_signal) * record_cycle);
    memset(fb_write_digital_output_signal, 0,
           sizeof(fb_io_operation_signal) * record_cycle);
    /* create new csv file */
    if ((log_fptr = fopen(log_file_name, "w+")) == nullptr)
    {
      printf("Error when open file \"%s\".\n", log_file_name);
      return 1;
    }
  }

  /* Create cyclic RT-thread */
  pthread_attr_t thattr;
  pthread_attr_init(&thattr);
  pthread_attr_setdetachstate(&thattr, PTHREAD_CREATE_JOINABLE);

  if (pthread_create(&cyclic_thread, &thattr, &my_thread, nullptr))
  {
    printf("pthread_create cyclic task failed\n");
    pthread_attr_destroy(&thattr);
    delete my_io;
    motion_servo_master_release(master);
    return -1;
  }

  while (run)
  {
    sched_yield();
    // sleep(0.01);
  }

  if (log_flag == mcTRUE && record_cycle_count > 0)
  {
    /* write columns at first line */
    fprintf(log_fptr, "%s\n", column_string);
    fclose(log_fptr);

    FILE* fptr;
    /* Open file */
    if ((fptr = fopen(log_file_name, "a")) == nullptr)
    {
      printf("Error when open file \"%s\".\n", log_file_name);
      return -1;
    }
    /* write Fb signals */
    for (size_t i = 0; i < record_cycle_count; i++)
    {
      fprintf(fptr, "%d,%d,%d,%d,%d,",
              static_cast<bool>(fb_read_digital_input_signal[i].enable),
              static_cast<bool>(fb_read_digital_input_signal[i].valid),
              static_cast<bool>(fb_read_digital_input_signal[i].busy),
              static_cast<bool>(fb_read_digital_input_signal[i].error),
              static_cast<bool>(fb_read_digital_input_signal[i].value));
      fprintf(fptr, "%d,%d,%d,%d,%d,",
              static_cast<bool>(fb_read_digital_output_signal[i].enable),
              static_cast<bool>(fb_read_digital_output_signal[i].valid),
              static_cast<bool>(fb_read_digital_output_signal[i].busy),
              static_cast<bool>(fb_read_digital_output_signal[i].error),
              static_cast<bool>(fb_read_digital_output_signal[i].value));
      fprintf(fptr, "%d,%d,%d,%d,%d\n",
              static_cast<bool>(fb_write_digital_output_signal[i].enable),
              static_cast<bool>(fb_write_digital_output_signal[i].valid),
              static_cast<bool>(fb_write_digital_output_signal[i].busy),
              static_cast<bool>(fb_write_digital_output_signal[i].error),
              static_cast<bool>(fb_write_digital_output_signal[i].value));
    }
    fclose(fptr);
  }

  /* Post processing */
  pthread_join(cyclic_thread, nullptr);
  pthread_attr_destroy(&thattr);
  delete my_io;
  motion_servo_master_release(master);
  free(fb_read_digital_input_signal);
  free(fb_read_digital_output_signal);
  free(fb_write_digital_output_signal);
  return 0;
}