// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file multi-axis-monitor.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */
#include <error.h>
#include <signal.h>
#include <getopt.h>
#include <unistd.h>
#include <pthread.h>
#include <sys/mman.h>
#include <sys/sysinfo.h>

#include <fb/common/include/axis.hpp>
#include <fb/common/include/global.hpp>
#include <fb/public/include/fb_power.hpp>
#include <fb/public/include/fb_move_relative.hpp>
#include <fb/public/include/fb_move_velocity.hpp>
#include <fb/public/include/fb_read_actual_position.hpp>
#include <fb/public/include/fb_read_actual_velocity.hpp>

// Macro
#define AXIS_MAX_NUM (256)
#define CONVEYOR_RATIO (5)
#define SERVO_ENCODER_ACCURACY (0x100000)
#define NSEC_PER_SEC (1000000000L)
#define DIFF_NS(A, B)                                                          \
  (((B).tv_sec - (A).tv_sec) * NSEC_PER_SEC + ((B).tv_nsec) - (A).tv_nsec)
#define CYCLE_COUNTER_PERSEC(X) (NSEC_PER_SEC / 1000 / X)

/* Thread related */
static pthread_t cyclic_thread;
static int cpu_id       = 1;
static volatile int run = 1;

/* RT to NRT data */
static int64_t latency_min_ns = 1000000;
static int64_t latency_max_ns = -1000000;
static int64_t latency_avg_ns = 0;
static uint64_t exec_min_ns   = 1000000;
static uint64_t exec_max_ns   = 0;
static uint64_t exec_avg_ns   = 0;
static uint64_t cycle_count   = 0;

/* Command line arguments */
static bool verbose          = false;
static bool output           = false;
static unsigned int cycle_us = 1000;
static unsigned int axis_num = 6;

using namespace RTmotion;

/* Motion control thread function */
void* rt_func(void* /*arg*/)
{
  /* Timestamps used for cycle */
  struct timespec next_period;

  /* Variables used for time recording */
  struct timespec start_time      = { 0, 0 };
  struct timespec last_start_time = { 0, 0 };
  struct timespec end_time        = { 0, 0 };
  int64_t latency_ns              = 0;
  uint64_t exec_ns                = 0;

  /* RTmotion variables */
  Servo* servo[AXIS_MAX_NUM];
  AxisConfig config[AXIS_MAX_NUM];
  AXIS_REF axis[AXIS_MAX_NUM];
  FbPower fb_power[AXIS_MAX_NUM];
  FbMoveRelative move_rel[AXIS_MAX_NUM];
  FbReadActualPosition read_pos[AXIS_MAX_NUM];
  FbReadActualVelocity read_vel[AXIS_MAX_NUM];

  /* RTmotion variables */
  for (size_t i = 0; i < axis_num; i++)
  {
    servo[i] = new Servo();

    config[i].encoder_count_per_unit_ = SERVO_ENCODER_ACCURACY / CONVEYOR_RATIO;
    config[i].frequency_              = 1.0 / cycle_us * 1000000;

    axis[i] = new Axis();
    axis[i]->setAxisId(i);
    axis[i]->setAxisConfig(&config[i]);
    axis[i]->setServo(servo[i]);

    fb_power[i].setAxis(axis[i]);
    fb_power[i].setEnable(mcTRUE);
    fb_power[i].setEnablePositive(mcTRUE);
    fb_power[i].setEnableNegative(mcTRUE);

    read_pos[i].setAxis(axis[i]);
    read_pos[i].setEnable(mcTRUE);

    read_vel[i].setAxis(axis[i]);
    read_vel[i].setEnable(mcTRUE);

    move_rel[i].setAxis(axis[i]);
    move_rel[i].setDistance(-150);
    move_rel[i].setVelocity(50);
    move_rel[i].setAcceleration(500);
    move_rel[i].setDeceleration(500);
    move_rel[i].setJerk(500);
    move_rel[i].setBufferMode(mcAborting);
    move_rel[i].setExecute(mcFALSE);
  }

  /* Check the requested core is available on the system */
  int n_cores = get_nprocs();
  if (cpu_id < 0 || cpu_id >= n_cores)
  {
    printf("This application is configured to run on core %d, but the system "
           "has cores 0-%d only.\n",
           cpu_id, n_cores - 1);
    return nullptr;
  }

  /* Set CPU core affinity */
  cpu_set_t cpuset;
  CPU_ZERO(&cpuset);
  CPU_SET(cpu_id, &cpuset);
  pthread_setaffinity_np(pthread_self(), sizeof(cpu_set_t), &cpuset);

  /* Start motion cycles */
  clock_gettime(CLOCK_MONOTONIC, &next_period);
  last_start_time = next_period;
  end_time        = next_period;
  while (run)
  {
    next_period.tv_nsec += cycle_us * 1000;
    while (next_period.tv_nsec >= NSEC_PER_SEC)
    {
      next_period.tv_nsec -= NSEC_PER_SEC;
      next_period.tv_sec++;
    }
    clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &next_period, nullptr);
    clock_gettime(CLOCK_MONOTONIC, &start_time);

    /* Latency min, avg, max */
    latency_ns = DIFF_NS(next_period, start_time);
    latency_avg_ns += fabs(latency_ns);
    if (latency_ns > latency_max_ns)
      latency_max_ns = latency_ns;
    if (latency_ns < latency_min_ns)
      latency_min_ns = latency_ns;

    /* Exect time min, avg, max */
    if (cycle_count > 0)
    {
      exec_ns = DIFF_NS(last_start_time, end_time);
      exec_avg_ns += fabs(exec_ns);
      if (exec_ns > exec_max_ns)
        exec_max_ns = exec_ns;
      if (exec_ns < exec_min_ns)
        exec_min_ns = exec_ns;
    }
    last_start_time = start_time;

    /* Run RTmotion update */
    for (size_t i = 0; i < axis_num; i++)
    {
      axis[i]->runCycle();
      fb_power[i].runCycle();
      read_pos[i].runCycle();
      read_vel[i].runCycle();
      move_rel[i].runCycle();
    }

    /* Print axis pos and vel when verbose enabled */
    if (verbose)
    {
      for (size_t i = 0; i < axis_num; i++)
      {
        printf("Current position - %ld: %f,\tvelocity: %f\n", i,
               read_pos[i].getFloatValue(), read_vel[i].getFloatValue());
      }
    }

    /* Trigger axis movement when all axis are powered on */
    mcBOOL power_on = mcTRUE;
    for (size_t i = 0; i < axis_num; i++)
      power_on = (power_on == mcTRUE) &&
                         (fb_power[i].getPowerStatus() == mcTRUE) ?
                     mcTRUE :
                     mcFALSE;

    if (power_on == mcTRUE)
    {
      for (size_t i = 0; i < axis_num; i++)
        move_rel[i].setExecute(mcTRUE);
    }

    /* Control logic for axis */
    for (size_t i = 0; i < axis_num; i++)
    {
      if (move_rel[i].isDone() == mcTRUE)
      {
        move_rel[i].setExecute(mcFALSE);
        move_rel[i].setDistance(-move_rel[i].getPosition());
      }
    }

    clock_gettime(CLOCK_MONOTONIC, &end_time);
    cycle_count++;
  }

  /* Clean up */
  for (size_t i = 0; i < axis_num; i++)
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

/* Logging thread funtion */
static void print_stat()
{
  char* fmt_data = nullptr;

  if (output)
  {
    fmt_data = (char*)"\r%10ld [%10.3f,%10.3f,%10.3f] [%10.3f,%10.3f,%10.3f]";
    printf(fmt_data, cycle_count / CYCLE_COUNTER_PERSEC(cycle_us),
           (float)latency_min_ns / 1000,
           (float)latency_avg_ns / cycle_count / 1000,
           (float)latency_max_ns / 1000, (float)exec_min_ns / 1000,
           (float)exec_avg_ns / cycle_count / 1000, (float)exec_max_ns / 1000);
    fflush(stdout);
  }
}

/* Set thread attributes */
static void setup_sched_parameters(pthread_attr_t* attr, int prio)
{
  struct sched_param p;
  int ret;

  ret = pthread_attr_init(attr);
  if (ret)
    error(1, ret, "pthread_attr_init()");

  ret = pthread_attr_setinheritsched(attr, PTHREAD_EXPLICIT_SCHED);
  if (ret)
    error(1, ret, "pthread_attr_setinheritsched()");

  ret = pthread_attr_setschedpolicy(attr, prio ? SCHED_FIFO : SCHED_OTHER);
  if (ret)
    error(1, ret, "pthread_attr_setschedpolicy()");

  p.sched_priority = prio;
  ret              = pthread_attr_setschedparam(attr, &p);
  if (ret)
    error(1, ret, "pthread_attr_setschedparam()");
}

/* Parse arguments */
static void getOptions(int argc, char** argv)
{
  int index;
  static struct option long_options[] = {
    // name           has_arg             flag   val
    { "interval", required_argument, nullptr, 'i' },
    { "cpu_affinity", required_argument, nullptr, 'a' },
    { "axis_number", required_argument, nullptr, 'm' },
    { "verbose", no_argument, nullptr, 'v' },
    { "output", no_argument, nullptr, 'o' },
    { "help", no_argument, nullptr, 'h' },
    {}
  };
  do
  {
    index = getopt_long(argc, argv, "i:a:m:voh", long_options, nullptr);
    switch (index)
    {
      case 'i':
        cycle_us = (unsigned int)atof(optarg);
        printf("Cycle-time: Set cycle time to %d (us)\n", cycle_us);
        break;
      case 'a':
        cpu_id = (unsigned int)atof(optarg);
        printf("CPU affinity: Set CPU affinity of rt thread to core %d\n",
               cpu_id);
        break;
      case 'm':
        axis_num = (unsigned int)atof(optarg);
        if (axis_num < 1)
          printf("Error: Invalid axis number %d\n", axis_num);
        else
          printf("Axis number: Set axis number to %d\n", axis_num);
        break;
      case 'v':
        verbose = true;
        printf("verbose: print pos and vel values.\n");
        break;
      case 'o':
        output = true;
        printf("Output: print time statistic in %d us cycle.\n", cycle_us * 10);
        break;
      case 'h':
        printf("Global options:\n");
        printf("    --interval     -i  Specify RT cycle time(us).\n");
        printf("    --affinity     -a  Specify RT thread CPU affinity.\n");
        printf("    --axis-num     -m  Specify axis number.\n");
        printf("    --verbose      -v  Be verbose.\n");
        printf("    --output       -o  Enable output in 10ms cycle.\n");
        printf("    --help         -h  Show this help.\n");
        exit(0);
        break;
    }
  } while (index != -1);
}

/* Main thread */
int main(int argc, char* argv[])
{
  /* Parse arguments */
  getOptions(argc, argv);

  /* Register signal */
  auto signal_handler = [](int /*unused*/) { run = 0; };
  signal(SIGTERM, signal_handler);
  signal(SIGINT, signal_handler);

  mlockall(MCL_CURRENT | MCL_FUTURE);

  /* Create cyclic RT-thread */
  pthread_attr_t tattr;
  setup_sched_parameters(&tattr, 99);
  if (pthread_create(&cyclic_thread, &tattr, rt_func, nullptr))
  {
    fprintf(stderr, "pthread_create cyclic task failed\n");
    pthread_attr_destroy(&tattr);
    return 1;
  }

  /* Print output header */
  char* fmt_head;
  fmt_head = (char*)"    Dur(s) "
                    "           Sched_lat(us)          "
                    "           Exec_time(us)          \n";
  printf("%s", fmt_head);

  /* Main loop to print stat */
  while (run)
  {
    print_stat();
    usleep(cycle_us * 10);
  }

  pthread_cancel(cyclic_thread);
  pthread_join(cyclic_thread, nullptr);
  printf("\nEnd of Program\n");
  return 0;
}