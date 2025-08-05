// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

#include <fb/common/include/axis.hpp>
#include <fb/public/include/fb_move_relative.hpp>
#include <fb/public/include/fb_power.hpp>
#include <fb/public/include/fb_read_actual_position.hpp>
#include <fb/private/include/fb_read_actual_torque.hpp>
#include <fb/public/include/fb_read_actual_velocity.hpp>
#include <fb/private/include/fb_set_controller_mode.hpp>
#include <fb/private/include/fb_torque_control.hpp>
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
static bool log_flag                  = false;
static char* eni_file                 = nullptr;
static bool verbose                   = false;
static uint64_t ratio                 = PER_CIRCLE_ENCODER;
static MC_SERVO_CONTROL_MODE set_mode = mcServoControlModePosition;

// RTmotion related
#define SET_TARGET_TORQUE 100
#define SET_MAX_PROFILE_VEL 5.0
using namespace RTmotion;
static AXIS_REF axis;
static FbPower fb_power;
static FbMoveRelative fb_move;
static FbTorqueControl fb_torque_control;
static FbReadActualPosition fb_read_pos;
static FbReadActualVelocity fb_read_vel;
static FbReadActualTorque fb_read_toq;
static FbSetControllerMode fb_set_controller_mode;

// log data
static char column_string[]      = "cycle_count, act_pos, act_vel, act_toq, \
                               FbTorqueControl.Torque, \
                               FbTorqueControl.Velocity, \
                               FbTorqueControl.Execute, \
                               FbTorqueControl.Done, \
                               FbTorqueControl.Busy, \
                               FbTorqueControl.Error, \
                               FbTorqueControl.ErrorID, \
                               FbReadTorque.Enable, \
                               FbReadTorque.Valid, \
                               FbReadTorque.Busy, \
                               FbReadTorque.Error, \
                               FbReadTorque.ErrorID, \
                               FbReadTorque.Torque, \
                               FbSetControllerMode.execute, \
                               FbSetControllerMode.mode, \
                               FbSetControllerMode.Done, \
                               FbSetControllerMode.Busy, \
                               FbSetControllerMode.Error, \
                               FbSetControllerMode.ErrorID";
static char log_file_name[20]    = "data.csv";
static FILE* log_fptr            = nullptr;
static uint64_t* cycle_count_ptr = nullptr;
static float* act_pos_ptr        = nullptr;
static float* act_vel_ptr        = nullptr;
static float* act_toq_ptr        = nullptr;
/* FbTorqueControl */
static int16_t* tar_toq_ptr          = nullptr;
static uint32_t* max_vel_ptr         = nullptr;
static bool* toq_fb_exec_ptr         = nullptr;
static bool* toq_fb_done_ptr         = nullptr;
static bool* toq_fb_busy_ptr         = nullptr;
static bool* toq_fb_error_ptr        = nullptr;
static uint16_t* toq_fb_error_id_ptr = nullptr;
/* FbReadTorque */
static bool* read_toq_fb_enable_ptr       = nullptr;
static bool* read_toq_fb_valid_ptr        = nullptr;
static bool* read_toq_fb_busy_ptr         = nullptr;
static bool* read_toq_fb_error_ptr        = nullptr;
static uint16_t* read_toq_fb_error_id_ptr = nullptr;
static float* read_toq_fb_torque_ptr      = nullptr;
/* FbSetControllerMode */
static bool* set_mode_fb_exec_ptr         = nullptr;
static uint8_t* set_mode_fb_mode_ptr      = nullptr;
static bool* set_mode_fb_done_ptr         = nullptr;
static bool* set_mode_fb_busy_ptr         = nullptr;
static bool* set_mode_fb_error_ptr        = nullptr;
static uint16_t* set_mode_fb_error_id_ptr = nullptr;
static unsigned int running_cycle_10min =
    (unsigned int)(CYCLE_COUNTER_PERSEC(cycle_us) * 600);
static unsigned int recorded_cycle = 0;

typedef enum
{
  MC_TORQUE_INIT = 0,
  MC_TORQUE_MOVE_RELATIVE,
  MC_TORQUE_SET_TORQUE_MODE,
  MC_TORQUE_TORQUE_CONTROL,
  MC_TORQUE_SET_POS_MODE,
} TORQUE_CONTROL_TEST;
static TORQUE_CONTROL_TEST s_torque_control_func = MC_TORQUE_INIT;
static uint32_t s_func_test_count                = 0;

// RT thread function
void* my_thread(void* /*arg*/)
{
  struct timespec next_period, dc_period;
  mcBOOL powered_on    = mcFALSE;
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
    fb_torque_control.runCycle();
    fb_read_pos.runCycle();
    fb_read_vel.runCycle();
    fb_read_toq.runCycle();
    fb_set_controller_mode.runCycle();
    powered_on = fb_power.getPowerStatus();

    switch (s_torque_control_func)
    {
      case MC_TORQUE_INIT: {
        if (powered_on == mcTRUE)
        {
          fb_read_toq.setEnable(mcTRUE);
          s_torque_control_func = MC_TORQUE_MOVE_RELATIVE;
          printf("Axis is powered on. Continue to execute fb_move.\n");
        }
      }
      break;
      case MC_TORQUE_MOVE_RELATIVE: {
        if (fb_move.isDone() == mcTRUE)
        {
          fb_move.setExecute(mcFALSE);
          s_torque_control_func = MC_TORQUE_SET_TORQUE_MODE;
          set_mode              = mcServoControlModeTorque;
          fb_set_controller_mode.setMode(set_mode);
          printf("fb_moveRelative test done, execute fb_setControllerMode.\n");
        }
        else
          fb_move.setExecute(mcTRUE);
      }
      break;
      case MC_TORQUE_SET_TORQUE_MODE: {
        if (fb_set_controller_mode.isDone() == mcTRUE)
        {
          fb_set_controller_mode.setEnable(mcFALSE);
          s_torque_control_func = MC_TORQUE_TORQUE_CONTROL;
        }
        else
          fb_set_controller_mode.setEnable(mcTRUE);
      }
      break;
      case MC_TORQUE_TORQUE_CONTROL: {
        fb_torque_control.setExecute(mcTRUE);
        if (fb_torque_control.isDone() == mcTRUE)
          printf("Torque control FB done. \n");
        if (s_func_test_count++ > 10000)
        {
          s_func_test_count     = 0;
          s_torque_control_func = MC_TORQUE_SET_POS_MODE;
          fb_torque_control.setExecute(mcFALSE);
          set_mode = mcServoControlModePosition;
          fb_set_controller_mode.setMode(set_mode);
          printf("fb_torqueControl test done, execute fb_setControllerMode.\n");
        }
      }
      break;
      case MC_TORQUE_SET_POS_MODE: {
        if (fb_set_controller_mode.isDone() == mcTRUE)
        {
          s_torque_control_func = MC_TORQUE_MOVE_RELATIVE;
          fb_set_controller_mode.setEnable(mcFALSE);
          fb_move.setExecute(mcFALSE);
          fb_move.setPosition(-fb_move.getPosition());
        }
        else
          fb_set_controller_mode.setEnable(mcTRUE);
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
        /* FbTorqueControl */
        tar_toq_ptr[recorded_cycle]      = SET_TARGET_TORQUE;
        max_vel_ptr[recorded_cycle]      = SET_MAX_PROFILE_VEL;
        toq_fb_exec_ptr[recorded_cycle]  = (bool)fb_torque_control.isEnabled();
        toq_fb_done_ptr[recorded_cycle]  = (bool)fb_torque_control.isDone();
        toq_fb_busy_ptr[recorded_cycle]  = (bool)fb_torque_control.isBusy();
        toq_fb_error_ptr[recorded_cycle] = (bool)fb_torque_control.isError();
        toq_fb_error_id_ptr[recorded_cycle] = fb_torque_control.getErrorID();
        /* FbReadTorque */
        read_toq_fb_enable_ptr[recorded_cycle] = (bool)fb_read_toq.isEnabled();
        read_toq_fb_valid_ptr[recorded_cycle]  = (bool)fb_read_toq.isValid();
        read_toq_fb_busy_ptr[recorded_cycle]   = (bool)fb_read_toq.isBusy();
        read_toq_fb_error_ptr[recorded_cycle]  = (bool)fb_read_toq.isError();
        read_toq_fb_error_id_ptr[recorded_cycle] = fb_read_toq.getErrorID();
        read_toq_fb_torque_ptr[recorded_cycle]   = fb_read_toq.getFloatValue();
        /* FbSetControllerMode */
        set_mode_fb_exec_ptr[recorded_cycle] =
            (bool)fb_set_controller_mode.isEnabled();
        set_mode_fb_mode_ptr[recorded_cycle] = (uint8_t)set_mode;
        set_mode_fb_done_ptr[recorded_cycle] =
            (bool)fb_set_controller_mode.isDone();
        set_mode_fb_busy_ptr[recorded_cycle] =
            (bool)fb_set_controller_mode.isBusy();
        set_mode_fb_error_ptr[recorded_cycle] =
            (bool)fb_set_controller_mode.isError();
        set_mode_fb_error_id_ptr[recorded_cycle] =
            fb_set_controller_mode.getErrorID();

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
    /* FbTorqueControl */
    fprintf(fptr, "%d,", tar_toq_ptr[i]);
    fprintf(fptr, "%d,", max_vel_ptr[i]);
    fprintf(fptr, "%d,", toq_fb_exec_ptr[i]);
    fprintf(fptr, "%d,", toq_fb_done_ptr[i]);
    fprintf(fptr, "%d,", toq_fb_busy_ptr[i]);
    fprintf(fptr, "%d,", toq_fb_error_ptr[i]);
    fprintf(fptr, "%d,", toq_fb_error_id_ptr[i]);
    /* FbReadTorque */
    fprintf(fptr, "%d,", read_toq_fb_enable_ptr[i]);
    fprintf(fptr, "%d,", read_toq_fb_valid_ptr[i]);
    fprintf(fptr, "%d,", read_toq_fb_busy_ptr[i]);
    fprintf(fptr, "%d,", read_toq_fb_error_ptr[i]);
    fprintf(fptr, "%d,", read_toq_fb_error_id_ptr[i]);
    fprintf(fptr, "%f,", read_toq_fb_torque_ptr[i]);
    /* FbSetControllerMode */
    fprintf(fptr, "%d,", set_mode_fb_exec_ptr[i]);
    fprintf(fptr, "%d,", set_mode_fb_mode_ptr[i]);
    fprintf(fptr, "%d,", set_mode_fb_done_ptr[i]);
    fprintf(fptr, "%d,", set_mode_fb_busy_ptr[i]);
    fprintf(fptr, "%d,", set_mode_fb_error_ptr[i]);
    fprintf(fptr, "%d\n", set_mode_fb_error_id_ptr[i]);
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
  /* FbTorqueControl */
  tar_toq_ptr = (int16_t*)malloc(sizeof(int16_t) * uint(running_cycle_10min));
  memset(tar_toq_ptr, 0, sizeof(int16_t) * uint(running_cycle_10min));
  max_vel_ptr = (uint32_t*)malloc(sizeof(uint32_t) * uint(running_cycle_10min));
  memset(max_vel_ptr, 0, sizeof(uint32_t) * uint(running_cycle_10min));
  toq_fb_exec_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(toq_fb_exec_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  toq_fb_done_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(toq_fb_done_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  toq_fb_busy_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(toq_fb_busy_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  toq_fb_error_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(toq_fb_error_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  toq_fb_error_id_ptr =
      (uint16_t*)malloc(sizeof(uint16_t) * uint(running_cycle_10min));
  memset(toq_fb_error_id_ptr, 0, sizeof(uint16_t) * uint(running_cycle_10min));
  /* FbReadTorque */
  read_toq_fb_enable_ptr =
      (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(read_toq_fb_enable_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  read_toq_fb_valid_ptr =
      (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(read_toq_fb_valid_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  read_toq_fb_busy_ptr =
      (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(read_toq_fb_busy_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  read_toq_fb_error_ptr =
      (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(read_toq_fb_error_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  read_toq_fb_error_id_ptr =
      (uint16_t*)malloc(sizeof(uint16_t) * uint(running_cycle_10min));
  memset(read_toq_fb_error_id_ptr, 0,
         sizeof(uint16_t) * uint(running_cycle_10min));
  read_toq_fb_torque_ptr =
      (float*)malloc(sizeof(float) * uint(running_cycle_10min));
  memset(read_toq_fb_torque_ptr, 0, sizeof(float) * uint(running_cycle_10min));
  /* FbSetControllerMode */
  set_mode_fb_exec_ptr =
      (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(set_mode_fb_exec_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  set_mode_fb_mode_ptr =
      (uint8_t*)malloc(sizeof(uint8_t) * uint(running_cycle_10min));
  memset(set_mode_fb_mode_ptr, 0, sizeof(uint8_t) * uint(running_cycle_10min));
  set_mode_fb_done_ptr =
      (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(set_mode_fb_done_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  set_mode_fb_busy_ptr =
      (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(set_mode_fb_busy_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  set_mode_fb_error_ptr =
      (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(set_mode_fb_error_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  set_mode_fb_error_id_ptr =
      (uint16_t*)malloc(sizeof(uint16_t) * uint(running_cycle_10min));
  memset(set_mode_fb_error_id_ptr, 0,
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

  fb_torque_control.setAxis(axis);
  fb_torque_control.setPosition(100);
  fb_torque_control.setVelocity(20);
  fb_torque_control.setTorque(SET_TARGET_TORQUE);
  fb_torque_control.setMaxProfileVelocity(SET_MAX_PROFILE_VEL);
  fb_torque_control.setAcceleration(20);
  fb_torque_control.setDeceleration(20);
  fb_torque_control.setJerk(500);
  fb_torque_control.setBufferMode(mcAborting);
  fb_torque_control.setExecute(mcFALSE);

  fb_read_pos.setAxis(axis);
  fb_read_pos.setEnable(mcTRUE);

  fb_read_vel.setAxis(axis);
  fb_read_vel.setEnable(mcTRUE);

  fb_read_toq.setAxis(axis);
  fb_read_toq.setEnable(mcFALSE);

  fb_set_controller_mode.setAxis(axis);
  fb_set_controller_mode.setEnable(mcFALSE);

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
  /* FbTorqueControl */
  free(tar_toq_ptr);
  free(max_vel_ptr);
  free(toq_fb_exec_ptr);
  free(toq_fb_done_ptr);
  free(toq_fb_busy_ptr);
  free(toq_fb_error_ptr);
  free(toq_fb_error_id_ptr);
  /* FbReadTorque */
  free(read_toq_fb_enable_ptr);
  free(read_toq_fb_valid_ptr);
  free(read_toq_fb_busy_ptr);
  free(read_toq_fb_error_ptr);
  free(read_toq_fb_error_id_ptr);
  free(read_toq_fb_torque_ptr);
  /* FbSetControllerMode */
  free(set_mode_fb_exec_ptr);
  free(set_mode_fb_mode_ptr);
  free(set_mode_fb_done_ptr);
  free(set_mode_fb_busy_ptr);
  free(set_mode_fb_error_ptr);
  free(set_mode_fb_error_id_ptr);
  printf("End of Program\n");
  return 0;
}
