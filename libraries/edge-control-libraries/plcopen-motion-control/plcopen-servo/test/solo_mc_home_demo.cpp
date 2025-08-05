// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

#include <fb/common/include/axis.hpp>
#include <fb/private/include/fb_home.hpp>
#include <fb/public/include/fb_move_absolute.hpp>
#include <fb/public/include/fb_power.hpp>
#include <fb/public/include/fb_read_actual_position.hpp>
#include <fb/private/include/fb_read_actual_torque.hpp>
#include <fb/public/include/fb_read_actual_velocity.hpp>
#include <fb/private/include/fb_set_controller_mode.hpp>
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
#define SET_HOME_METHOD 1
#define SET_HOME_VEL_SWITCH PER_CIRCLE_ENCODER
#define SET_HOME_VEL_ZERO PER_CIRCLE_ENCODER
using namespace RTmotion;
static AXIS_REF axis;
static FbPower fb_power;
static FbMoveAbsolute fb_move;
static FbHome fb_home;
static FbReadActualPosition fb_read_pos;
static FbReadActualVelocity fb_read_vel;
static FbReadActualTorque fb_read_toq;
static FbSetControllerMode fb_set_controller_mode;

// log data
static char column_string[]      = "cycle_count, act_pos, act_vel, act_toq, \
                               home_method, \
                               home_vel_switch, \
                               home_vel_zero, \
                               FbHome.Execute, \
                               FbHome.Done, \
                               FbHome.Busy, \
                               FbHome.Abort, \
                               FbHome.Error, \
                               FbHome.ErrorID";
static char log_file_name[20]    = "data.csv";
static FILE* log_fptr            = nullptr;
static uint64_t* cycle_count_ptr = nullptr;
static float* act_pos_ptr        = nullptr;
static float* act_vel_ptr        = nullptr;
static float* act_toq_ptr        = nullptr;
/* FbHome */
static int8_t* home_method_ptr        = nullptr;
static uint32_t* home_vel_switch_ptr  = nullptr;
static uint32_t* home_vel_zero_ptr    = nullptr;
static bool* home_fb_exec_ptr         = nullptr;
static bool* home_fb_done_ptr         = nullptr;
static bool* home_fb_busy_ptr         = nullptr;
static bool* home_fb_abort_ptr        = nullptr;
static bool* home_fb_error_ptr        = nullptr;
static uint16_t* home_fb_error_id_ptr = nullptr;
static unsigned int running_cycle_10min =
    (unsigned int)(CYCLE_COUNTER_PERSEC(cycle_us) * 600);
static unsigned int recorded_cycle = 0;

typedef enum
{
  MC_DEMO_SET_HOME_MODE = 0,
  MC_DEMO_GO_HOME,
  MC_DEMO_SET_POS_MODE,
  MC_DEMO_MOVE_ABSOLUTE
} MC_DEMO_HOME_TEST;
static MC_DEMO_HOME_TEST s_home_demo_func = MC_DEMO_SET_HOME_MODE;
static AxisParamInfo* param_table         = nullptr;

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
    fb_home.runCycle();
    fb_read_pos.runCycle();
    fb_read_vel.runCycle();
    fb_read_toq.runCycle();
    fb_set_controller_mode.runCycle();
    powered_on = fb_power.getPowerStatus();

    switch (s_home_demo_func)
    {
      case MC_DEMO_SET_HOME_MODE: {
        if ((powered_on == mcTRUE) &&
            (fb_set_controller_mode.isDone() == mcTRUE))
        {
          s_home_demo_func = MC_DEMO_GO_HOME;
          printf("fb_setControllerMode done. execute fb_home.\n");
        }
        else
        {
          if ((powered_on == mcTRUE) &&
              (fb_set_controller_mode.isEnabled() == mcFALSE))
          {
            fb_set_controller_mode.setMode(mcServoControlModeHomeServo);
            fb_set_controller_mode.setEnable(mcTRUE);
            printf("set controller mode to HM. \r\n");
          }
        }
      }
      break;
      case MC_DEMO_GO_HOME: {
        if (fb_home.isDone() == mcTRUE)
        {
          fb_home.setExecute(mcFALSE);
          s_home_demo_func = MC_DEMO_SET_POS_MODE;
          fb_set_controller_mode.setMode(mcServoControlModePosition);
          printf(
              "fb_home test done, execute fb_setControllerMode to pos mode.\n");
        }
        else
          fb_home.setExecute(mcTRUE);
      }
      break;
      case MC_DEMO_SET_POS_MODE: {
        if (fb_set_controller_mode.isDone() == mcTRUE)
        {
          s_home_demo_func = MC_DEMO_MOVE_ABSOLUTE;
          printf("fb_setControllerMode done. execute fb_moveAbsolute.\n");
        }
      }
      break;
      case MC_DEMO_MOVE_ABSOLUTE: {
        if (fb_move.isDone() == mcTRUE)
        {
          fb_move.setExecute(mcFALSE);
          s_home_demo_func = MC_DEMO_SET_HOME_MODE;
          fb_set_controller_mode.setMode(mcServoControlModeHomeServo);
          printf("fb_moveAbsolute test done, execute fb_setControllerMode to "
                 "home mode.\n");
        }
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
        /* FbHome */
        home_method_ptr[recorded_cycle]      = SET_HOME_METHOD;
        home_vel_switch_ptr[recorded_cycle]  = SET_HOME_VEL_SWITCH;
        home_vel_zero_ptr[recorded_cycle]    = SET_HOME_VEL_ZERO;
        home_fb_exec_ptr[recorded_cycle]     = (bool)fb_home.isEnabled();
        home_fb_done_ptr[recorded_cycle]     = (bool)fb_home.isDone();
        home_fb_busy_ptr[recorded_cycle]     = (bool)fb_home.isBusy();
        home_fb_abort_ptr[recorded_cycle]    = (bool)fb_home.isAborted();
        home_fb_error_ptr[recorded_cycle]    = (bool)fb_home.isError();
        home_fb_error_id_ptr[recorded_cycle] = fb_home.getErrorID();

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
    fprintf(fptr, "%d,", home_method_ptr[i]);
    fprintf(fptr, "%d,", home_vel_switch_ptr[i]);
    fprintf(fptr, "%d,", home_vel_zero_ptr[i]);
    fprintf(fptr, "%d,", home_fb_exec_ptr[i]);
    fprintf(fptr, "%d,", home_fb_done_ptr[i]);
    fprintf(fptr, "%d,", home_fb_busy_ptr[i]);
    fprintf(fptr, "%d,", home_fb_abort_ptr[i]);
    fprintf(fptr, "%d,", home_fb_error_ptr[i]);
    fprintf(fptr, "%d\n", home_fb_error_id_ptr[i]);
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
  /* FbHome */
  home_method_ptr = (int8_t*)malloc(sizeof(int8_t) * uint(running_cycle_10min));
  memset(home_method_ptr, 0, sizeof(int8_t) * uint(running_cycle_10min));
  home_vel_switch_ptr =
      (uint32_t*)malloc(sizeof(uint32_t) * uint(running_cycle_10min));
  memset(home_vel_switch_ptr, 0, sizeof(uint32_t) * uint(running_cycle_10min));
  home_vel_zero_ptr =
      (uint32_t*)malloc(sizeof(uint32_t) * uint(running_cycle_10min));
  memset(home_vel_zero_ptr, 0, sizeof(uint32_t) * uint(running_cycle_10min));
  home_fb_exec_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(home_fb_exec_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  home_fb_done_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(home_fb_done_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  home_fb_busy_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(home_fb_busy_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  home_fb_abort_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(home_fb_abort_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  home_fb_error_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(home_fb_error_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  home_fb_error_id_ptr =
      (uint16_t*)malloc(sizeof(uint16_t) * uint(running_cycle_10min));
  memset(home_fb_error_id_ptr, 0, sizeof(uint16_t) * uint(running_cycle_10min));
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

  fb_home.setAxis(axis);
  fb_home.setAcceleration(20);
  fb_home.setDeceleration(20);
  fb_home.setJerk(500);
  fb_home.setBufferMode(mcAborting);
  fb_home.setExecute(mcFALSE);

  fb_read_pos.setAxis(axis);
  fb_read_pos.setEnable(mcTRUE);

  fb_read_vel.setAxis(axis);
  fb_read_vel.setEnable(mcTRUE);

  fb_read_toq.setAxis(axis);
  fb_read_toq.setEnable(mcTRUE);

  fb_set_controller_mode.setAxis(axis);
  fb_set_controller_mode.setEnable(mcFALSE);

  param_table = new AxisParamInfo[3]{
    { 0x6098, 0x00, 1 },  // homing method
    { 0x6099, 0x01, 4 },  // speed during search for switch
    { 0x6099, 0x02, 4 }   // speed during search for zero
  };
  axis->setAxisParamInit(3, param_table);
  axis->writeAxisParam(0, SET_HOME_METHOD);
  axis->writeAxisParam(1, SET_HOME_VEL_SWITCH);
  axis->writeAxisParam(2, SET_HOME_VEL_ZERO);

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
  delete[] param_table;
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
  free(home_method_ptr);
  free(home_vel_switch_ptr);
  free(home_vel_zero_ptr);
  free(home_fb_exec_ptr);
  free(home_fb_done_ptr);
  free(home_fb_busy_ptr);
  free(home_fb_abort_ptr);
  free(home_fb_error_ptr);
  free(home_fb_error_id_ptr);
  printf("End of Program\n");
  return 0;
}
