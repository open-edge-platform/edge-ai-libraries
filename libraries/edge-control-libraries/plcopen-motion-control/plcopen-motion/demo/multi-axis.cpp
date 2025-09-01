// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file multi-axis.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <signal.h>
#include <pthread.h>
#include <sys/mman.h>
#include <getopt.h>

#include <fb/common/include/axis.hpp>
#include <fb/common/include/global.hpp>
#include <fb/public/include/fb_power.hpp>
#include <fb/public/include/fb_move_relative.hpp>
#include <fb/public/include/fb_move_velocity.hpp>
#include <fb/public/include/fb_read_actual_position.hpp>
#include <fb/public/include/fb_read_actual_velocity.hpp>

static unsigned int cycle_us =
    1000;  // Define real-time cycle time as 1 ms (micro-seconds)
#define NSEC_PER_MICROSEC                                                      \
  1000              // Record execution time for 1000 times for 1 s (seconds)
#define AXIS_NUM 1  // Set axis number as 1

static volatile int run = 1;
static pthread_t cyclic_thread;

using namespace RTmotion;

void* my_thread(void* /*arg*/)
{
  AXIS_REF axis[AXIS_NUM];  // "AXIS_REF" is the pointer to axis objects
  for (auto& ax : axis)
  {
    ax = new Axis();  // "AXIS_REF" should be initialized by "new" operator
    ax->setAxisId(1);
  }

  /* AxisConfig contains multiple configurations for the axis (= defaul value):
      - MC_SERVO_CONTROL_MODE mode_      = mcServoControlModePosition;
      - uint64_t encoder_count_per_unit_ = 1000000;
      - uint64_t node_buffer_size_       = 2;
      - bool sw_vel_limit_               = false;
      - double vel_limit_                = 5000.0;
      - bool sw_acc_limit_               = false;
      - double acc_limit_                = 5000.0;
      - bool sw_range_limit_             = false;
      - double pos_positive_limit_       = 5000.0;
      - double pos_negative_limit_       = 5000.0;
      - double frequency_                = 1000.0;
  */
  AxisConfig config[AXIS_NUM];
  for (size_t i = 0; i < AXIS_NUM; i++)
  {
    config[i].frequency_ = 1.0 / cycle_us * 1000000;
    axis[i]->setAxisConfig(&config[i]);
  }

  Servo* servo[AXIS_NUM];
  for (size_t i = 0; i < AXIS_NUM; i++)
  {
    servo[i] = new Servo();  // Create virtual servo motors
    axis[i]->setServo(servo[i]);
  }
  printf("Axis initialized.\n");

  FbPower fb_power[AXIS_NUM];  // Initialize MC_Power
  for (size_t i = 0; i < AXIS_NUM; i++)
  {
    fb_power[i].setAxis(axis[i]);
    fb_power[i].setEnable(mcTRUE);
    fb_power[i].setEnablePositive(mcTRUE);
    fb_power[i].setEnableNegative(mcTRUE);
  }

  FbMoveRelative fb_move_rel[AXIS_NUM];  // Initialize MC_MoveRelative
  for (size_t i = 0; i < AXIS_NUM; i++)
  {
    fb_move_rel[i].setAxis(axis[i]);
    fb_move_rel[i].setContinuousUpdate(mcFALSE);
    fb_move_rel[i].setDistance(200);
    fb_move_rel[i].setVelocity(500);
    fb_move_rel[i].setAcceleration(500);
    fb_move_rel[i].setJerk(5000);
    fb_move_rel[i].setBufferMode(mcAborting);
  }

  FbReadActualPosition read_pos[AXIS_NUM];  // Initialize MC_ReadActualPosition
  for (size_t i = 0; i < AXIS_NUM; i++)
  {
    read_pos[i].setAxis(axis[i]);
    read_pos[i].setEnable(mcTRUE);
  }

  FbReadActualVelocity read_vel[AXIS_NUM];  // Initialize MC_ReadActualVelocity
  for (size_t i = 0; i < AXIS_NUM; i++)
  {
    read_vel[i].setAxis(axis[i]);
    read_vel[i].setEnable(mcTRUE);
  }
  printf("Function block initialized.\n");

  struct timespec next_period;
  struct sched_param param = {};
  param.sched_priority     = 99;  // Set real-time thread priority
  /* Set real-time thread schedule policy as preemptable "SCHED_FIFO" */
  pthread_setschedparam(pthread_self(), SCHED_FIFO, &param);
  clock_gettime(CLOCK_MONOTONIC, &next_period);

  while (run != 0)
  {
    next_period.tv_nsec += cycle_us * 1000;
    while (next_period.tv_nsec >= NSEC_PER_SEC)
    {
      next_period.tv_nsec -= NSEC_PER_SEC;
      next_period.tv_sec++;
    }
    /* Sleep to the next cycle start time "next_period"
    Using clock "CLOCK_MONOTONIC" for accurate clock time */
    clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &next_period, nullptr);

    /* All the "runCycle()" functions of axes and function blocks
      should be run in every real-time cycle */
    for (size_t i = 0; i < AXIS_NUM; i++)
    {
      axis[i]->runCycle();
      fb_power[i].runCycle();
      fb_move_rel[i].runCycle();
      read_pos[i].runCycle();
      read_vel[i].runCycle();
    }

    /* Trigger axis movement when all axis are powered on */
    mcBOOL power_on = mcTRUE;
    for (auto& fb : fb_power)
      power_on = (power_on == mcTRUE) && (fb.getPowerStatus() == mcTRUE) ?
                     mcTRUE :
                     mcFALSE;

    /* Only enable MC_MoveRelative when the axis is powered on */
    if (power_on == mcTRUE)
    {
      for (auto& fb : fb_move_rel)
        fb.setExecute(mcTRUE);
    }

    /* When the MC_MoveRelative is done, reverse direction
      and move back with the same relative distance */
    for (auto& fb : fb_move_rel)
    {
      if (fb.isDone() == mcTRUE)
      {
        fb.setExecute(mcFALSE);
        fb.setPosition(-fb.getPosition());
      }
    }

    /* All read function blocks using "getFloatValue()" function to get the
      desired value. This print is only for a demo, please do not make prints in
      a real-time thread for real-life usage. Otherwise,
      it will hurt real-time performance. */
    printf("Joint %d, pos: %f, vel: %f\n", 0, read_pos[0].getFloatValue(),
           read_vel[0].getFloatValue());
  }

  /* Release the memory for the axis and servo objects after the real-time task
   * finishes */
  for (size_t i = 0; i < AXIS_NUM; i++)
  {
    if (!servo[i])
    {
      delete servo[i];
      servo[i] = nullptr;
    }
    if (!axis[i])
    {
      delete axis[i];
      axis[i] = nullptr;
    }
  }
  return nullptr;
}

/* Parse command arguments */
static void getOptions(int argc, char** argv)
{
  int index;
  static struct option long_options[] = {
    // name		has_arg				flag	val
    { "interval", required_argument, nullptr, 'i' },
    { "help", no_argument, nullptr, 'h' },
    {}
  };
  do
  {
    index = getopt_long(argc, argv, "i:h", long_options, nullptr);
    switch (index)
    {
      case 'i':
        cycle_us = (unsigned int)atof(optarg);
        printf("Time: Set running interval to %d us\n", cycle_us);
        break;
      case 'h':
        printf("Global options:\n");
        printf("    --interval  -i  Set cycle time (us).\n");
        printf("    --help  -h  Show this help.\n");
        exit(0);
        break;
    }
  } while (index != -1);
}

/****************************************************************************
 * Main function
 ***************************************************************************/
int main(int argc, char* argv[])
{
  getOptions(argc, argv);
  auto signal_handler = [](int /*unused*/) { run = 0; };
  signal(SIGTERM, signal_handler);
  signal(SIGINT, signal_handler);
  mlockall(MCL_CURRENT | MCL_FUTURE);

  /* Create cyclic RT-thread */
  pthread_attr_t thattr;
  pthread_attr_init(&thattr);
  pthread_attr_setdetachstate(&thattr, PTHREAD_CREATE_JOINABLE);

  if (pthread_create(&cyclic_thread, &thattr, &my_thread, nullptr))
  {
    fprintf(stderr, "pthread_create cyclic task failed\n");
    return 1;
  }

  pthread_join(cyclic_thread, nullptr);
  printf("End of Program\n");
  return 0;
}

/****************************************************************************/
