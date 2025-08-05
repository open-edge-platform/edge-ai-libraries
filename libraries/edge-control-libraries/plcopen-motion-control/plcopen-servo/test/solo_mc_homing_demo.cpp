// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

#include <fb/common/include/axis.hpp>
#include <fb/public/include/fb_homing.hpp>
#include <fb/private/include/fb_set_position.hpp>
#include <fb/public/include/fb_move_relative.hpp>
#include <fb/public/include/fb_power.hpp>
#include <fb/public/include/fb_read_actual_position.hpp>
#include <fb/private/include/fb_read_actual_torque.hpp>
#include <fb/public/include/fb_read_actual_velocity.hpp>
#include <fb/private/include/fb_read_axis_info.hpp>
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
static bool log_flag  = false;
static char* eni_file = nullptr;
static bool verbose   = false;
static uint64_t ratio = PER_CIRCLE_ENCODER;

// RTmotion related
using namespace RTmotion;
static AXIS_REF axis;
static FbPower fb_power;
static FbMoveRelative fb_move;
static FbHoming fb_homing;
static FbSetPosition fb_set_position;
static FbReadActualPosition fb_read_pos;
static FbReadActualVelocity fb_read_vel;
static FbReadActualTorque fb_read_toq;
static FbReadAxisInfo fb_read_axis_info;
/* FbHoming */
static MC_DIRECTION homing_dir            = mcPositiveDirection;
static mcBOOL homing_abs_switch_sig       = mcFALSE;
static mcBOOL homing_limit_switch_neg_sig = mcFALSE;
static mcBOOL homing_limit_switch_pos_sig = mcFALSE;
static float homing_limit_offset          = 0.0;
/* FbSetPosition */
static float set_position_pos                 = 50.0;
static MC_SET_POSITION_MODE set_position_mode = mcSetPositionModeRelative;

// log data
static char column_string[]      = "cycle_count, act_pos, act_vel, act_toq, \
                               FbHoming.Execute, \
                               FbHoming.Direction, \
                               FbHoming.AbsoluteSwitchSignal, \
                               FbHoming.LimitSwitchNegativeSignal, \
                               FbHoming.LimitSwitchPositiveSignal, \
                               FbHoming.LimitOffset, \
                               FbHoming.Velocity, \
                               FbHoming.Acceleration, \
                               FbHoming.Jerk, \
                               FbHoming.Done, \
                               FbHoming.Busy, \
                               FbHoming.Active, \
                               FbHoming.CommandAborted, \
                               FbHoming.Error, \
                               FbHoming.ErrorID, \
                               FbSetPosition.Execute, \
                               FbSetPosition.Positon, \
                               FbSetPosition.Mode, \
                               FbSetPosition.Done, \
                               FbSetPosition.Busy, \
                               FbSetPosition.Error, \
                               FbSetPosition.ErrorID, \
                               FbReadAxisInfo.Execute, \
                               FbReadAxisInfo.Valid, \
                               FbReadAxisInfo.Busy, \
                               FbReadAxisInfo.Error, \
                               FbReadAxisInfo.ErrorID, \
                               FbReadAxisInfo.HomeAbsSwitch, \
                               FbReadAxisInfo.LimitSwitchPos, \
                               FbReadAxisInfo.LimitSwitchNeg, \
                               FbReadAxisInfo.Simulation, \
                               FbReadAxisInfo.CommunicationReady, \
                               FbReadAxisInfo.ReadyForPowerOn, \
                               FbReadAxisInfo.PowerOn, \
                               FbReadAxisInfo.IsHomed, \
                               FbReadAxisInfo.Warning";
static char log_file_name[20]    = "data.csv";
static FILE* log_fptr            = nullptr;
static uint64_t* cycle_count_ptr = nullptr;
static float* act_pos_ptr        = nullptr;
static float* act_vel_ptr        = nullptr;
static float* act_toq_ptr        = nullptr;
/* FbHoming */
static bool* homing_fb_exec_ptr                 = nullptr;
static uint8_t* homing_fb_dir_ptr               = nullptr;
static bool* homing_fb_abs_switch_sig_ptr       = nullptr;
static bool* homing_fb_limit_switch_neg_sig_ptr = nullptr;
static bool* homing_fb_limit_switch_pos_sig_ptr = nullptr;
static float* homing_fb_limit_offset_ptr        = nullptr;
static float* homing_fb_vel_ptr                 = nullptr;
static float* homing_fb_acc_ptr                 = nullptr;
static float* homing_fb_jerk_ptr                = nullptr;
static bool* homing_fb_done_ptr                 = nullptr;
static bool* homing_fb_busy_ptr                 = nullptr;
static bool* homing_fb_active_ptr               = nullptr;
static bool* homing_fb_cmd_aborted_ptr          = nullptr;
static bool* homing_fb_error_ptr                = nullptr;
static uint16_t* homing_fb_error_id_ptr         = nullptr;
/* FbSetPosition */
static bool* set_pos_fb_exec_ptr         = nullptr;
static float* set_pos_fb_pos_ptr         = nullptr;
static uint8_t* set_pos_fb_mode_ptr      = nullptr;
static bool* set_pos_fb_done_ptr         = nullptr;
static bool* set_pos_fb_busy_ptr         = nullptr;
static bool* set_pos_fb_error_ptr        = nullptr;
static uint16_t* set_pos_fb_error_id_ptr = nullptr;
/* FbReadAxisInfo */
static bool* rd_axis_fb_exec_ptr             = nullptr;
static bool* rd_axis_fb_valid_ptr            = nullptr;
static bool* rd_axis_fb_busy_ptr             = nullptr;
static bool* rd_axis_fb_error_ptr            = nullptr;
static uint16_t* rd_axis_fb_error_id_ptr     = nullptr;
static bool* rd_axis_fb_home_abs_switch_ptr  = nullptr;
static bool* rd_axis_fb_limit_switch_pos_ptr = nullptr;
static bool* rd_axis_fb_limit_switch_neg_ptr = nullptr;
static bool* rd_axis_fb_simulation_ptr       = nullptr;
static bool* rd_axis_fb_comm_ready_ptr       = nullptr;
static bool* rd_axis_fb_rdy_for_power_on_ptr = nullptr;
static bool* rd_axis_fb_power_on_ptr         = nullptr;
static bool* rd_axis_fb_is_homed_ptr         = nullptr;
static bool* rd_axis_fb_warning_ptr          = nullptr;
static unsigned int running_cycle_10min =
    (unsigned int)(CYCLE_COUNTER_PERSEC(cycle_us) * 600);
static unsigned int recorded_cycle = 0;

typedef enum
{
  MC_DEMO_POWER_ON = 0,
  MC_DEMO_HOMING,
  MC_DEMO_SET_POSITION,
  MC_DEMO_MOVE_RELATIVE
} MC_DEMO_HOME_TEST;
static MC_DEMO_HOME_TEST s_homing_deme_func = MC_DEMO_POWER_ON;

// RT thread function
void* my_thread(void* /*arg*/)
{
  struct timespec next_period, dc_period;
  uint64_t cycle_count = 0;

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
    fb_move.runCycle();
    fb_homing.runCycle();
    fb_set_position.runCycle();
    fb_read_pos.runCycle();
    fb_read_vel.runCycle();
    fb_read_toq.runCycle();
    fb_read_axis_info.runCycle();

    switch (s_homing_deme_func)
    {
      case MC_DEMO_POWER_ON: {
        if (fb_power.getPowerStatus() == mcTRUE)
        {
          s_homing_deme_func = MC_DEMO_HOMING;
          printf("Axis is powered on. Continue to execute fb_homing.\n");
        }
      }
      break;
      case MC_DEMO_HOMING: {
        if (fb_homing.isDone() == mcTRUE)
        {
          fb_homing.setExecute(mcFALSE);
          fb_set_position.setPosition(set_position_pos);
          s_homing_deme_func = MC_DEMO_SET_POSITION;
          printf(
              "Homing FB execute done. Continue to execute fb_set_position.\n");
        }
        else
        {
          fb_homing.setExecute(mcTRUE);
          if (abs(fb_read_pos.getFloatValue() - 10.0) < 0.1)
          {
            homing_limit_switch_neg_sig = mcTRUE;
            fb_homing.setLimitNegSignal(homing_limit_switch_neg_sig);
          }
          else if (abs(fb_read_pos.getFloatValue() - 20.0) < 0.1)
          {
            homing_abs_switch_sig = mcTRUE;
            fb_homing.setRefSignal(homing_abs_switch_sig);
          }
          else if (abs(fb_read_pos.getFloatValue() - 30.0) < 0.1)
          {
            homing_abs_switch_sig = mcFALSE;
            fb_homing.setRefSignal(homing_abs_switch_sig);
          }
        }
      }
      break;
      case MC_DEMO_SET_POSITION: {
        if (fb_set_position.isDone() == mcTRUE)
        {
          fb_set_position.setEnable(mcFALSE);
          s_homing_deme_func = MC_DEMO_MOVE_RELATIVE;
          printf("Set_position FB execute done. Continue to execute "
                 "fb_move_relative.\n");
        }
        else
          fb_set_position.setEnable(mcTRUE);
      }
      break;
      case MC_DEMO_MOVE_RELATIVE: {
        if (fb_move.isDone() == mcTRUE)
          fb_move.setExecute(mcFALSE);
        else
          fb_move.setExecute(mcTRUE);
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
        /* FbHoming */
        homing_fb_exec_ptr[recorded_cycle] = (bool)fb_homing.isEnabled();
        homing_fb_dir_ptr[recorded_cycle]  = (uint8_t)homing_dir;
        homing_fb_abs_switch_sig_ptr[recorded_cycle] =
            (bool)homing_abs_switch_sig;
        homing_fb_limit_switch_neg_sig_ptr[recorded_cycle] =
            (bool)homing_limit_switch_neg_sig;
        homing_fb_limit_switch_pos_sig_ptr[recorded_cycle] =
            (bool)homing_limit_switch_pos_sig;
        homing_fb_limit_offset_ptr[recorded_cycle] = homing_limit_offset;
        homing_fb_vel_ptr[recorded_cycle]          = fb_homing.getVelocity();
        homing_fb_acc_ptr[recorded_cycle]         = fb_homing.getAcceleration();
        homing_fb_jerk_ptr[recorded_cycle]        = fb_homing.getJerk();
        homing_fb_done_ptr[recorded_cycle]        = (bool)fb_homing.isDone();
        homing_fb_busy_ptr[recorded_cycle]        = (bool)fb_homing.isBusy();
        homing_fb_active_ptr[recorded_cycle]      = (bool)fb_homing.isActive();
        homing_fb_cmd_aborted_ptr[recorded_cycle] = (bool)fb_homing.isAborted();
        homing_fb_error_ptr[recorded_cycle]       = (bool)fb_homing.isError();
        homing_fb_error_id_ptr[recorded_cycle]    = fb_homing.getErrorID();
        /* FbSetPosition */
        set_pos_fb_exec_ptr[recorded_cycle] = (bool)fb_set_position.isEnabled();
        set_pos_fb_pos_ptr[recorded_cycle]  = set_position_pos;
        set_pos_fb_mode_ptr[recorded_cycle] = (uint8_t)set_position_mode;
        set_pos_fb_done_ptr[recorded_cycle] = (bool)fb_set_position.isDone();
        set_pos_fb_busy_ptr[recorded_cycle] = (bool)fb_set_position.isBusy();
        set_pos_fb_error_ptr[recorded_cycle] = (bool)fb_set_position.isError();
        set_pos_fb_error_id_ptr[recorded_cycle] = fb_set_position.getErrorID();
        /* FbReadAxisInfo */
        rd_axis_fb_exec_ptr[recorded_cycle] =
            (bool)fb_read_axis_info.isEnabled();
        rd_axis_fb_valid_ptr[recorded_cycle] =
            (bool)fb_read_axis_info.isValid();
        rd_axis_fb_busy_ptr[recorded_cycle] = (bool)fb_read_axis_info.isBusy();
        rd_axis_fb_error_ptr[recorded_cycle] =
            (bool)fb_read_axis_info.isError();
        rd_axis_fb_error_id_ptr[recorded_cycle] =
            fb_read_axis_info.getErrorID();
        rd_axis_fb_home_abs_switch_ptr[recorded_cycle] =
            (bool)fb_read_axis_info.getAxisHomeAbsSwitch();
        rd_axis_fb_limit_switch_pos_ptr[recorded_cycle] =
            (bool)fb_read_axis_info.getAxisLimitSwitchPos();
        rd_axis_fb_limit_switch_neg_ptr[recorded_cycle] =
            (bool)fb_read_axis_info.getAxisLimitSwitchNeg();
        rd_axis_fb_simulation_ptr[recorded_cycle] =
            (bool)fb_read_axis_info.getAxisSimulation();
        rd_axis_fb_comm_ready_ptr[recorded_cycle] =
            (bool)fb_read_axis_info.getAxisCommunicationReady();
        rd_axis_fb_rdy_for_power_on_ptr[recorded_cycle] =
            (bool)fb_read_axis_info.getAxisReadyForPowerOn();
        rd_axis_fb_power_on_ptr[recorded_cycle] =
            (bool)fb_read_axis_info.getAxisPowerOn();
        rd_axis_fb_is_homed_ptr[recorded_cycle] =
            (bool)fb_read_axis_info.getAxisIsHomed();
        rd_axis_fb_warning_ptr[recorded_cycle] =
            (bool)fb_read_axis_info.getAxisWarning();

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
    /* FbHoming */
    fprintf(fptr, "%d,", homing_fb_exec_ptr[i]);
    fprintf(fptr, "%d,", homing_fb_dir_ptr[i]);
    fprintf(fptr, "%d,", homing_fb_abs_switch_sig_ptr[i]);
    fprintf(fptr, "%d,", homing_fb_limit_switch_neg_sig_ptr[i]);
    fprintf(fptr, "%d,", homing_fb_limit_switch_pos_sig_ptr[i]);
    fprintf(fptr, "%f,", homing_fb_limit_offset_ptr[i]);
    fprintf(fptr, "%f,", homing_fb_vel_ptr[i]);
    fprintf(fptr, "%f,", homing_fb_acc_ptr[i]);
    fprintf(fptr, "%f,", homing_fb_jerk_ptr[i]);
    fprintf(fptr, "%d,", homing_fb_done_ptr[i]);
    fprintf(fptr, "%d,", homing_fb_busy_ptr[i]);
    fprintf(fptr, "%d,", homing_fb_active_ptr[i]);
    fprintf(fptr, "%d,", homing_fb_cmd_aborted_ptr[i]);
    fprintf(fptr, "%d,", homing_fb_error_ptr[i]);
    fprintf(fptr, "%d,", homing_fb_error_id_ptr[i]);
    /* FbSetPosition */
    fprintf(fptr, "%d,", set_pos_fb_exec_ptr[i]);
    fprintf(fptr, "%f,", set_pos_fb_pos_ptr[i]);
    fprintf(fptr, "%d,", set_pos_fb_mode_ptr[i]);
    fprintf(fptr, "%d,", set_pos_fb_done_ptr[i]);
    fprintf(fptr, "%d,", set_pos_fb_busy_ptr[i]);
    fprintf(fptr, "%d,", set_pos_fb_error_ptr[i]);
    fprintf(fptr, "%d,", set_pos_fb_error_id_ptr[i]);
    /* FbReadAxisInfo */
    fprintf(fptr, "%d,", rd_axis_fb_exec_ptr[i]);
    fprintf(fptr, "%d,", rd_axis_fb_valid_ptr[i]);
    fprintf(fptr, "%d,", rd_axis_fb_busy_ptr[i]);
    fprintf(fptr, "%d,", rd_axis_fb_error_ptr[i]);
    fprintf(fptr, "%d,", rd_axis_fb_error_id_ptr[i]);
    fprintf(fptr, "%d,", rd_axis_fb_home_abs_switch_ptr[i]);
    fprintf(fptr, "%d,", rd_axis_fb_limit_switch_pos_ptr[i]);
    fprintf(fptr, "%d,", rd_axis_fb_limit_switch_neg_ptr[i]);
    fprintf(fptr, "%d,", rd_axis_fb_simulation_ptr[i]);
    fprintf(fptr, "%d,", rd_axis_fb_comm_ready_ptr[i]);
    fprintf(fptr, "%d,", rd_axis_fb_rdy_for_power_on_ptr[i]);
    fprintf(fptr, "%d,", rd_axis_fb_power_on_ptr[i]);
    fprintf(fptr, "%d,", rd_axis_fb_is_homed_ptr[i]);
    fprintf(fptr, "%d\n", rd_axis_fb_warning_ptr[i]);
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
        printf("verbose: print pos, vel and torque values.\n");
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
  /* FbHoming */
  homing_fb_exec_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(homing_fb_exec_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  homing_fb_dir_ptr =
      (uint8_t*)malloc(sizeof(uint8_t) * uint(running_cycle_10min));
  memset(homing_fb_dir_ptr, 0, sizeof(uint8_t) * uint(running_cycle_10min));
  homing_fb_abs_switch_sig_ptr =
      (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(homing_fb_abs_switch_sig_ptr, 0,
         sizeof(bool) * uint(running_cycle_10min));
  homing_fb_limit_switch_neg_sig_ptr =
      (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(homing_fb_limit_switch_neg_sig_ptr, 0,
         sizeof(bool) * uint(running_cycle_10min));
  homing_fb_limit_switch_pos_sig_ptr =
      (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(homing_fb_limit_switch_pos_sig_ptr, 0,
         sizeof(bool) * uint(running_cycle_10min));
  homing_fb_limit_offset_ptr =
      (float*)malloc(sizeof(float) * uint(running_cycle_10min));
  memset(homing_fb_limit_offset_ptr, 0,
         sizeof(float) * uint(running_cycle_10min));
  homing_fb_vel_ptr = (float*)malloc(sizeof(float) * uint(running_cycle_10min));
  memset(homing_fb_vel_ptr, 0, sizeof(float) * uint(running_cycle_10min));
  homing_fb_acc_ptr = (float*)malloc(sizeof(float) * uint(running_cycle_10min));
  memset(homing_fb_acc_ptr, 0, sizeof(float) * uint(running_cycle_10min));
  homing_fb_jerk_ptr =
      (float*)malloc(sizeof(float) * uint(running_cycle_10min));
  memset(homing_fb_jerk_ptr, 0, sizeof(float) * uint(running_cycle_10min));
  homing_fb_done_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(homing_fb_done_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  homing_fb_busy_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(homing_fb_busy_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  homing_fb_active_ptr =
      (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(homing_fb_active_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  homing_fb_cmd_aborted_ptr =
      (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(homing_fb_cmd_aborted_ptr, 0,
         sizeof(bool) * uint(running_cycle_10min));
  homing_fb_error_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(homing_fb_error_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  homing_fb_error_id_ptr =
      (uint16_t*)malloc(sizeof(uint16_t) * uint(running_cycle_10min));
  memset(homing_fb_error_id_ptr, 0,
         sizeof(uint16_t) * uint(running_cycle_10min));
  /* FbSetPosition */
  set_pos_fb_exec_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(set_pos_fb_exec_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  set_pos_fb_pos_ptr =
      (float*)malloc(sizeof(float) * uint(running_cycle_10min));
  memset(set_pos_fb_pos_ptr, 0, sizeof(float) * uint(running_cycle_10min));
  set_pos_fb_mode_ptr =
      (uint8_t*)malloc(sizeof(uint8_t) * uint(running_cycle_10min));
  memset(set_pos_fb_mode_ptr, 0, sizeof(uint8_t) * uint(running_cycle_10min));
  set_pos_fb_done_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(set_pos_fb_done_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  set_pos_fb_busy_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(set_pos_fb_busy_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  set_pos_fb_error_ptr =
      (bool*)malloc(sizeof(float) * uint(running_cycle_10min));
  memset(set_pos_fb_error_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  set_pos_fb_error_id_ptr =
      (uint16_t*)malloc(sizeof(uint16_t) * uint(running_cycle_10min));
  memset(set_pos_fb_error_id_ptr, 0,
         sizeof(uint16_t) * uint(running_cycle_10min));
  /* FbReadAxisInfo */
  rd_axis_fb_exec_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(rd_axis_fb_exec_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  rd_axis_fb_valid_ptr =
      (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(rd_axis_fb_valid_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  rd_axis_fb_busy_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(rd_axis_fb_busy_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  rd_axis_fb_error_ptr =
      (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(rd_axis_fb_error_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  rd_axis_fb_error_id_ptr =
      (uint16_t*)malloc(sizeof(uint16_t) * uint(running_cycle_10min));
  memset(rd_axis_fb_error_id_ptr, 0,
         sizeof(uint16_t) * uint(running_cycle_10min));
  rd_axis_fb_home_abs_switch_ptr =
      (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(rd_axis_fb_home_abs_switch_ptr, 0,
         sizeof(bool) * uint(running_cycle_10min));
  rd_axis_fb_limit_switch_pos_ptr =
      (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(rd_axis_fb_limit_switch_pos_ptr, 0,
         sizeof(bool) * uint(running_cycle_10min));
  rd_axis_fb_limit_switch_neg_ptr =
      (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(rd_axis_fb_limit_switch_neg_ptr, 0,
         sizeof(bool) * uint(running_cycle_10min));
  rd_axis_fb_simulation_ptr =
      (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(rd_axis_fb_simulation_ptr, 0,
         sizeof(bool) * uint(running_cycle_10min));
  rd_axis_fb_comm_ready_ptr =
      (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(rd_axis_fb_comm_ready_ptr, 0,
         sizeof(bool) * uint(running_cycle_10min));
  rd_axis_fb_rdy_for_power_on_ptr =
      (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(rd_axis_fb_rdy_for_power_on_ptr, 0,
         sizeof(bool) * uint(running_cycle_10min));
  rd_axis_fb_power_on_ptr =
      (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(rd_axis_fb_power_on_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  rd_axis_fb_is_homed_ptr =
      (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(rd_axis_fb_is_homed_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  rd_axis_fb_warning_ptr =
      (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(rd_axis_fb_warning_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
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
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  fb_move.setAxis(axis);
  fb_move.setPosition(100);
  fb_move.setVelocity(50);
  fb_move.setAcceleration(20);
  fb_move.setDeceleration(20);
  fb_move.setJerk(500);
  fb_move.setBufferMode(mcAborting);
  fb_move.setExecute(mcFALSE);

  fb_homing.setAxis(axis);
  fb_homing.setDirection(homing_dir);
  fb_homing.setVelocity(10);
  fb_homing.setAcceleration(20);
  fb_homing.setDeceleration(20);
  fb_homing.setJerk(500);
  fb_homing.setBufferMode(mcAborting);
  fb_homing.setExecute(mcFALSE);

  fb_set_position.setAxis(axis);
  fb_set_position.setMode(set_position_mode);
  fb_set_position.setEnable(mcFALSE);

  fb_read_pos.setAxis(axis);
  fb_read_pos.setEnable(mcTRUE);

  fb_read_vel.setAxis(axis);
  fb_read_vel.setEnable(mcTRUE);

  fb_read_toq.setAxis(axis);
  fb_read_toq.setEnable(mcTRUE);

  fb_read_axis_info.setAxis(axis);
  fb_read_axis_info.setEnable(mcTRUE);

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
  /* FbHoming */
  free(homing_fb_exec_ptr);
  free(homing_fb_dir_ptr);
  free(homing_fb_abs_switch_sig_ptr);
  free(homing_fb_limit_switch_neg_sig_ptr);
  free(homing_fb_limit_switch_pos_sig_ptr);
  free(homing_fb_limit_offset_ptr);
  free(homing_fb_vel_ptr);
  free(homing_fb_acc_ptr);
  free(homing_fb_jerk_ptr);
  free(homing_fb_done_ptr);
  free(homing_fb_busy_ptr);
  free(homing_fb_active_ptr);
  free(homing_fb_cmd_aborted_ptr);
  free(homing_fb_error_ptr);
  free(homing_fb_error_id_ptr);
  /* FbSetPosition */
  free(set_pos_fb_exec_ptr);
  free(set_pos_fb_pos_ptr);
  free(set_pos_fb_mode_ptr);
  free(set_pos_fb_done_ptr);
  free(set_pos_fb_busy_ptr);
  free(set_pos_fb_error_ptr);
  free(set_pos_fb_error_id_ptr);
  /* FbReadAxisInfo */
  free(rd_axis_fb_exec_ptr);
  free(rd_axis_fb_valid_ptr);
  free(rd_axis_fb_busy_ptr);
  free(rd_axis_fb_error_ptr);
  free(rd_axis_fb_error_id_ptr);
  free(rd_axis_fb_home_abs_switch_ptr);
  free(rd_axis_fb_limit_switch_pos_ptr);
  free(rd_axis_fb_limit_switch_neg_ptr);
  free(rd_axis_fb_simulation_ptr);
  free(rd_axis_fb_comm_ready_ptr);
  free(rd_axis_fb_rdy_for_power_on_ptr);
  free(rd_axis_fb_power_on_ptr);
  free(rd_axis_fb_is_homed_ptr);
  free(rd_axis_fb_warning_ptr);
  printf("End of Program\n");
  return 0;
}
