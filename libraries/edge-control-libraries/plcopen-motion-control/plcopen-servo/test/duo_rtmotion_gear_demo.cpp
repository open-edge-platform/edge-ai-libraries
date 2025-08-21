// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

#include <stdio.h>
#include <string.h>
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
#include <iostream>
#include <motionentry.h>
#include <ecrt_config.hpp>
#include <ecrt_servo.hpp>
#include <fb/common/include/axis.hpp>
#include <fb/common/include/global.hpp>
#include <fb/public/include/fb_power.hpp>
#include <fb/public/include/fb_move_velocity.hpp>
#include <fb/public/include/fb_read_actual_velocity.hpp>
#include <fb/public/include/fb_read_actual_position.hpp>
#include <fb/private/include/fb_gear_in.hpp>
#include <fb/private/include/fb_gear_out.hpp>

// Ethercat servo
static EcrtServo* my_servo_1;
static EcrtServo* my_servo_2;

// Thread related
static pthread_t cyclic_thread;
static volatile mcINT run = 1;
static mcUINT cycle_us    = 1000;

// Ethercat related
static servo_master* master = nullptr;
static mcUSINT* domain1;
void* domain;

// Command line arguments
static char* eni_file     = nullptr;
static mcBOOL verbose     = mcFALSE;
static mcBOOL log_flag    = mcFALSE;
static mcULINT ratio      = PER_CIRCLE_ENCODER;
static mcINT numerator    = 2;
static mcUINT denominator = 1;

using namespace RTmotion;

static AXIS_REF axis_1;
static AXIS_REF axis_2;
static FbPower fb_power_1;
static FbPower fb_power_2;
static FbMoveVelocity fb_move_vel;
static FbGearIn fb_gear_in;
static FbGearOut fb_gear_out;
static FbReadActualVelocity fb_read_vel_1;
static FbReadActualVelocity fb_read_vel_2;
static FbReadActualPosition fb_read_pos_1;
static FbReadActualPosition fb_read_pos_2;

// log data
static char column_string[] = "FbGearIn.Execute,\
              FbGearIn.InGear,\
              FbGearIn.Active,\
              FbGearIn.Busy,\
              FbGearIn.Error,\
              FbGearOut.Execute,\
              FbGearOut.Done,\
              FbGearOut.Busy,\
              FbGearOut.Error,\
              master.vel,\
              slave.vel,\
              slave.axisState";
static char log_file_name[] = "duo_rtmotion_gear_demo_test_results.csv";
static FILE* log_fptr       = nullptr;
typedef struct
{
  mcBOOL execute;
  mcBOOL in_gear;
  mcBOOL active;
  mcBOOL done;
  mcBOOL busy;
  mcBOOL error;
} fb_gear_signal;
static fb_gear_signal* fb_gear_in_signal  = nullptr;
static fb_gear_signal* fb_gear_out_signal = nullptr;
static mcBOOL fb_gear_in_execute_state    = mcFALSE;
static mcBOOL fb_gear_out_execute_state   = mcFALSE;
static mcREAL* master_vel_ptr             = nullptr;
static mcREAL* slave_vel_ptr              = nullptr;
static mcUSINT* slave_axis_state_ptr      = nullptr;
static mcULINT record_cycle               = 35000;
static mcULINT record_cycle_count         = 0;

// Cycle function
void* my_thread(void* /*arg*/)
{
  struct timespec next_period, dc_period;
  mcULINT cycle_count = 0;

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
    fb_move_vel.runCycle();
    fb_gear_in.runCycle();
    fb_gear_out.runCycle();
    fb_read_vel_1.runCycle();
    fb_read_vel_2.runCycle();
    fb_read_pos_1.runCycle();
    fb_read_pos_2.runCycle();

    if (fb_power_1.getPowerStatus() == mcTRUE &&
        fb_power_2.getPowerStatus() == mcTRUE)
    {
      fb_move_vel.setExecute(mcTRUE);
      if (cycle_count < 15000)
      {
        fb_gear_in.setExecute(mcTRUE);
        fb_gear_in_execute_state = mcTRUE;
      }
    }

    if (cycle_count % 5000 == 0)
    {
      fb_move_vel.setVelocity(-fb_move_vel.getVelocity());
      fb_move_vel.setExecute(mcFALSE);
    }

    /* falling edge test of MC_GearIn */
    if (cycle_count == 15000)
    {
      fb_gear_in.setExecute(mcFALSE);
      fb_gear_in_execute_state = mcFALSE;
    }

    /* reexectue MC_GearIn */
    if (cycle_count == 18000)
    {
      fb_gear_in.setExecute(mcTRUE);
      fb_gear_in_execute_state = mcTRUE;
    }

    /* execute MC_GearOut */
    if (cycle_count == 25000)
    {
      fb_gear_out.setExecute(mcTRUE);
      fb_gear_out_execute_state = mcTRUE;
    }

    /* falling edge test of MC_GearOut */
    if (cycle_count == 30000)
    {
      fb_gear_out.setExecute(mcFALSE);
      fb_gear_out_execute_state = mcFALSE;
    }

    if (verbose == mcTRUE)
    {
      printf("Current Master velocity: %f\t   Current Slave velocity: %f   "
             "Current Slave state: %d\n",
             fb_read_vel_1.getFloatValue(), fb_read_vel_2.getFloatValue(),
             axis_2->getAxisState());
    }

    if (fb_gear_in.isError() == mcTRUE)
    {
      printf("FbGearIn error! Error ID:%d\n", fb_gear_in.getErrorID());
    }
    if (fb_gear_out.isError() == mcTRUE)
    {
      printf("FbGearOut error! Error ID:%d\n", fb_gear_out.getErrorID());
    }

    /* Write fb inputs and outputs to .cvs file*/
    if (log_flag == mcTRUE)
    {
      /* Save RT data to memory array */
      if (cycle_count < record_cycle)
      {
        /* IO signals of fb_read_digital_input */
        fb_gear_in_signal[record_cycle_count].execute =
            fb_gear_in_execute_state;
        fb_gear_in_signal[record_cycle_count].in_gear = fb_gear_in.getInGear();
        fb_gear_in_signal[record_cycle_count].active  = fb_gear_in.isActive();
        fb_gear_in_signal[record_cycle_count].busy    = fb_gear_in.isBusy();
        fb_gear_in_signal[record_cycle_count].error   = fb_gear_in.isError();
        /* IO signals of fb_read_digital_output */
        fb_gear_out_signal[record_cycle_count].execute =
            fb_gear_out_execute_state;
        fb_gear_out_signal[record_cycle_count].done  = fb_gear_out.isDone();
        fb_gear_out_signal[record_cycle_count].busy  = fb_gear_out.isBusy();
        fb_gear_out_signal[record_cycle_count].error = fb_gear_out.isError();
        master_vel_ptr[record_cycle_count] = fb_read_vel_1.getFloatValue();
        slave_vel_ptr[record_cycle_count]  = fb_read_vel_2.getFloatValue();
        slave_axis_state_ptr[record_cycle_count] = axis_2->getAxisState();
        record_cycle_count++;
      }
    }
    clock_gettime(CLOCK_MONOTONIC, &dc_period);
    motion_servo_sync_dc(master->master, TIMESPEC2NS(dc_period));
    motion_servo_send_process(master->master, static_cast<mcUSINT*>(domain));
    cycle_count++;
  }
  return nullptr;
}

static void getOptions(int argc, char** argv)
{
  int index;
  static struct option long_options[] = {
    // name             has_arg  flag	val
    { "eni", required_argument, nullptr, 'n' },
    { "interval", required_argument, nullptr, 'i' },
    { "ratio", required_argument, nullptr, 'r' },
    { "gear numerator", required_argument, nullptr, 'g' },
    { "gear denominator", required_argument, nullptr, 'd' },
    { "verbose", no_argument, nullptr, 'v' },
    { "log", no_argument, nullptr, 'l' },
    { "help", no_argument, nullptr, 'h' },
    {}
  };
  do
  {
    index = getopt_long(argc, argv, "n:i:r:g:d:vlh", long_options, nullptr);
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
      case 'r':
        ratio = (u_int64_t)atof(optarg);
        printf("Ratio: Set encoder ratio to %ld\n", ratio);
        break;
      case 'g':
        numerator = (mcINT)atof(optarg);
        printf("Gear numerator: Set gear numerator to %d.\n", denominator);
        break;
      case 'd':
        denominator = (mcUINT)atof(optarg);
        if (denominator == 0)
        {
          printf("Error: denominator should not be 0!\n");
          exit(0);
        }
        printf("Gear Denominator: Set gear denominator to %d.\n", denominator);
        break;
      case 'v':
        verbose = mcTRUE;
        printf("verbose: print pos and vel values.\n");
        break;
      case 'l':
        log_flag = mcTRUE;
        printf("log: record fb signals in a csv file.\n");
        break;
      case 'h':
        printf("Global options:\n");
        printf("    --eni             -n  Specify ENI/XML file\n");
        printf("    --interval        -i  Specify RT cycle time\n");
        printf("    --rat             -r  Specify encoder ratio\n");
        printf(
            "    --gear numerator  -g  Specify gear numerator (default:1)\n");
        printf(
            "    --denominator     -d  Specify gear denominator (default:1)\n");
        printf("    --ver             -v  Specify verbose print\n");
        printf("    --log             -l  Enable data log.\n");
        printf("    --help            -h  Show this help.\n");
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

  // my_servo_1 = new Servo();
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
  // my_servo_2->initialize(0,0);

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

  fb_move_vel.setAxis(axis_1);
  fb_move_vel.setVelocity(20);
  fb_move_vel.setAcceleration(15);
  fb_move_vel.setDeceleration(15);
  fb_move_vel.setJerk(500);
  fb_move_vel.setBufferMode(mcAborting);
  fb_move_vel.setExecute(mcFALSE);

  /* initialize MC_GearIn */
  fb_gear_in.setMaster(axis_1);
  fb_gear_in.setSlave(axis_2);
  fb_gear_in.setRatioNumerator(numerator);
  fb_gear_in.setRatioDenominator(denominator);
  fb_gear_in.setAcceleration(100);
  fb_gear_in.setDeceleration(100);
  fb_gear_in.setJerk(500);
  fb_gear_in.setBufferMode(mcAborting);

  /* initialize MC_GearOut */
  fb_gear_out.setSlave(axis_2);

  fb_read_vel_1.setAxis(axis_1);
  fb_read_vel_1.setEnable(mcTRUE);

  fb_read_vel_2.setAxis(axis_2);
  fb_read_vel_2.setEnable(mcTRUE);

  fb_read_pos_1.setAxis(axis_1);
  fb_read_pos_1.setEnable(mcTRUE);

  fb_read_pos_2.setAxis(axis_2);
  fb_read_pos_2.setEnable(mcTRUE);

  /* Initialize csv output */
  if (log_flag == mcTRUE)
  {
    fb_gear_in_signal =
        (fb_gear_signal*)malloc(sizeof(fb_gear_signal) * record_cycle);
    memset(fb_gear_in_signal, 0, sizeof(fb_gear_signal) * record_cycle);
    fb_gear_out_signal =
        (fb_gear_signal*)malloc(sizeof(fb_gear_signal) * record_cycle);
    memset(fb_gear_out_signal, 0, sizeof(fb_gear_signal) * record_cycle);
    master_vel_ptr = (mcREAL*)malloc(sizeof(mcREAL) * record_cycle);
    memset(master_vel_ptr, 0, sizeof(mcREAL) * record_cycle);
    slave_vel_ptr = (mcREAL*)malloc(sizeof(mcREAL) * record_cycle);
    memset(slave_vel_ptr, 0, sizeof(mcREAL) * record_cycle);
    slave_axis_state_ptr = (mcUSINT*)malloc(sizeof(mcUSINT) * record_cycle);
    memset(slave_axis_state_ptr, 0, sizeof(mcUSINT) * record_cycle);
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

  while (run)
  {
    sched_yield();
  }

  if (log_flag == mcTRUE && record_cycle_count > 0)
  {
    FILE* fptr;
    /* Open file */
    if ((fptr = fopen(log_file_name, "a")) == nullptr)
    {
      printf("Error when open file \"%s\".\n", log_file_name);
      return -1;
    }
    /* write Fb signals */
    for (size_t i = 0; i < record_cycle_count; i++)
    {
      fprintf(fptr, "%d,%d,%d,%d,%d,",
              static_cast<bool>(fb_gear_in_signal[i].execute),
              static_cast<bool>(fb_gear_in_signal[i].in_gear),
              static_cast<bool>(fb_gear_in_signal[i].active),
              static_cast<bool>(fb_gear_in_signal[i].busy),
              static_cast<bool>(fb_gear_in_signal[i].error));
      fprintf(fptr, "%d,%d,%d,%d,",
              static_cast<bool>(fb_gear_out_signal[i].execute),
              static_cast<bool>(fb_gear_out_signal[i].done),
              static_cast<bool>(fb_gear_out_signal[i].busy),
              static_cast<bool>(fb_gear_out_signal[i].error));
      fprintf(fptr, "%f,%f,%d\n", master_vel_ptr[i], slave_vel_ptr[i],
              slave_axis_state_ptr[i]);
    }
    fclose(fptr);
  }

  /* Post processing */
  pthread_join(cyclic_thread, nullptr);
  motion_servo_master_release(master);
  delete my_servo_1;
  delete my_servo_2;
  delete axis_1;
  delete axis_2;
  free(fb_gear_in_signal);
  free(fb_gear_out_signal);
  free(master_vel_ptr);
  free(slave_vel_ptr);
  printf("End of Program\n");
  return 0;
}