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
#include <fb/public/include/fb_move_relative.hpp>
#include <fb/public/include/fb_read_actual_position.hpp>
#include <fb/public/include/fb_read_actual_velocity.hpp>

#include <motionentry.h>
#include <ecrt_servo.hpp>

#ifndef CYCLE_US
#define CYCLE_US 1000
#endif
#define NSEC_PER_SEC (1000000000L)
#ifndef DIFF_NS
#define DIFF_NS(A,B)    		(((B).tv_sec - (A).tv_sec)*NSEC_PER_SEC + ((B).tv_nsec)-(A).tv_nsec)
#endif

static volatile int run = 1;
static pthread_t cyclic_thread;
static unsigned int count = 0;

// Ethercat related
static servo_master* master = NULL;
static uint8_t* domain1;
void* domain;

// Command line arguments
static char *eni_file = NULL;

/* Shm related data types
 * s_buf, handle_s: data sent from RT domain
 * r_buf, handle_r: data sent to RT domain
 */
#define MSG_LEN 500
#define JOINT_NUM 2
static char s_buf[MSG_LEN];
static char r_buf[MSG_LEN];
static shm_handle_t handle_s, handle_r;

static EcrtServo* my_servo[JOINT_NUM];
static RTmotion::AXIS_REF axis[JOINT_NUM];
static RTmotion::Servo* servos[JOINT_NUM];
static RTmotion::AxisConfig configs[JOINT_NUM];
static RTmotion::FbPower fbPower[JOINT_NUM];
static RTmotion::FbMoveAbsolute moveAbs[JOINT_NUM];
static RTmotion::FbReadActualPosition readPos[JOINT_NUM];
static RTmotion::FbReadActualVelocity readVel[JOINT_NUM];

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
  struct timespec loop_next_period, dc_period;
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
    motion_servo_recv_process(master->master, static_cast<uint8_t *>(domain));

    /* Get the joint commands */
    if (!shm_blkbuf_empty(handle_r))
    {
      ret = shm_blkbuf_read(handle_r, r_buf, sizeof(r_buf));
      if (ret) 
      {
        memcpy(&joint_cmd, r_buf, sizeof(joint_cmd));
        // printf("Received the joint command.\n");
        for (size_t i = 0; i < JOINT_NUM; i++)
        {
          // printf("Joint %ld, pos_cmd: %f, vel_cmd: %f, acc_cmd: %f\n", 
          //        i, joint_cmd.positions[i],
          //           joint_cmd.velocities[i], 
          //           joint_cmd.accelerations[i]);
        }
        waypoint_start = true;
      }
    }

#ifdef MEASURE_TIMING
    clock_gettime(CLOCK_MONOTONIC, &motion_start_time);
#endif

    for (size_t i = 0; i < JOINT_NUM; i ++)
    {
      axis[i]->runCycle();
      fbPower[i].runCycle();
      readPos[i].runCycle();
      readVel[i].runCycle();
    }

    /* Execute the joint command */
    if (waypoint_start)
    {
      // Un-trigger the function block execution
      for (size_t i = 0; i < JOINT_NUM; i++)
      {
        if (fabs(moveAbs[i].getPosition() * 3.1415926 / 180.0 - joint_cmd.positions[i]) > 0.0001)
        {
          moveAbs[i].setExecute(mcFALSE);
          moveAbs[i].runCycle();

          moveAbs[i].setPosition(joint_cmd.positions[i] * 180.0 / 3.1415926);
          moveAbs[i].setExecute(mcTRUE);
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
      // printf("Joint %ld, joint_state.positions: %f\n", 
      //         i, joint_state.positions[i]);
    }

    /* Send the joint state */
    memcpy(s_buf, &joint_state, sizeof(joint_state));
    if (!shm_blkbuf_full(handle_s))
    {
      ret = shm_blkbuf_write(handle_s, s_buf, sizeof(s_buf));
      // printf("%s: sent %d bytes\n", __FUNCTION__, ret);
    }

    clock_gettime(CLOCK_MONOTONIC, &dc_period);
    motion_servo_sync_dc(master->master, TIMESPEC2NS(dc_period));
    motion_servo_send_process(master->master, static_cast<uint8_t *>(domain));
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
    { "eni", required_argument, NULL, 'n' },
    { "help", no_argument, NULL, 'h' },
    {}
  };
  do
  {
    index = getopt_long(argc, argv, "n:h", longOptions, NULL);
    switch (index)
    {
      case 'n':
          if (eni_file)
            free(eni_file);
          eni_file = static_cast<char *>(malloc(strlen(optarg)+1));
          memset(eni_file, 0, strlen(optarg)+1);
          memmove(eni_file, optarg, strlen(optarg)+1);
          printf("Using %s\n", eni_file);
          break;
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
  struct timespec dc_period;
  getOptions(argc, argv);

  auto signal_handler = [](int){ run = 0; };
  signal(SIGTERM, signal_handler);
  signal(SIGINT, signal_handler);
  mlockall(MCL_CURRENT | MCL_FUTURE);

  /* Create master by ENI*/
  if (!eni_file) {
      printf("Error: Unspecify ENI/XML file\n");
      exit(0);
  }
  master = motion_servo_master_create(eni_file);
  free(eni_file);
  eni_file = NULL;
  if (master == NULL) {
      return -1;
  }
  /* Motion domain create */
  if (motion_servo_domain_entry_register(master, &domain)) {
      return -1;
  }

  if (!motion_servo_driver_register(master, domain)) {
      return -1;
  }

  motion_servo_set_send_interval(master);
  motion_servo_register_dc(master);
  clock_gettime(CLOCK_MONOTONIC, &dc_period);
  motion_master_set_application_time(master, TIMESPEC2NS(dc_period));

  for (size_t i = 0; i < JOINT_NUM; i++)
  {
    my_servo[i] = new EcrtServo();
    my_servo[i]->setMaster(master);
  }

  if (motion_servo_master_activate(master->master)) {
      printf("fail to activate master\n");
      return -1;
  }

  domain1 = motion_servo_domain_data(domain);
  if (!domain1) {
      printf("fail to get domain data\n");
      return 0;
  }

  for (size_t i = 0; i < JOINT_NUM; i++)
  {
    my_servo[i]->setDomain(domain1);
    my_servo[i]->initialize(0,i);
  }

  for (size_t i = 0; i < JOINT_NUM; i ++)
  {
    servos[i] = (RTmotion::Servo*)my_servo[i];
    configs[i].encoder_count_per_unit_ = PER_CIRCLE_ENCODER;
    axis[i] = new RTmotion::Axis();
    axis[i]->setAxisId(i);
    axis[i]->setAxisConfig(&configs[i]);
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
    moveAbs[i].setExecute(mcFALSE);
    moveAbs[i].setPosition(0.0);
    moveAbs[i].setVelocity(50);
    moveAbs[i].setAcceleration(100);
    moveAbs[i].setDeceleration(100);
    moveAbs[i].setJerk(50.0);
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
  motion_servo_master_release(master);
  shm_blkbuf_close(handle_s);
  shm_blkbuf_close(handle_r);
  for (size_t i = 0; i < JOINT_NUM; i ++)
  {
    delete servos[i];
    delete axis[i];
  }
  printf("\nEnd of Program\n");
  return 0;
}

/****************************************************************************/
