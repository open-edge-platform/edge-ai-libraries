// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

#include <fb/common/include/axis.hpp>
#include <fb/public/include/fb_move_absolute.hpp>
#include <fb/public/include/fb_move_additive.hpp>
#include <fb/public/include/fb_move_relative.hpp>
#include <fb/public/include/fb_move_velocity.hpp>
#include <fb/public/include/fb_power.hpp>
#include <fb/public/include/fb_read_actual_position.hpp>
#include <fb/public/include/fb_read_actual_velocity.hpp>
#include <fb/common/include/global.hpp>
#include <ecrt_config.hpp>
#include <ecrt_servo.hpp>
#include <errno.h>
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

// Ethercat servo
static EcrtServo* my_servo_1;
static EcrtServo* my_servo_2;

// Thread related
static pthread_t cyclic_thread;
static volatile int run      = 1;
static unsigned int cycle_us = 1000;

// Ethercat related
static servo_master* master = nullptr;
static uint8_t* domain1;
void* domain;

// Command line arguments
static char* eni_file = nullptr;

using namespace RTmotion;

static AXIS_REF axis_1;
static AXIS_REF axis_2;
static FbPower fb_power_1;
static FbPower fb_power_2;
static FbMoveRelative move_rel;
static FbMoveVelocity move_vel;
static FbReadActualPosition read_pos_1;
static FbReadActualPosition read_pos_2;
static FbReadActualVelocity read_vel_1;
static FbReadActualVelocity read_vel_2;

// Cycle function
void* my_thread(void* /*arg*/)
{
  struct timespec next_period, dc_period;
  unsigned int cycle_count = 0;

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

    axis_1->runCycle();
    axis_2->runCycle();
    fb_power_1.runCycle();
    fb_power_2.runCycle();
    move_rel.runCycle();
    move_vel.runCycle();
    read_pos_1.runCycle();
    read_pos_2.runCycle();
    read_vel_1.runCycle();
    read_vel_2.runCycle();

    printf("Current position - 1: %f,\tvelocity: %f \n",
           read_pos_1.getFloatValue(), read_vel_1.getFloatValue());
    printf("Current position - 2: %f,\tvelocity: %f \n",
           read_pos_2.getFloatValue(), read_vel_2.getFloatValue());

    if (fb_power_1.getPowerStatus() == mcTRUE &&
        fb_power_2.getPowerStatus() == mcTRUE)
    {
      move_rel.setExecute(mcTRUE);
      move_vel.setExecute(mcTRUE);
    }

    if (move_rel.isDone() == mcTRUE)
    {
      cycle_count++;
      if (cycle_count > 500)
      {
        printf("FbMoveRelative is done\n");
        move_rel.setExecute(mcFALSE);
        move_rel.setPosition(-move_rel.getPosition());
        cycle_count = 0;
      }
    }

    clock_gettime(CLOCK_MONOTONIC, &dc_period);
    motion_servo_sync_dc(master->master, TIMESPEC2NS(dc_period));
    motion_servo_send_process(master->master, static_cast<uint8_t*>(domain));
  }
  return nullptr;
}

static void getOptions(int argc, char** argv)
{
  int index;
  static struct option long_options[] = {
    // name		has_arg				flag	val
    { "eni", required_argument, nullptr, 'n' },
    { "interval", required_argument, nullptr, 'i' },
    { "help", no_argument, nullptr, 'h' },
    {}
  };
  do
  {
    index = getopt_long(argc, argv, "n:i:h", long_options, nullptr);
    switch (index)
    {
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
      case 'h':
        printf("Global options:\n");
        printf("    --eni       -n  Specify ENI/XML file\n");
        printf("    --interval  -i  Specify RT cycle time\n");
        printf("    --help      -h  Show this help.\n");
        exit(0);
        break;
    }
  } while (index != -1);
}

int main(int argc, char* argv[])
{
  struct timespec dc_period;
  auto signal_handler = [](int /*unused*/) { run = 0; };
  getOptions(argc, argv);
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
  /* Motion domain create */
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

  my_servo_1 = new EcrtServo();
  my_servo_2 = new EcrtServo();
  my_servo_1->setMaster(master);
  my_servo_2->setMaster(master);

  if (motion_servo_master_activate(master->master))
  {
    printf("fail to activate master\n");
    return -1;
  }

  domain1 = motion_servo_domain_data(domain);
  if (!domain1)
  {
    printf("fail to get domain data\n");
    return 0;
  }

  my_servo_1->setDomain(domain1);
  my_servo_2->setDomain(domain1);

  my_servo_1->initialize(0, 0);
  my_servo_2->initialize(0, 1);

  Servo* servo_1;
  servo_1 = (Servo*)my_servo_1;
  Servo* servo_2;
  servo_2 = (Servo*)my_servo_2;

  AxisConfig config_1;
  config_1.encoder_count_per_unit_ = PER_CIRCLE_ENCODER;
  config_1.frequency_              = 1.0 / cycle_us * 1000000;
  AxisConfig config_2;
  config_2.encoder_count_per_unit_ = PER_CIRCLE_ENCODER;
  config_2.frequency_              = 1.0 / cycle_us * 1000000;

  axis_1 = new Axis();
  axis_1->setAxisId(1);
  axis_1->setAxisConfig(&config_1);
  axis_1->setServo(servo_1);

  axis_2 = new Axis();
  axis_2->setAxisId(2);
  axis_2->setAxisConfig(&config_2);
  axis_2->setServo(servo_2);

  fb_power_1.setAxis(axis_1);
  fb_power_1.setEnable(mcTRUE);
  fb_power_1.setEnablePositive(mcTRUE);
  fb_power_1.setEnableNegative(mcTRUE);

  fb_power_2.setAxis(axis_2);
  fb_power_2.setEnable(mcTRUE);
  fb_power_2.setEnablePositive(mcTRUE);
  fb_power_2.setEnableNegative(mcTRUE);

  move_rel.setAxis(axis_1);
  // moveRel.setDistance(100);
  move_rel.setPosition(-100);
  move_rel.setVelocity(100);
  move_rel.setAcceleration(50);
  move_rel.setDeceleration(50);
  move_rel.setJerk(500);
  move_rel.setBufferMode(mcAborting);
  move_rel.setExecute(mcFALSE);

  move_vel.setAxis(axis_2);
  move_vel.setVelocity(50);
  move_vel.setAcceleration(50);
  move_vel.setDeceleration(50);
  move_vel.setJerk(500);
  move_vel.setBufferMode(mcAborting);
  move_vel.setExecute(mcFALSE);

  read_pos_1.setAxis(axis_1);
  read_pos_1.setEnable(mcTRUE);

  read_vel_1.setAxis(axis_1);
  read_vel_1.setEnable(mcTRUE);

  read_pos_2.setAxis(axis_2);
  read_pos_2.setEnable(mcTRUE);

  read_vel_2.setAxis(axis_2);
  read_vel_2.setEnable(mcTRUE);

  /* Create cyclic RT-thread */
  pthread_attr_t thattr;
  pthread_attr_init(&thattr);
  pthread_attr_setdetachstate(&thattr, PTHREAD_CREATE_JOINABLE);

  if (pthread_create(&cyclic_thread, &thattr, &my_thread, nullptr))
  {
    fprintf(stderr, "pthread_create cyclic task failed\n");
    return 1;
  }

  while (run)
  {
    sched_yield();
  }

  pthread_join(cyclic_thread, nullptr);
  motion_servo_master_release(master);
  delete my_servo_1;
  delete my_servo_2;
  delete axis_1;
  delete axis_2;
  printf("End of Program\n");
  return 0;
}
