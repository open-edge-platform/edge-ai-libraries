// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file rt.cpp
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

#define CYCLE_US 1000
#define NSEC_PER_SEC (1000000000L)
#ifndef DIFF_NS
#define DIFF_NS(A,B)    		(((B).tv_sec - (A).tv_sec)*NSEC_PER_SEC + ((B).tv_nsec)-(A).tv_nsec)
#endif

static volatile int run = 1;
static pthread_t cyclic_thread;

/* Shm related data types
 * s_buf, handle_s: data sent from RT domain
 * r_buf, handle_r: data sent to RT domain
 */
#define MSG_LEN 150000
#define JOINT_NUM 6
#define POINT_NUM 100
static char s_buf[MSG_LEN];
static char r_buf[MSG_LEN];
static shm_handle_t handle_s, handle_r;

struct TrajPoint
{
  double positions[JOINT_NUM] = {};
  double velocities[JOINT_NUM] = {};
  double accelerations[JOINT_NUM] = {};
  double effort[JOINT_NUM] = {};
  double time_from_start;
};

struct TrajCmd
{
  uint32_t point_num = 0;
  TrajPoint points[POINT_NUM]= {};
};

struct JointState
{
  double joint_pos[JOINT_NUM] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
  double joint_vel[JOINT_NUM] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
  bool traj_done = false;
  bool error = false;
};

static TrajCmd traj_cmd;
static JointState joint_state;

void* my_thread(void* /*arg*/)
{
  struct timespec next_period, start_time, current_time;
  unsigned int index = 0;
  bool traj_start = false;
  int ret;

  struct sched_param param = {};
  param.sched_priority = 99;
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
    clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &next_period, NULL);

    /* Get the trajectory commands */
    if (!shm_blkbuf_empty(handle_r))
    {
      ret = shm_blkbuf_read(handle_r, r_buf, sizeof(r_buf));
      if (ret) 
      {
        clock_gettime(CLOCK_MONOTONIC, &start_time);
        index = 0;
        traj_start = true;
        joint_state.traj_done = false;
        memcpy(&traj_cmd, r_buf, sizeof(traj_cmd));
        printf("Received the trajectory command.\n");
        // for (size_t i = 0; i < traj_cmd.point_num; i++)
        // {
        //   printf("The %ldth point: ", i);
        //   for (size_t j = 0; j < JOINT_NUM; j++)
        //     printf(" %f", traj_cmd.points[i].positions[j]);
        //   printf("\n");
        // }
      }
    }

    /* Execute the trajectory */
    clock_gettime(CLOCK_MONOTONIC, &current_time);
    if (traj_start)
    {
      if (DIFF_NS(start_time, current_time) >= traj_cmd.points[index].time_from_start)
      {
        // printf("duration %ld, waypoint time: %f\n", DIFF_NS(start_time, current_time), traj_cmd.points[index].time_from_start);
        if (index < traj_cmd.point_num)
        {
          for (size_t i = 0; i < JOINT_NUM; i++)
            joint_state.joint_pos[i] = traj_cmd.points[index].positions[i];
          
          index++;
        }
        else
        {
          joint_state.traj_done = true;
          traj_start = false;
          printf("Trajectory done.\n");
        }
      }
    }

    /* Send the joint state */
    memcpy(s_buf, &joint_state, sizeof(joint_state));
    if (!shm_blkbuf_full(handle_s))
    {
      ret = shm_blkbuf_write(handle_s, s_buf, sizeof(s_buf));
      // printf("%s: sent %d bytes\n", __FUNCTION__, ret);
    }
  }
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

  /* Create cyclic RT-thread */
  pthread_attr_t thattr;
  pthread_attr_init(&thattr);
  pthread_attr_setdetachstate(&thattr, PTHREAD_CREATE_JOINABLE);

  handle_s = shm_blkbuf_init((char*)"rtsend", 16, MSG_LEN);
  handle_r = shm_blkbuf_init((char*)"rtread", 16, MSG_LEN);

  if (pthread_create(&cyclic_thread, &thattr, &my_thread, NULL))
  {
    fprintf(stderr, "pthread_create cyclic task failed\n");
    return 1;
  }

  while (run)
    sched_yield();

  pthread_join(cyclic_thread, NULL);
  shm_blkbuf_close(handle_s);
  shm_blkbuf_close(handle_r);
  printf("\nEnd of Program\n");
  return 0;
}

/****************************************************************************/
