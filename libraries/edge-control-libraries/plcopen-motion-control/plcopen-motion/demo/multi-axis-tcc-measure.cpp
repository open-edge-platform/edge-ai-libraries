// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file multi-axis.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <fb/common/include/axis.hpp>
#include <fb/common/include/global.hpp>
#include <fb/public/include/fb_power.hpp>
#include <fb/public/include/fb_move_relative.hpp>
#include <fb/public/include/fb_move_velocity.hpp>
#include <fb/public/include/fb_read_actual_position.hpp>
#include <fb/public/include/fb_read_actual_velocity.hpp>

#include <thread>
#include <errno.h>
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
#include <string.h>

#include <ittnotify/ittnotify.h>
#include <tcc/err_code.h>
#include <tcc/cache.h>
#include <tcc/measurement.h>
#include <tcc/measurement_helpers.h>

#define COLLECTOR_LIBRARY_VAR_NAME "INTEL_LIBITTNOTIFY64"
#define TCC_COLLECTOR_NAME "libtcc_collector.so"
/**
 * @brief Sets an environment variable if it was not set before.
 */
inline static int setenv_if_not_set(const char* var_name, const char* value)
{
  if (setenv(var_name, value, 0) != 0)
  {
    fprintf(stderr, "setenv: can't set %s to '%s': %s(%i)\n", var_name, value,
            strerror(errno), errno);
    return -1;
  }
  return 0;
}
static __itt_domain* domain                    = NULL;
static __itt_string_handle* measurement_handle = NULL;

#define CYCLE_US 1000
#define BUFFER_SIZE 1000
#define AXIS_NUM 6

static volatile int run = 1;
static pthread_t cyclic_thread;

static double running_time         = 1.0;
static unsigned int running_time_t = (unsigned int)(BUFFER_SIZE * running_time);

using namespace RTmotion;
static AXIS_REF axis[AXIS_NUM];
static Servo* servo[AXIS_NUM];
static FbPower* fb_power[AXIS_NUM];
static FbMoveRelative* fb_move_rel[AXIS_NUM];
static FbReadActualPosition* readPos[AXIS_NUM];
static FbReadActualVelocity* readVel[AXIS_NUM];

void print_statistics()
{
  int tcc_sts                                 = 0;
  struct tcc_measurement* tcc_measurement_ptr = NULL;
  tcc_sts =
      tcc_measurement_get(domain, measurement_handle, &tcc_measurement_ptr);
  if (TCC_E_SUCCESS == tcc_sts)
  {
    tcc_measurement_get_avg(tcc_measurement_ptr);
    printf("\n*** Statistics for workload ****************************\n");
    printf(
        "    Minimum total latency: %.0f CPU cycles (%ld ns)\n",
        tcc_measurement_ptr->clk_min,
        tcc_measurement_convert_clock_to_timespec(tcc_measurement_ptr->clk_min)
            .tv_nsec);
    printf(
        "    Maximum total latency: %.0f CPU cycles (%ld ns)\n",
        tcc_measurement_ptr->clk_max,
        tcc_measurement_convert_clock_to_timespec(tcc_measurement_ptr->clk_max)
            .tv_nsec);
    printf("    Average total latency: %.0f CPU cycles (%ld ns)\n",
           tcc_measurement_ptr->clk_result,
           tcc_measurement_convert_clock_to_timespec(
               tcc_measurement_ptr->clk_result)
               .tv_nsec);
    printf("********************************************************\n\n");
  }
}

void* my_thread(void* /*arg*/)
{
  int tcc_status                              = TCC_E_SUCCESS;
  static const char measurement_name[]        = "MOTION";
  struct tcc_measurement* tcc_measurement_ptr = NULL;

  /* Initialize thmeasuremente ITT task handle to collect performance data for
   * the sample workload */
  domain             = __itt_domain_create("TCC");
  measurement_handle = __itt_string_handle_create(measurement_name);
  if (!domain || !measurement_handle)
  {
    printf("Unable to create ITT handles\n");
    return NULL;
  }

  setenv_if_not_set(COLLECTOR_LIBRARY_VAR_NAME, TCC_COLLECTOR_NAME);

  /* Get tcc_measurement structure with collected data from ITT. Measurements
   * will be printed if the measurement library collector is solely used */
  if ((tcc_status = tcc_measurement_get(domain, measurement_handle,
                                        &tcc_measurement_ptr)) != TCC_E_SUCCESS)
  {
    if (tcc_status == -TCC_E_NOT_AVAILABLE &&
        getenv(COLLECTOR_LIBRARY_VAR_NAME) != NULL)
    {
      printf("External collector is used.\nExecution will continue with no "
             "measurement results.\n");
    }
    else
    {
      printf("Collector is not set. Execution will continue with no "
             "measurement results.\n");
      printf("Use -c or --collect flag to enable collection or set environment "
             "variable manually.\n");
    }
  }

  struct timespec next_period;
  unsigned int cycle_counter = 0;

  struct sched_param param = {};
  param.sched_priority     = 99;
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

    __itt_task_begin(domain, __itt_null, __itt_null, measurement_handle);
    for (size_t i = 0; i < AXIS_NUM; i++)
    {
      axis[i]->runCycle();
      fb_power[i]->runCycle();
      fb_move_rel[i]->runCycle();
      readPos[i]->runCycle();
      readVel[i]->runCycle();
    }

    if (cycle_counter > running_time_t)
      run = 0;

    for (size_t i = 0; i < AXIS_NUM; i++)
    {
      if (fb_move_rel[i]->isEnabled() == mcFALSE &&
          fb_power[i]->getPowerStatus() == mcTRUE)
        fb_move_rel[i]->setExecute(mcTRUE);

      // if (fb_move_rel[i].isDone() && (cycle_counter % 6000 == 0))
      if (fb_move_rel[i]->isDone() == mcTRUE)
      {
        fb_move_rel[i]->setExecute(mcFALSE);
        fb_move_rel[i]->setPosition(-fb_move_rel[i]->getPosition());
      }
    }
    __itt_task_end(domain);

    // printf("Joint %d, pos: %f, vel: %f\n",
    //         0, readPos[0].getFloatValue(), readVel[0].getFloatValue());

    cycle_counter++;
  }

  print_statistics();
  return NULL;
}

static void getOptions(int argc, char** argv)
{
  int index;
  static struct option longOptions[] = {
    // name		has_arg				flag	val
    { "time", required_argument, NULL, 't' },
    { "help", no_argument, NULL, 'h' },
    {}
  };
  do
  {
    index = getopt_long(argc, argv, "t:h", longOptions, NULL);
    switch (index)
    {
      case 't':
        running_time   = atof(optarg);
        running_time_t = (unsigned int)(BUFFER_SIZE * running_time);
        printf("Time: Set running time to %d ms\n", running_time_t);
        break;
      case 'h':
        printf("Global options:\n");
        printf("    --time  -t  Set running time(s).\n");
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
  auto signal_handler = [](int) { run = 0; };
  signal(SIGTERM, signal_handler);
  signal(SIGINT, signal_handler);
  mlockall(MCL_CURRENT | MCL_FUTURE);
#ifdef CACHE_MISS_CHECK
  uint64_t cnt0;
  uint64_t cnt1;
  uint64_t cnt2;
  uint64_t cnt3;

  cnt0 = __rdpmc(0);
  cnt1 = __rdpmc(1);
  cnt2 = __rdpmc(2);
  cnt3 = __rdpmc(3);
#endif
  for (size_t i = 0; i < AXIS_NUM; i++)
  {
    axis[i] = new Axis();
    axis[i]->setAxisId(i);

    servo[i] = new Servo();
    axis[i]->setServo(servo[i]);

    fb_power[i] = new FbPower();
    fb_power[i]->setAxis(axis[i]);
    fb_power[i]->setEnable(mcTRUE);
    fb_power[i]->setEnablePositive(mcTRUE);
    fb_power[i]->setEnableNegative(mcTRUE);

    fb_move_rel[i] = new FbMoveRelative();
    fb_move_rel[i]->setAxis(axis[i]);
    fb_move_rel[i]->setContinuousUpdate(mcFALSE);
    fb_move_rel[i]->setDistance(200);
    fb_move_rel[i]->setVelocity(500);
    fb_move_rel[i]->setAcceleration(500);
    fb_move_rel[i]->setJerk(5000);
    fb_move_rel[i]->setBufferMode(mcAborting);

    readPos[i] = new FbReadActualPosition();
    readPos[i]->setAxis(axis[i]);
    readPos[i]->setEnable(mcTRUE);

    readVel[i] = new FbReadActualVelocity();
    readVel[i]->setAxis(axis[i]);
    readVel[i]->setEnable(mcTRUE);
  }

  printf("Axis init succeed. Axis size: %ld.\n", sizeof(Axis));
  printf("Function blocks init succeed.\n");

  /* Create cyclic RT-thread */
  pthread_attr_t thattr;
  pthread_attr_init(&thattr);
  pthread_attr_setdetachstate(&thattr, PTHREAD_CREATE_JOINABLE);

  if (pthread_create(&cyclic_thread, &thattr, &my_thread, NULL))
  {
    fprintf(stderr, "pthread_create cyclic task failed\n");
    return -1;
  }

  pthread_join(cyclic_thread, NULL);
#ifdef CACHE_MISS_CHECK
  printf("L2 Hit %lld, L2 Miss %lld, L3 Hit %lld, L3 Miss %lld\n",
         __rdpmc(0) - cnt0, __rdpmc(1) - cnt1, __rdpmc(2) - cnt2,
         __rdpmc(3) - cnt3);
#endif
  /* Releasing memory */
  printf("Deallocating memory\n");
  for (size_t i = 0; i < AXIS_NUM; i++)
  {
    delete axis[i];
    delete servo[i];
    delete fb_power[i];
    delete fb_move_rel[i];
    delete readPos[i];
    delete readVel[i];
  }

  printf("End of Program\n");
  return 0;
}

/****************************************************************************/
