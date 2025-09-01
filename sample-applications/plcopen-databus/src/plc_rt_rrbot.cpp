// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file plc_rt_rrbot.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <cstdio>
#include <thread>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <pthread.h>
#include <sys/mman.h>
#include <getopt.h>

#include <shmringbuf.h>

#include <fb/public/include/fb_power.hpp>
#include <fb/public/include/fb_move_absolute.hpp>
#include <fb/public/include/fb_read_actual_position.hpp>
#include <fb/public/include/fb_read_actual_velocity.hpp>
#include <fb/public/include/fb_read_command_acceleration.hpp>
#ifdef PLOT
#include <RTmotion/tool/fb_debug_tool.hpp>
#endif

#define CYCLE_US 1000
#define NSEC_PER_SEC (1000000000L)
#ifndef DIFF_NS
#define DIFF_NS(A,B)    		(((B).tv_sec - (A).tv_sec)*NSEC_PER_SEC + ((B).tv_nsec)-(A).tv_nsec)
#endif

static volatile int run = 1;
static pthread_t cyclic_thread;
static unsigned int count = 0;

/* Shm related data types
 * s_buf, handle_s: data sent from RT domain
 * r_buf, handle_r: data sent to RT domain
 */
#define MSG_LEN 500
#define JOINT_NUM 2
static char s_buf[MSG_LEN];
static char r_buf[MSG_LEN];
static shm_handle_t handle_s, handle_r;

static RTmotion::AXIS_REF axis[JOINT_NUM];
static RTmotion::Servo* servos[JOINT_NUM];
static RTmotion::AxisConfig configs[JOINT_NUM];
static RTmotion::FbPower fbPower[JOINT_NUM];
static RTmotion::FbMoveAbsolute moveAbs[JOINT_NUM];
static RTmotion::FbReadActualPosition readPos[JOINT_NUM];
static RTmotion::FbReadActualVelocity readVel[JOINT_NUM];
static RTmotion::FbReadCommandAcceleration readAcc[JOINT_NUM];
#ifdef PLOT
static FBDigitalProfile profile;
#endif

using namespace RTmotion;

struct JointCommand
{
  double positions[JOINT_NUM] = {0};
  double velocities[JOINT_NUM] = {0};
  double accelerations[JOINT_NUM] = {0};
  double efforts[JOINT_NUM] = {0};
};

struct JointState
{
  double positions[JOINT_NUM] = {0};
  double velocities[JOINT_NUM] = {0};
  double accelerations[JOINT_NUM] = {0};
  double efforts[JOINT_NUM] = {0};
};

static JointCommand joint_cmd;
static JointState joint_state;

void* my_thread(void* /*arg*/)
{
#ifdef PLOT
  profile.reset();
  profile.addFB("cmd");
  profile.addFB("state");
  profile.addItemName("cmd.pos");
  profile.addItemName("cmd.vel");
  profile.addItemName("cmd.acc");
  profile.addItemName("state.pos");
  profile.addItemName("state.vel");
  profile.addItemName("state.acc");
#endif
  struct timespec loop_next_period;
#ifdef MEASURE_TIMING
  struct timespec loop_wakeup_time, motion_start_time, motion_end_time;
  int64_t latency_ns = 0;
  int64_t latency_min_ns = 1000000, latency_max_ns = -1000000, latency_avg_ns = 0;
  int64_t motion_min_ns = 1000000, motion_max_ns = -1000000, motion_avg_ns = 0;
#endif
  int ret;
  bool waypoint_start = false;

  struct sched_param param = {};
  param.sched_priority = 99;
  pthread_setschedparam(pthread_self(), SCHED_FIFO, &param);
  clock_gettime(CLOCK_MONOTONIC, &loop_next_period);

  while (run != 0)
  {
    loop_next_period.tv_nsec += CYCLE_US * 1000;
    while (loop_next_period.tv_nsec >= NSEC_PER_SEC)
    {
      loop_next_period.tv_nsec -= NSEC_PER_SEC;
      loop_next_period.tv_sec++;
    }
    clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &loop_next_period, NULL);
#ifdef MEASURE_TIMING
    clock_gettime(CLOCK_MONOTONIC, &loop_wakeup_time);
    latency_ns = DIFF_NS(loop_next_period, loop_wakeup_time);
    latency_avg_ns += fabs(latency_ns);
    if (latency_ns > latency_max_ns)
        latency_max_ns = latency_ns;
    if (latency_ns < latency_min_ns)
        latency_min_ns = latency_ns;
#endif
    count++;
    /* Get the joint commands */
    if (!shm_blkbuf_empty(handle_r))
    {
      ret = shm_blkbuf_read(handle_r, r_buf, sizeof(r_buf));
      if (ret) 
      {
        memcpy(&joint_cmd, r_buf, sizeof(joint_cmd));
        // printf("Received the joint command.\n");
        // for (size_t i = 0; i < JOINT_NUM; i++)
        // {
        //   printf("Joint %ld, pos_cmd: %f, vel_cmd: %f, acc_cmd: %f, time: %ld.%ld\n", 
        //          i, joint_cmd.positions[i],
        //             joint_cmd.velocities[i], 
        //             joint_cmd.accelerations[i], loop_wakeup_time.tv_sec, loop_wakeup_time.tv_nsec);
        // }
        waypoint_start = true;
      }
    }

#ifdef MEASURE_TIMING
    clock_gettime(CLOCK_MONOTONIC, &motion_start_time);
#endif
    for (size_t i = 0; i < JOINT_NUM; i ++)
    {
      if (moveAbs[i].isEnabled() == mcFALSE)
        moveAbs[i].setExecute(mcTRUE);
      axis[i]->runCycle();
      moveAbs[i].runCycle();
      fbPower[i].runCycle();
      readPos[i].runCycle();
      readVel[i].runCycle();
      readAcc[i].runCycle();
    }

    /* Execute the joint command */
    if (waypoint_start)
    {
      // Un-trigger the function block execution
      for (size_t i = 0; i < JOINT_NUM; i++)
      {
        if (fabs(moveAbs[i].getPosition() * 3.1415926 / 180.0 - joint_cmd.positions[i]) > 0.0001)
        {
          moveAbs[i].setPosition(joint_cmd.positions[i] * 180.0 / 3.1415926);
          moveAbs[i].setExecute(mcFALSE);
          moveAbs[i].runCycle();
        }
      }

      waypoint_start = false;
    }
#ifdef MEASURE_TIMING
    clock_gettime(CLOCK_MONOTONIC, &motion_end_time);
    latency_ns = DIFF_NS(motion_start_time, motion_end_time);
    motion_avg_ns += fabs(latency_ns);
    if (latency_ns > motion_max_ns)
        motion_max_ns = latency_ns;
    if (latency_ns < motion_min_ns)
        motion_min_ns = latency_ns;
#endif

    for (size_t i = 0; i < JOINT_NUM; i++)
    {
      joint_state.positions[i] = readPos[i].getFloatValue() * 3.1415926 / 180.0;
      joint_state.velocities[i] = readVel[i].getFloatValue() * 3.1415926 / 180.0;
      // printf("Joint %ld, pos: %f, vel: %f, acc: %f\n", 
      //         i, joint_state.positions[i], joint_state.velocities[i], joint_state.accelerations[i]);
    }

#ifdef PLOT
    profile.addState("cmd.pos", joint_cmd.positions[1] * 180.0 / 3.1415926);
    profile.addState("cmd.vel", joint_cmd.velocities[1] * 180.0 / 3.1415926);
    profile.addState("cmd.acc", joint_cmd.accelerations[1] * 180.0 / 3.1415926);
    profile.addState("state.pos", readPos[1].getFloatValue());
    fabs(readVel[1].getFloatValue()) < 500 ? profile.addState("state.vel", readVel[1].getFloatValue()): profile.addState("state.vel", joint_cmd.velocities[1] * 180.0 / 3.1415926);
    profile.addState("state.acc", readAcc[1].getFloatValue());
    profile.addTime(count);
#endif
    /* Send the joint state */
    memcpy(s_buf, &joint_state, sizeof(joint_state));
    if (!shm_blkbuf_full(handle_s))
    {
      ret = shm_blkbuf_write(handle_s, s_buf, sizeof(s_buf));
      // printf("%s: sent %d bytes\n", __FUNCTION__, ret);
    }
  }
#ifdef MEASURE_TIMING
  printf("******************************************************\n");
  printf("jitter time     %10.3f...%10.3f...%10.3f\n", (float)latency_min_ns/1000, 
                                                       (float)latency_avg_ns/count/1000,
                                                       (float)latency_max_ns/1000);
  printf("motion time     %10.3f...%10.3f...%10.3f\n", (float)motion_min_ns/1000, 
                                                       (float)motion_avg_ns/count/1000,
                                                       (float)motion_max_ns/1000);
  printf("******************************************************\n");
#endif
  return NULL;
}

static void getOptions(int argc, char** argv)
{
  int index;
  static struct option longOptions[] = {
    // name     has_arg          flag  val
    { "time", required_argument, NULL, 't' },
    { "help", no_argument, NULL, 'h' },
    {}
  };
  do
  {
    index = getopt_long(argc, argv, "t:h", longOptions, NULL);
    switch (index)
    {
      case 'h':
        printf("Global options:\n");
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

  auto signal_handler = [](int){ run = 0; };
  signal(SIGTERM, signal_handler);
  signal(SIGINT, signal_handler);
  mlockall(MCL_CURRENT | MCL_FUTURE);

  for (size_t i = 0; i < JOINT_NUM; i ++)
  {
    axis[i] = new RTmotion::Axis();
    axis[i]->setAxisId(i);
    axis[i]->setAxisConfig(&configs[i]);

    servos[i] = new RTmotion::Servo();
    axis[i]->setServo(servos[i]);
    printf("Axis %lu initialized.\n", i);
  }

  // Initialize function blocks
  for (size_t i = 0; i < JOINT_NUM; i++)
  {
    fbPower[i].setAxis(axis[i]);
    fbPower[i].setEnable(mcTRUE);
    fbPower[i].setEnablePositive(mcTRUE);
    fbPower[i].setEnableNegative(mcTRUE);
  }

  for (size_t i = 0; i < JOINT_NUM; i ++)
  {
    moveAbs[i].setAxis(axis[i]);
    moveAbs[i].setPosition(0.0);
    moveAbs[i].setVelocity(50);
    moveAbs[i].setAcceleration(100);
    moveAbs[i].setDeceleration(100);
    moveAbs[i].setJerk(1000);
    moveAbs[i].setBufferMode(RTmotion::mcAborting);
  }
  
  for (size_t i = 0; i < JOINT_NUM; i ++)
  {
    readPos[i].setAxis(axis[i]);
    readPos[i].setEnable(mcTRUE);
  }  

  for (size_t i = 0; i < JOINT_NUM; i ++)
  {
    readVel[i].setAxis(axis[i]);
    readVel[i].setEnable(mcTRUE);
  }

  for (size_t i = 0; i < JOINT_NUM; i ++)
  {
    readAcc[i].setAxis(axis[i]);
    readAcc[i].setEnable(mcTRUE);
  }
  printf("Function blocks initialized.\n");

  /* Create cyclic RT-thread */
  pthread_attr_t thattr;
  pthread_attr_init(&thattr);
  pthread_attr_setdetachstate(&thattr, PTHREAD_CREATE_JOINABLE);

  handle_s = shm_blkbuf_init((char*)"rtsend", 2, MSG_LEN);
  handle_r = shm_blkbuf_init((char*)"rtread", 2, MSG_LEN);

  if (pthread_create(&cyclic_thread, &thattr, &my_thread, NULL))
  {
    fprintf(stderr, "pthread_create cyclic task failed\n");
    return 1;
  }

  while (run)
    sched_yield();

  pthread_join(cyclic_thread, NULL);
#ifdef PLOT
  profile.plot("plc_rt_rrbot.png");
#endif
  for (size_t i = 0; i < JOINT_NUM; i ++)
  {
    delete servos[i];
    delete axis[i];
  }
  shm_blkbuf_close(handle_s);
  shm_blkbuf_close(handle_r);
  printf("\nEnd of Program\n");
  return 0;
}

/****************************************************************************/
