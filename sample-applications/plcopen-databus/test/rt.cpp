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

static volatile int run = 1;
static pthread_t cyclic_thread;

#define MSG_LEN 512
#define JOINT_NUM 6
static char r_buf[MSG_LEN];
static shm_handle_t handle_s, handle_r;

struct joint_commands
{
  uint8_t mode = 0; // "0" position control, "1" velocity control 
  double joint_values[JOINT_NUM] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
};

struct joint_states
{
  double joint_values[JOINT_NUM] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
};

void* my_thread(void* /*arg*/)
{
  struct timespec next_period;
  unsigned int cycle_counter = 0;
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

    /* get the joint commands */
    if (!shm_blkbuf_empty(handle_r))
    {

      ret = shm_blkbuf_read(handle_r, r_buf, sizeof(r_buf));
      if (ret) {
        joint_commands joint_cmds;
        memcpy(&joint_cmds, r_buf, sizeof(joint_cmds));

        for (size_t i = 0; i < JOINT_NUM; i++)
          printf("\t %zu th joint: %f\n", i, joint_cmds.joint_values[i]);
      }
    }

    cycle_counter++;
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
  {
    sched_yield();
  }

  pthread_join(cyclic_thread, NULL);

  printf("\nEnd of Program\n");
  return 0;
}

/****************************************************************************/
