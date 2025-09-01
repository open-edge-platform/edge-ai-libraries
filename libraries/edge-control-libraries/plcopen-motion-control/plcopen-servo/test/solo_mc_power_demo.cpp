// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

#include <fb/common/include/axis.hpp>
#include <fb/public/include/fb_power.hpp>
#include <fb/public/include/fb_reset.hpp>
#include <fb/public/include/fb_read_actual_position.hpp>
#include <fb/public/include/fb_read_actual_velocity.hpp>
#include <fb/private/include/fb_read_actual_torque.hpp>
#include <fb/public/include/fb_read_status.hpp>
#include <fb/public/include/fb_read_axis_error.hpp>
#include <fb/common/include/global.hpp>
#include <ecrt_config.hpp>
#include <ecrt_servo.hpp>
#include <errno.h>
#include <error.h>
#include <getopt.h>
#include <limits.h>
#include <motionentry.h>
#include <mqueue.h>
#include <pthread.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/ipc.h>
#include <sys/mman.h>
#include <sys/shm.h>
#include <sys/time.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

#define CYCLE_COUNTER_PERSEC(X) (NSEC_PER_SEC / 1000 / X)
static EcrtServo* my_servo;

// Thread related
static pthread_t cyclic_thread;
static volatile int run      = 1;
static unsigned int cycle_us = 1000;

// Ethercat related
static servo_master* master = nullptr;
static uint8_t* domain1;
void* domain;

// Command line arguments
static bool log_flag             = false;
static char* eni_file            = nullptr;
static bool verbose              = false;
static uint64_t ratio            = PER_CIRCLE_ENCODER;
static MC_ERROR_CODE fb_error_id = mcErrorCodeGood;

// RTmotion related
using namespace RTmotion;
static AXIS_REF axis;
static FbPower fb_power;
static FbReset fb_reset;
static FbReadActualPosition fb_read_pos;
static FbReadActualVelocity fb_read_vel;
static FbReadActualTorque fb_read_toq;
static FbReadStatus fb_read_status;
static FbReadAxisError fb_read_axis_err;

// log data
static char column_string[]      = "cycle_count, act_pos, act_vel, act_toq, \
                               FbPower.Enable, \
                               FbPower.EnablePositive, \
                               FbPower.EnableNegative, \
                               FbPower.status, \
                               FbPower.Valid, \
                               FbPower.Error, \
                               FbPower.ErrorID, \
                               FbReset.Execute, \
                               FbReset.Done, \
                               FbReset.Busy, \
                               FbReset.Error, \
                               FbReset.ErrorID, \
                               FbReadStatus.Enable, \
                               FbReadStatus.Valid, \
                               FbReadStatus.Busy, \
                               FbReadStatus.Error, \
                               FbReadStatus.ErrorID, \
                               FbReadStatus.ErrorStop, \
                               FbReadStatus.Disabled, \
                               FbReadStatus.Stopping, \
                               FbReadStatus.Homing, \
                               FbReadStatus.Standstill, \
                               FbReadStatus.DiscreteMotion, \
                               FbReadStatus.ContinuousMotion, \
                               FbReadStatus.SynchronizedMotion, \
                               FbReadAxisError.Enable, \
                               FbReadAxisError.Valid, \
                               FbReadAxisError.Busy, \
                               FbReadAxisError.Error, \
                               FbReadAxisError.ErrorID, \
                               FbReadAxisError.AxisErrorID";
static char log_file_name[20]    = "data.csv";
static FILE* log_fptr            = nullptr;
static uint64_t* cycle_count_ptr = nullptr;
static float* act_pos_ptr        = nullptr;
static float* act_vel_ptr        = nullptr;
static float* act_toq_ptr        = nullptr;
/* FbPower */
static bool* power_fb_enable_ptr       = nullptr;
static bool* power_fb_enb_positive_ptr = nullptr;
static bool* power_fb_enb_negative_ptr = nullptr;
static bool* power_fb_status_ptr       = nullptr;
static bool* power_fb_valid_ptr        = nullptr;
static bool* power_fb_error_ptr        = nullptr;
static uint16_t* power_fb_error_id_ptr = nullptr;
/* FbReset */
static bool* reset_fb_exec_ptr         = nullptr;
static bool* reset_fb_done_ptr         = nullptr;
static bool* reset_fb_busy_ptr         = nullptr;
static bool* reset_fb_error_ptr        = nullptr;
static uint16_t* reset_fb_error_id_ptr = nullptr;
/* FbReadStatus */
static bool* rd_sta_fb_enable_ptr       = nullptr;
static bool* rd_sta_fb_valid_ptr        = nullptr;
static bool* rd_sta_fb_busy_ptr         = nullptr;
static bool* rd_sta_fb_error_ptr        = nullptr;
static uint16_t* rd_sta_fb_error_id_ptr = nullptr;
static bool* rd_sta_fb_error_stop_ptr   = nullptr;
static bool* rd_sta_fb_disabled_ptr     = nullptr;
static bool* rd_sta_fb_stopping_ptr     = nullptr;
static bool* rd_sta_fb_homing_ptr       = nullptr;
static bool* rd_sta_fb_standstill_ptr   = nullptr;
static bool* rd_sta_fb_dis_motion_ptr   = nullptr;
static bool* rd_sta_fb_con_motion_ptr   = nullptr;
static bool* rd_sta_fb_syn_motion_ptr   = nullptr;
/* FbReadAxisError */
static bool* rd_err_fb_enable_ptr         = nullptr;
static bool* rd_err_fb_valid_ptr          = nullptr;
static bool* rd_err_fb_busy_ptr           = nullptr;
static bool* rd_err_fb_error_ptr          = nullptr;
static uint16_t* rd_err_fb_error_id_ptr   = nullptr;
static uint16_t* rd_err_axis_error_id_ptr = nullptr;
static unsigned int running_cycle_10min =
    (unsigned int)(CYCLE_COUNTER_PERSEC(cycle_us) * 600);
static unsigned int recorded_cycle = 0;

typedef enum
{
  MC_DEMO_POWER_ON = 0,
  MC_DEMO_POWER_OFF,
  MC_DEMO_IDLE,
  MC_DEMO_ERROR,
  MC_DEMO_RESET
} MC_DEMO_TEST;
static MC_DEMO_TEST s_demo_test_func = MC_DEMO_POWER_ON;

// RT thread function
void* my_thread(void* /*arg*/)
{
  struct timespec next_period, dc_period;
  uint64_t cycle_count      = 0;
  uint64_t idle_cycle_count = 0;
  mcBOOL powered_on         = mcFALSE;

  struct sched_param param = {};
  param.sched_priority     = 99;
  pthread_setschedparam(pthread_self(), SCHED_FIFO, &param);
  clock_gettime(CLOCK_MONOTONIC, &next_period);

  while (run)
  {
    next_period.tv_nsec += cycle_us * 1000;
    while (next_period.tv_nsec >= NSEC_PER_SEC)
    {
      next_period.tv_nsec -= NSEC_PER_SEC;
      next_period.tv_sec++;
    }
    clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &next_period, nullptr);
    motion_servo_recv_process(master->master, static_cast<uint8_t*>(domain));

    axis->runCycle();
    fb_power.runCycle();
    fb_reset.runCycle();
    fb_read_pos.runCycle();
    fb_read_vel.runCycle();
    fb_read_toq.runCycle();
    fb_read_status.runCycle();
    fb_read_axis_err.runCycle();
    powered_on  = fb_power.getPowerStatus();
    fb_error_id = fb_read_axis_err.getAxisErrorId();

    switch (s_demo_test_func)
    {
      case MC_DEMO_POWER_ON: {
        fb_power.setEnable(mcTRUE);
        if (powered_on == mcTRUE)
        {
          s_demo_test_func = MC_DEMO_IDLE;
          idle_cycle_count = 0;
          printf("Axis is powered on. \n");
        }
      }
      break;
      case MC_DEMO_POWER_OFF: {
        fb_power.setEnable(mcFALSE);
        if (powered_on == mcFALSE)
        {
          s_demo_test_func = MC_DEMO_IDLE;
          idle_cycle_count = 0;
          printf("Axis is powered off. \n");
        }
      }
      break;
      case MC_DEMO_IDLE: {
        // monitor error
        if (fb_error_id)
        {
          fb_power.setEnable(mcFALSE);
          s_demo_test_func = MC_DEMO_ERROR;
          printf("Axis enter error status, error_id:%d, cycle:%ld. \n",
                 fb_error_id, cycle_count);
        }
        // timeout
        if (idle_cycle_count++ > (10 * CYCLE_COUNTER_PERSEC(cycle_us)))
        {
          if (powered_on == mcTRUE)
          {
            printf("Axis idle timeout, enter to power off. \n");
            s_demo_test_func = MC_DEMO_POWER_OFF;
          }
          else
          {
            printf("Axis idle timeout, enter to power on. \n");
            s_demo_test_func = MC_DEMO_POWER_ON;
          }
        }
      }
      break;
      case MC_DEMO_ERROR: {
        /* servo error code */
        if (fb_error_id & 0x60)
        {
          s_demo_test_func = MC_DEMO_RESET;
          printf("Axis has a servo error, request mc_reset to clear it. \n");
        }
      }
      break;
      case MC_DEMO_RESET: {
        if (fb_reset.isDone() == mcTRUE)
        {
          fb_reset.setEnable(mcFALSE);
          s_demo_test_func = MC_DEMO_IDLE;
          idle_cycle_count = 0;
          printf("Axis is reset done. \n");
        }
        else
          fb_reset.setEnable(mcTRUE);
      }
      break;
      default:
        break;
    }

    clock_gettime(CLOCK_MONOTONIC, &dc_period);
    motion_servo_sync_dc(master->master, TIMESPEC2NS(dc_period));
    motion_servo_send_process(master->master, static_cast<uint8_t*>(domain));

    if (log_flag)
    {
      /* Save RT data to memory array */
      if (recorded_cycle < running_cycle_10min)
      {
        cycle_count_ptr[recorded_cycle] = cycle_count;
        act_pos_ptr[recorded_cycle]     = fb_read_pos.getFloatValue();
        act_vel_ptr[recorded_cycle]     = fb_read_vel.getFloatValue();
        act_toq_ptr[recorded_cycle]     = fb_read_toq.getFloatValue();
        /* FbPower */
        power_fb_enable_ptr[recorded_cycle]       = (bool)fb_power.isEnabled();
        power_fb_enb_positive_ptr[recorded_cycle] = (bool)mcTRUE;
        power_fb_enb_negative_ptr[recorded_cycle] = (bool)mcTRUE;
        power_fb_status_ptr[recorded_cycle]   = (bool)fb_power.getPowerStatus();
        power_fb_valid_ptr[recorded_cycle]    = (bool)fb_power.isValid();
        power_fb_error_ptr[recorded_cycle]    = (bool)fb_power.isError();
        power_fb_error_id_ptr[recorded_cycle] = fb_power.getErrorID();
        /* FbReset */
        reset_fb_exec_ptr[recorded_cycle]     = (bool)fb_reset.isEnabled();
        reset_fb_done_ptr[recorded_cycle]     = (bool)fb_reset.isDone();
        reset_fb_busy_ptr[recorded_cycle]     = (bool)fb_reset.isBusy();
        reset_fb_error_ptr[recorded_cycle]    = (bool)fb_reset.isError();
        reset_fb_error_id_ptr[recorded_cycle] = fb_reset.getErrorID();
        /* FbReadStatus */
        rd_sta_fb_enable_ptr[recorded_cycle] = (bool)fb_read_status.isEnabled();
        rd_sta_fb_valid_ptr[recorded_cycle]  = (bool)fb_read_status.isValid();
        rd_sta_fb_busy_ptr[recorded_cycle]   = (bool)fb_read_status.isBusy();
        rd_sta_fb_error_ptr[recorded_cycle]  = (bool)fb_read_status.isError();
        rd_sta_fb_error_id_ptr[recorded_cycle] = fb_read_status.getErrorID();
        rd_sta_fb_error_stop_ptr[recorded_cycle] =
            (bool)fb_read_status.isErrorStop();
        rd_sta_fb_disabled_ptr[recorded_cycle] =
            (bool)fb_read_status.isDisabled();
        rd_sta_fb_stopping_ptr[recorded_cycle] =
            (bool)fb_read_status.isStopping();
        rd_sta_fb_homing_ptr[recorded_cycle] = (bool)fb_read_status.isHoming();
        rd_sta_fb_standstill_ptr[recorded_cycle] =
            (bool)fb_read_status.isStandStill();
        rd_sta_fb_dis_motion_ptr[recorded_cycle] =
            (bool)fb_read_status.isDiscretMotion();
        rd_sta_fb_con_motion_ptr[recorded_cycle] =
            (bool)fb_read_status.isContinuousMotion();
        rd_sta_fb_syn_motion_ptr[recorded_cycle] =
            (bool)fb_read_status.isSynchronizedMotion();
        /* FbReadAxisError */
        rd_err_fb_enable_ptr[recorded_cycle] =
            (bool)fb_read_axis_err.isEnabled();
        rd_err_fb_valid_ptr[recorded_cycle] = (bool)fb_read_axis_err.isValid();
        rd_err_fb_busy_ptr[recorded_cycle]  = (bool)fb_read_axis_err.isBusy();
        rd_err_fb_error_ptr[recorded_cycle] = (bool)fb_read_axis_err.isError();
        rd_err_fb_error_id_ptr[recorded_cycle]   = fb_read_status.getErrorID();
        rd_err_axis_error_id_ptr[recorded_cycle] = fb_error_id;

        recorded_cycle++;
      }
    }
    cycle_count++;
    /* Print axis pos and vel when verbose enabled */
    if (verbose)
      printf("Count: %ld, Current position: %f,\tvelocity: %f,\ttorque: %f \n",
             cycle_count, fb_read_pos.getFloatValue(),
             fb_read_vel.getFloatValue(), fb_read_toq.getFloatValue());
  }
  return nullptr;
}

static void save_log(unsigned int len, char* log_file)
{
  FILE* fptr;

  // Open file
  if ((fptr = fopen(log_file, "a")) == nullptr)
  {
    printf("Error when open file \"%s\".\n", log_file);
    return;
  }

  if (len > running_cycle_10min)
  {
    printf("Error! Writing length larger than the max arry size.\n");
    fclose(fptr);
    return;
  }

  // Write data
  for (size_t i = 0; i < len; ++i)
  {
    fprintf(fptr, "%ld,", cycle_count_ptr[i]);
    fprintf(fptr, "%f,", act_pos_ptr[i]);
    fprintf(fptr, "%f,", act_vel_ptr[i]);
    fprintf(fptr, "%f,", act_toq_ptr[i]);
    /* FbPower */
    fprintf(fptr, "%d,", power_fb_enable_ptr[i]);
    fprintf(fptr, "%d,", power_fb_enb_positive_ptr[i]);
    fprintf(fptr, "%d,", power_fb_enb_negative_ptr[i]);
    fprintf(fptr, "%d,", power_fb_status_ptr[i]);
    fprintf(fptr, "%d,", power_fb_valid_ptr[i]);
    fprintf(fptr, "%d,", power_fb_error_ptr[i]);
    fprintf(fptr, "%d,", power_fb_error_id_ptr[i]);
    /* FbReset */
    fprintf(fptr, "%d,", reset_fb_exec_ptr[i]);
    fprintf(fptr, "%d,", reset_fb_done_ptr[i]);
    fprintf(fptr, "%d,", reset_fb_busy_ptr[i]);
    fprintf(fptr, "%d,", reset_fb_error_ptr[i]);
    fprintf(fptr, "%d,", reset_fb_error_id_ptr[i]);
    /* FbReadStatus */
    fprintf(fptr, "%d,", rd_sta_fb_enable_ptr[i]);
    fprintf(fptr, "%d,", rd_sta_fb_valid_ptr[i]);
    fprintf(fptr, "%d,", rd_sta_fb_busy_ptr[i]);
    fprintf(fptr, "%d,", rd_sta_fb_error_ptr[i]);
    fprintf(fptr, "%d,", rd_sta_fb_error_id_ptr[i]);
    fprintf(fptr, "%d,", rd_sta_fb_error_stop_ptr[i]);
    fprintf(fptr, "%d,", rd_sta_fb_disabled_ptr[i]);
    fprintf(fptr, "%d,", rd_sta_fb_stopping_ptr[i]);
    fprintf(fptr, "%d,", rd_sta_fb_homing_ptr[i]);
    fprintf(fptr, "%d,", rd_sta_fb_standstill_ptr[i]);
    fprintf(fptr, "%d,", rd_sta_fb_dis_motion_ptr[i]);
    fprintf(fptr, "%d,", rd_sta_fb_con_motion_ptr[i]);
    fprintf(fptr, "%d,", rd_sta_fb_syn_motion_ptr[i]);
    /* FbReadAxisError */
    fprintf(fptr, "%d,", rd_err_fb_enable_ptr[i]);
    fprintf(fptr, "%d,", rd_err_fb_valid_ptr[i]);
    fprintf(fptr, "%d,", rd_err_fb_busy_ptr[i]);
    fprintf(fptr, "%d,", rd_err_fb_error_ptr[i]);
    fprintf(fptr, "%d,", rd_err_fb_error_id_ptr[i]);
    fprintf(fptr, "%d\n", rd_err_axis_error_id_ptr[i]);
  }

  fclose(fptr);
}

static void getOptions(int argc, char** argv)
{
  int index;
  static struct option long_options[] = {
    // name		 has_arg				flag	val
    { "log", no_argument, nullptr, 'l' },
    { "eni", required_argument, nullptr, 'n' },
    { "interval", required_argument, nullptr, 'i' },
    { "ratio", required_argument, nullptr, 'r' },
    { "verbose", required_argument, nullptr, 'v' },
    { "help", no_argument, nullptr, 'h' },
    {}
  };
  do
  {
    index = getopt_long(argc, argv, "n:i:r:lvh", long_options, nullptr);
    switch (index)
    {
      case 'l':
        log_flag = true;
        printf("log: output FBs state as a csv file.\n");
        break;
      case 'n':
        if (eni_file)
          free(eni_file);
        eni_file = static_cast<char*>(malloc(strlen(optarg) + 1));
        memset(eni_file, 0, strlen(optarg) + 1);
        memmove(eni_file, optarg, strlen(optarg) + 1);
        printf("Using %s\n", eni_file);
        break;
      case 'i':
        cycle_us = (unsigned int)atof(optarg);
        printf("Time: Set running interval to %d us\n", cycle_us);
        break;
      case 'r':
        ratio = (u_int64_t)atof(optarg);
        printf("Ratio: Set encoder ratio to %ld\n", ratio);
        break;
      case 'v':
        verbose = true;
        printf("verbose: print pos and vel values.\n");
        break;
      case 'h':
        printf("Global options:\n");
        printf("    --eni       -n  Specify ENI/XML file\n");
        printf("    --int       -i  Specify RT cycle time\n");
        printf("    --log       -l  Output .csv log data 10 minutes\n");
        printf("    --rat       -r  Specify encoder ratio\n");
        printf("    --ver       -v  Specify verbose print\n");
        printf("    --help      -h  Show this help.\n");
        exit(0);
        break;
    }
  } while (index != -1);
}

static void init_stat()
{
  cycle_count_ptr =
      (uint64_t*)malloc(sizeof(uint64_t) * uint(running_cycle_10min));
  memset(cycle_count_ptr, 0, sizeof(uint64_t) * uint(running_cycle_10min));
  act_pos_ptr = (float*)malloc(sizeof(float) * uint(running_cycle_10min));
  memset(act_pos_ptr, 0, sizeof(float) * uint(running_cycle_10min));
  act_vel_ptr = (float*)malloc(sizeof(float) * uint(running_cycle_10min));
  memset(act_vel_ptr, 0, sizeof(float) * uint(running_cycle_10min));
  act_toq_ptr = (float*)malloc(sizeof(float) * uint(running_cycle_10min));
  memset(act_toq_ptr, 0, sizeof(float) * uint(running_cycle_10min));
  /* FbPower */
  power_fb_enable_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(power_fb_enable_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  power_fb_enb_positive_ptr =
      (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(power_fb_enb_positive_ptr, 0,
         sizeof(bool) * uint(running_cycle_10min));
  power_fb_enb_negative_ptr =
      (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(power_fb_enb_negative_ptr, 0,
         sizeof(bool) * uint(running_cycle_10min));
  power_fb_status_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(power_fb_status_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  power_fb_valid_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(power_fb_valid_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  power_fb_error_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(power_fb_error_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  power_fb_error_id_ptr =
      (uint16_t*)malloc(sizeof(uint16_t) * uint(running_cycle_10min));
  memset(power_fb_error_id_ptr, 0,
         sizeof(uint16_t) * uint(running_cycle_10min));
  /* FbReset */
  reset_fb_exec_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(reset_fb_exec_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  reset_fb_done_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(reset_fb_done_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  reset_fb_busy_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(reset_fb_busy_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  reset_fb_error_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(reset_fb_error_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  reset_fb_error_id_ptr =
      (uint16_t*)malloc(sizeof(uint16_t) * uint(running_cycle_10min));
  memset(reset_fb_error_id_ptr, 0,
         sizeof(uint16_t) * uint(running_cycle_10min));
  /* FbReadStatus */
  rd_sta_fb_enable_ptr =
      (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(rd_sta_fb_enable_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  rd_sta_fb_valid_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(rd_sta_fb_valid_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  rd_sta_fb_busy_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(rd_sta_fb_busy_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  rd_sta_fb_error_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(rd_sta_fb_error_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  rd_sta_fb_error_id_ptr =
      (uint16_t*)malloc(sizeof(uint16_t) * uint(running_cycle_10min));
  memset(rd_sta_fb_error_id_ptr, 0,
         sizeof(uint16_t) * uint(running_cycle_10min));
  rd_sta_fb_error_stop_ptr =
      (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(rd_sta_fb_error_stop_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  rd_sta_fb_disabled_ptr =
      (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(rd_sta_fb_disabled_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  rd_sta_fb_stopping_ptr =
      (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(rd_sta_fb_stopping_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  rd_sta_fb_homing_ptr =
      (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(rd_sta_fb_homing_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  rd_sta_fb_standstill_ptr =
      (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(rd_sta_fb_standstill_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  rd_sta_fb_dis_motion_ptr =
      (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(rd_sta_fb_dis_motion_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  rd_sta_fb_con_motion_ptr =
      (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(rd_sta_fb_con_motion_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  rd_sta_fb_syn_motion_ptr =
      (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(rd_sta_fb_syn_motion_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  /* FbReadAxisError */
  rd_err_fb_enable_ptr =
      (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(rd_err_fb_enable_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  rd_err_fb_valid_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(rd_err_fb_valid_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  rd_err_fb_busy_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(rd_err_fb_busy_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  rd_err_fb_error_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(rd_err_fb_error_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  rd_err_fb_error_id_ptr =
      (uint16_t*)malloc(sizeof(uint16_t) * uint(running_cycle_10min));
  memset(rd_err_fb_error_id_ptr, 0,
         sizeof(uint16_t) * uint(running_cycle_10min));
  rd_err_axis_error_id_ptr =
      (uint16_t*)malloc(sizeof(uint16_t) * uint(running_cycle_10min));
  memset(rd_err_axis_error_id_ptr, 0,
         sizeof(uint16_t) * uint(running_cycle_10min));
}

int main(int argc, char* argv[])
{
  getOptions(argc, argv);
  struct timespec dc_period;
  auto signal_handler = [](int /*unused*/) { run = 0; };
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

  /* Create motion domain */
  if (motion_servo_domain_entry_register(master, &domain))
  {
    return -1;
  }

  if (!motion_servo_driver_register(master, domain))
  {
    return -1;
  }

  motion_servo_set_send_interval(master);
  motion_servo_register_dc(master);
  clock_gettime(CLOCK_MONOTONIC, &dc_period);
  motion_master_set_application_time(master, TIMESPEC2NS(dc_period));

  if (motion_servo_master_activate(master->master))
  {
    printf("Fail to activate master\n");
    return -1;
  }

  domain1 = motion_servo_domain_data(domain);
  if (!domain1)
  {
    printf("Fail to get domain data\n");
    return 0;
  }

  /* Create motion servo */
  my_servo = new EcrtServo();
  my_servo->setMaster(master);
  my_servo->setDomain(domain1);
  my_servo->initialize(0, 0);
  Servo* servo = (Servo*)my_servo;

  /* Create motion axis */
  AxisConfig config;
  config.encoder_count_per_unit_ = ratio;
  config.frequency_              = 1.0 / cycle_us * 1000000;
  axis                           = new RTmotion::Axis();
  axis->setAxisId(1);
  axis->setAxisConfig(&config);
  axis->setServo(servo);

  /* Create motion function blocks */
  fb_power.setAxis(axis);
  fb_power.setEnable(mcFALSE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  fb_reset.setAxis(axis);
  fb_reset.setEnable(mcFALSE);

  fb_read_pos.setAxis(axis);
  fb_read_pos.setEnable(mcTRUE);

  fb_read_vel.setAxis(axis);
  fb_read_vel.setEnable(mcTRUE);

  fb_read_toq.setAxis(axis);
  fb_read_toq.setEnable(mcTRUE);

  fb_read_status.setAxis(axis);
  fb_read_status.setEnable(mcTRUE);

  fb_read_axis_err.setAxis(axis);
  fb_read_axis_err.setEnable(mcTRUE);

  if (log_flag)
  {
    init_stat();

    /* create new csv file */
    if ((log_fptr = fopen(log_file_name, "w+")) == nullptr)
    {
      printf("Error when open file \"%s\".\n", log_file_name);
      return 1;
    }

    /* write columns at first line */
    fprintf(log_fptr, "%s\n", column_string);
    fclose(log_fptr);
  }

  /* Create cyclic RT-thread */
  pthread_attr_t thattr;
  pthread_attr_init(&thattr);
  pthread_attr_setdetachstate(&thattr, PTHREAD_CREATE_JOINABLE);

  if (pthread_create(&cyclic_thread, &thattr, &my_thread, nullptr))
  {
    fprintf(stderr, "pthread_create cyclic task failed\n");
    return 1;
  }

  /* Wait until RT thread exit */
  while (run)
    usleep(10000);

  /* Post processing */
  pthread_join(cyclic_thread, nullptr);
  motion_servo_master_release(master);
  delete my_servo;
  delete axis;

  /* Open file to write execution time record */
  if (log_flag && recorded_cycle > 0)
    save_log(recorded_cycle, log_file_name);

  free(cycle_count_ptr);
  free(act_pos_ptr);
  free(act_vel_ptr);
  free(act_toq_ptr);
  /* FbPower */
  free(power_fb_enable_ptr);
  free(power_fb_enb_positive_ptr);
  free(power_fb_enb_negative_ptr);
  free(power_fb_status_ptr);
  free(power_fb_valid_ptr);
  free(power_fb_error_ptr);
  free(power_fb_error_id_ptr);
  /* FbReset */
  free(reset_fb_exec_ptr);
  free(reset_fb_done_ptr);
  free(reset_fb_busy_ptr);
  free(reset_fb_error_ptr);
  free(reset_fb_error_id_ptr);
  /* FbReadStatus */
  free(rd_sta_fb_enable_ptr);
  free(rd_sta_fb_valid_ptr);
  free(rd_sta_fb_busy_ptr);
  free(rd_sta_fb_error_ptr);
  free(rd_sta_fb_error_id_ptr);
  free(rd_sta_fb_error_stop_ptr);
  free(rd_sta_fb_disabled_ptr);
  free(rd_sta_fb_stopping_ptr);
  free(rd_sta_fb_homing_ptr);
  free(rd_sta_fb_standstill_ptr);
  free(rd_sta_fb_dis_motion_ptr);
  free(rd_sta_fb_con_motion_ptr);
  free(rd_sta_fb_syn_motion_ptr);
  /* FbReadAxisError */
  free(rd_err_fb_enable_ptr);
  free(rd_err_fb_valid_ptr);
  free(rd_err_fb_busy_ptr);
  free(rd_err_fb_error_ptr);
  free(rd_err_fb_error_id_ptr);
  free(rd_err_axis_error_id_ptr);
  printf("End of Program\n");
  return 0;
}
