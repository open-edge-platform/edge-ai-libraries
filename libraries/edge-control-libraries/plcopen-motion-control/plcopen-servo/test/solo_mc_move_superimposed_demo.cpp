// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <error.h>
#include <mqueue.h>
#include <signal.h>
#include <pthread.h>
#include <stdlib.h>
#include <stdbool.h>
#include <unistd.h>
#include <limits.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/shm.h>
#include <sys/ipc.h>
#include <sys/types.h>
#include <sys/time.h>
#include <time.h>
#include <getopt.h>
#include <motionentry.h>
#include <ecrt_config.hpp>
#include <ecrt_servo.hpp>
#include <fb/common/include/axis.hpp>
#include <fb/common/include/global.hpp>
#include <fb/public/include/fb_power.hpp>
#include <fb/public/include/fb_move_relative.hpp>
#include <fb/public/include/fb_read_actual_position.hpp>
#include <fb/public/include/fb_read_actual_velocity.hpp>
#include <fb/private/include/fb_read_actual_torque.hpp>
#include <fb/private/include/fb_move_superimposed.hpp>

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
#define SET_MOVE_REL_DIS 200
#define SET_MOVE_REL_VEL 20
#define SET_MOVE_REL_ACC 20
#define SET_MOVE_REL_DCC 20
#define SET_MOVE_REL_JERK 500
#define SET_MOVE_SUP_DIS 50
#define SET_MOVE_SUP_DIFF_VEL 50
#define SET_MOVE_SUP_ACC 20
#define SET_MOVE_SUP_DCC 20
#define SET_MOVE_SUP_JERK 500
using namespace RTmotion;
static AXIS_REF axis;
static FbPower fb_power;
static FbMoveRelative fb_move_rel;
static FbMoveSuperimposed fb_move_sup;
static FbReadActualPosition fb_read_pos;
static FbReadActualVelocity fb_read_vel;
static FbReadActualTorque fb_read_toq;

// log data
static char column_string[]      = "cycle_count, act_pos, act_vel, act_toq, \
                               FbMoveRelative.Execute, \
                               FbMoveRelative.Distance, \
                               FbMoveRelative.Velocity, \
                               FbMoveRelative.Acceleration, \
                               FbMoveRelative.Deceleration, \
                               FbMoveRelative.Jerk, \
                               FbMoveRelative.Done, \
                               FbMoveRelative.Busy, \
                               FbMoveRelative.Active, \
                               FbMoveRelative.Abort, \
                               FbMoveRelative.Error, \
                               FbMoveRelative.ErrorID, \
                               FbMoveSuperimposed.Execute, \
                               FbMoveSuperimposed.Distance, \
                               FbMoveSuperimposed.VelocityDiff, \
                               FbMoveSuperimposed.Acceleration, \
                               FbMoveSuperimposed.Deceleration, \
                               FbMoveSuperimposed.Jerk, \
                               FbMoveSuperimposed.Done, \
                               FbMoveSuperimposed.Busy, \
                               FbMoveSuperimposed.Abort, \
                               FbMoveSuperimposed.Error, \
                               FbMoveSuperimposed.ErrorID, \
                               FbMoveSuperimposed.CoveredDistance";
static char log_file_name[20]    = "data.csv";
static FILE* log_fptr            = nullptr;
static uint64_t* cycle_count_ptr = nullptr;
static float* act_pos_ptr        = nullptr;
static float* act_vel_ptr        = nullptr;
static float* act_toq_ptr        = nullptr;
/* FbMoveRelative */
static bool* rel_fb_exec_ptr         = nullptr;
static float* rel_fb_dis_ptr         = nullptr;
static float* rel_fb_vel_ptr         = nullptr;
static float* rel_fb_acc_ptr         = nullptr;
static float* rel_fb_dcc_ptr         = nullptr;
static float* rel_fb_jerk_ptr        = nullptr;
static bool* rel_fb_done_ptr         = nullptr;
static bool* rel_fb_busy_ptr         = nullptr;
static bool* rel_fb_active_ptr       = nullptr;
static bool* rel_fb_abort_ptr        = nullptr;
static bool* rel_fb_error_ptr        = nullptr;
static uint16_t* rel_fb_error_id_ptr = nullptr;
/* FbMoveSuperimposed */
static bool* sup_fb_exec_ptr         = nullptr;
static float* sup_fb_dis_ptr         = nullptr;
static float* sup_fb_vel_diff_ptr    = nullptr;
static float* sup_fb_acc_ptr         = nullptr;
static float* sup_fb_dcc_ptr         = nullptr;
static float* sup_fb_jerk_ptr        = nullptr;
static bool* sup_fb_done_ptr         = nullptr;
static bool* sup_fb_busy_ptr         = nullptr;
static bool* sup_fb_abort_ptr        = nullptr;
static bool* sup_fb_error_ptr        = nullptr;
static uint16_t* sup_fb_error_id_ptr = nullptr;
static float* sup_fb_cover_dis_ptr   = nullptr;
static unsigned int running_cycle_10min =
    (unsigned int)(CYCLE_COUNTER_PERSEC(cycle_us) * 600);
static unsigned int recorded_cycle = 0;

typedef enum
{
  TEST_AXIS_INIT = 0,
  TEST_AXIS_POWERED_ON,
  TEST_AXIS_MOVE_SUP,
  TEST_AXIS_IDLE
} FB_TEST;
static FB_TEST s_func_block_test = TEST_AXIS_INIT;
static mcDWORD s_func_test_count = 0;

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
    fb_move_rel.runCycle();
    fb_move_sup.runCycle();
    fb_read_pos.runCycle();
    fb_read_vel.runCycle();
    fb_read_toq.runCycle();
    powered_on = fb_power.getPowerStatus();

    switch (s_func_block_test)
    {
      case TEST_AXIS_INIT:
        if (powered_on == mcTRUE)
        {
          s_func_block_test = TEST_AXIS_POWERED_ON;
          fb_move_rel.setExecute(mcTRUE);
          printf("Axis is powered on. Continue to execute move_relative fb.\n");
        }
        break;
      case TEST_AXIS_POWERED_ON:
        if (s_func_test_count++ > 2000)
        {
          s_func_test_count = 0;
          s_func_block_test = TEST_AXIS_MOVE_SUP;
          fb_move_sup.setExecute(mcTRUE);
          printf("Next to enable move_superimposed fb.\n");
        }
        break;
      case TEST_AXIS_MOVE_SUP:
        if (fb_move_sup.isDone() == mcTRUE)
        {
          s_func_block_test = TEST_AXIS_IDLE;
          fb_move_sup.setExecute(mcFALSE);
          printf("Move_superimposed fb done.\n");
        }
        break;
      case TEST_AXIS_IDLE:
        if (fb_move_rel.isDone() == mcTRUE)
          fb_move_rel.setExecute(mcFALSE);
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
        /* FbMoveRelative */
        rel_fb_exec_ptr[recorded_cycle]     = (bool)fb_move_rel.isEnabled();
        rel_fb_dis_ptr[recorded_cycle]      = SET_MOVE_REL_DIS;
        rel_fb_vel_ptr[recorded_cycle]      = SET_MOVE_REL_VEL;
        rel_fb_acc_ptr[recorded_cycle]      = SET_MOVE_REL_ACC;
        rel_fb_dcc_ptr[recorded_cycle]      = SET_MOVE_REL_DCC;
        rel_fb_jerk_ptr[recorded_cycle]     = SET_MOVE_REL_JERK;
        rel_fb_done_ptr[recorded_cycle]     = (bool)fb_move_rel.isDone();
        rel_fb_busy_ptr[recorded_cycle]     = (bool)fb_move_rel.isBusy();
        rel_fb_active_ptr[recorded_cycle]   = (bool)fb_move_rel.isActive();
        rel_fb_abort_ptr[recorded_cycle]    = (bool)fb_move_rel.isAborted();
        rel_fb_error_ptr[recorded_cycle]    = (bool)fb_move_rel.isError();
        rel_fb_error_id_ptr[recorded_cycle] = fb_move_rel.getErrorID();
        /* FbMoveSuperimposed */
        sup_fb_exec_ptr[recorded_cycle]      = (bool)fb_move_sup.isEnabled();
        sup_fb_dis_ptr[recorded_cycle]       = SET_MOVE_SUP_DIS;
        sup_fb_vel_diff_ptr[recorded_cycle]  = SET_MOVE_SUP_DIFF_VEL;
        sup_fb_acc_ptr[recorded_cycle]       = SET_MOVE_SUP_ACC;
        sup_fb_dcc_ptr[recorded_cycle]       = SET_MOVE_SUP_DCC;
        sup_fb_jerk_ptr[recorded_cycle]      = SET_MOVE_SUP_JERK;
        sup_fb_done_ptr[recorded_cycle]      = (bool)fb_move_sup.isDone();
        sup_fb_busy_ptr[recorded_cycle]      = (bool)fb_move_sup.isBusy();
        sup_fb_abort_ptr[recorded_cycle]     = (bool)fb_move_sup.isAborted();
        sup_fb_error_ptr[recorded_cycle]     = (bool)fb_move_sup.isError();
        sup_fb_error_id_ptr[recorded_cycle]  = fb_move_sup.getErrorID();
        sup_fb_cover_dis_ptr[recorded_cycle] = fb_move_sup.getCoveredDistance();
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
    /* FbMoveRelative */
    fprintf(fptr, "%d,", rel_fb_exec_ptr[i]);
    fprintf(fptr, "%f,", rel_fb_dis_ptr[i]);
    fprintf(fptr, "%f,", rel_fb_vel_ptr[i]);
    fprintf(fptr, "%f,", rel_fb_acc_ptr[i]);
    fprintf(fptr, "%f,", rel_fb_dcc_ptr[i]);
    fprintf(fptr, "%f,", rel_fb_jerk_ptr[i]);
    fprintf(fptr, "%d,", rel_fb_done_ptr[i]);
    fprintf(fptr, "%d,", rel_fb_busy_ptr[i]);
    fprintf(fptr, "%d,", rel_fb_active_ptr[i]);
    fprintf(fptr, "%d,", rel_fb_abort_ptr[i]);
    fprintf(fptr, "%d,", rel_fb_error_ptr[i]);
    fprintf(fptr, "%d,", rel_fb_error_id_ptr[i]);
    /* FbMoveSuperimposed */
    fprintf(fptr, "%d,", sup_fb_exec_ptr[i]);
    fprintf(fptr, "%f,", sup_fb_dis_ptr[i]);
    fprintf(fptr, "%f,", sup_fb_vel_diff_ptr[i]);
    fprintf(fptr, "%f,", sup_fb_acc_ptr[i]);
    fprintf(fptr, "%f,", sup_fb_dcc_ptr[i]);
    fprintf(fptr, "%f,", sup_fb_jerk_ptr[i]);
    fprintf(fptr, "%d,", sup_fb_done_ptr[i]);
    fprintf(fptr, "%d,", sup_fb_busy_ptr[i]);
    fprintf(fptr, "%d,", sup_fb_abort_ptr[i]);
    fprintf(fptr, "%d,", sup_fb_error_ptr[i]);
    fprintf(fptr, "%d,", sup_fb_error_id_ptr[i]);
    fprintf(fptr, "%f\n", sup_fb_cover_dis_ptr[i]);
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
  /* FbMoveRelative */
  rel_fb_exec_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(rel_fb_exec_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  rel_fb_dis_ptr = (float*)malloc(sizeof(float) * uint(running_cycle_10min));
  memset(rel_fb_dis_ptr, 0, sizeof(float) * uint(running_cycle_10min));
  rel_fb_vel_ptr = (float*)malloc(sizeof(float) * uint(running_cycle_10min));
  memset(rel_fb_vel_ptr, 0, sizeof(float) * uint(running_cycle_10min));
  rel_fb_acc_ptr = (float*)malloc(sizeof(float) * uint(running_cycle_10min));
  memset(rel_fb_acc_ptr, 0, sizeof(float) * uint(running_cycle_10min));
  rel_fb_dcc_ptr = (float*)malloc(sizeof(float) * uint(running_cycle_10min));
  memset(rel_fb_dcc_ptr, 0, sizeof(float) * uint(running_cycle_10min));
  rel_fb_jerk_ptr = (float*)malloc(sizeof(float) * uint(running_cycle_10min));
  memset(rel_fb_jerk_ptr, 0, sizeof(float) * uint(running_cycle_10min));
  rel_fb_done_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(rel_fb_done_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  rel_fb_busy_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(rel_fb_busy_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  rel_fb_active_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(rel_fb_active_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  rel_fb_abort_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(rel_fb_abort_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  rel_fb_error_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(rel_fb_error_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  rel_fb_error_id_ptr =
      (uint16_t*)malloc(sizeof(uint16_t) * uint(running_cycle_10min));
  memset(rel_fb_error_id_ptr, 0, sizeof(uint16_t) * uint(running_cycle_10min));
  /* FbMoveSuperimposed */
  sup_fb_exec_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(sup_fb_exec_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  sup_fb_dis_ptr = (float*)malloc(sizeof(float) * uint(running_cycle_10min));
  memset(sup_fb_dis_ptr, 0, sizeof(float) * uint(running_cycle_10min));
  sup_fb_vel_diff_ptr =
      (float*)malloc(sizeof(float) * uint(running_cycle_10min));
  memset(sup_fb_vel_diff_ptr, 0, sizeof(float) * uint(running_cycle_10min));
  sup_fb_acc_ptr = (float*)malloc(sizeof(float) * uint(running_cycle_10min));
  memset(sup_fb_acc_ptr, 0, sizeof(float) * uint(running_cycle_10min));
  sup_fb_dcc_ptr = (float*)malloc(sizeof(float) * uint(running_cycle_10min));
  memset(sup_fb_dcc_ptr, 0, sizeof(float) * uint(running_cycle_10min));
  sup_fb_jerk_ptr = (float*)malloc(sizeof(float) * uint(running_cycle_10min));
  memset(sup_fb_jerk_ptr, 0, sizeof(float) * uint(running_cycle_10min));
  sup_fb_done_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(sup_fb_done_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  sup_fb_busy_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(sup_fb_busy_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  sup_fb_abort_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(sup_fb_abort_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  sup_fb_error_ptr = (bool*)malloc(sizeof(bool) * uint(running_cycle_10min));
  memset(sup_fb_error_ptr, 0, sizeof(bool) * uint(running_cycle_10min));
  sup_fb_error_id_ptr =
      (uint16_t*)malloc(sizeof(uint16_t) * uint(running_cycle_10min));
  memset(sup_fb_error_id_ptr, 0, sizeof(uint16_t) * uint(running_cycle_10min));
  sup_fb_cover_dis_ptr =
      (float*)malloc(sizeof(float) * uint(running_cycle_10min));
  memset(sup_fb_cover_dis_ptr, 0, sizeof(float) * uint(running_cycle_10min));
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

  fb_move_rel.setAxis(axis);
  fb_move_rel.setPosition(SET_MOVE_REL_DIS);
  fb_move_rel.setVelocity(SET_MOVE_REL_VEL);
  fb_move_rel.setAcceleration(SET_MOVE_REL_ACC);
  fb_move_rel.setDeceleration(SET_MOVE_REL_DCC);
  fb_move_rel.setJerk(SET_MOVE_REL_JERK);
  fb_move_rel.setBufferMode(mcAborting);
  fb_move_rel.setExecute(mcFALSE);

  fb_move_sup.setAxis(axis);
  fb_move_sup.setContinuousUpdate(mcFALSE);
  fb_move_sup.setDistance(SET_MOVE_SUP_DIS);
  fb_move_sup.setVelocityDiff(SET_MOVE_SUP_DIFF_VEL);
  fb_move_sup.setAcceleration(SET_MOVE_SUP_ACC);
  fb_move_sup.setDeceleration(SET_MOVE_SUP_DCC);
  fb_move_sup.setJerk(SET_MOVE_SUP_JERK);
  fb_move_sup.setExecute(mcFALSE);

  fb_read_pos.setAxis(axis);
  fb_read_pos.setEnable(mcTRUE);

  fb_read_vel.setAxis(axis);
  fb_read_vel.setEnable(mcTRUE);

  fb_read_toq.setAxis(axis);
  fb_read_toq.setEnable(mcTRUE);

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
  /* FbMoveRelative */
  free(rel_fb_exec_ptr);
  free(rel_fb_dis_ptr);
  free(rel_fb_vel_ptr);
  free(rel_fb_acc_ptr);
  free(rel_fb_dcc_ptr);
  free(rel_fb_jerk_ptr);
  free(rel_fb_done_ptr);
  free(rel_fb_busy_ptr);
  free(rel_fb_active_ptr);
  free(rel_fb_abort_ptr);
  free(rel_fb_error_ptr);
  free(rel_fb_error_id_ptr);
  /* FbMoveSuperimposed */
  free(sup_fb_exec_ptr);
  free(sup_fb_dis_ptr);
  free(sup_fb_vel_diff_ptr);
  free(sup_fb_acc_ptr);
  free(sup_fb_dcc_ptr);
  free(sup_fb_jerk_ptr);
  free(sup_fb_done_ptr);
  free(sup_fb_busy_ptr);
  free(sup_fb_abort_ptr);
  free(sup_fb_error_ptr);
  free(sup_fb_error_id_ptr);
  free(sup_fb_cover_dis_ptr);
  printf("End of Program\n");
  return 0;
}
