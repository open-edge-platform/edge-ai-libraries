// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

#include <fb/common/include/axis.hpp>
#include <fb/public/include/fb_move_velocity.hpp>
#include <fb/public/include/fb_power.hpp>
#include <fb/public/include/fb_read_actual_position.hpp>
#include <fb/public/include/fb_read_actual_velocity.hpp>
#include <fb/public/include/fb_read_actual_acceleration.hpp>
#include <fb/public/include/fb_read_command_position.hpp>
#include <fb/public/include/fb_read_command_velocity.hpp>
#include <fb/public/include/fb_read_command_acceleration.hpp>
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

static EcrtServo* my_servo;

// Thread related
static pthread_t cyclic_thread;
static volatile mcINT run = 1;
static mcUINT cycle_us    = 1000;

// Ethercat related
static servo_master* master = nullptr;
static mcUSINT* domain1;
void* domain;

// Command line arguments
static char* eni_file  = nullptr;
static mcBOOL verbose  = mcFALSE;
static mcBOOL log_flag = mcFALSE;
static mcULINT ratio   = PER_CIRCLE_ENCODER;

// RTmotion related
using namespace RTmotion;
static AXIS_REF axis;
static FbPower fb_power;
static FbMoveVelocity fb_move;
static FbReadActualPosition fb_read_pos;
static FbReadActualVelocity fb_read_vel;
static FbReadActualAcceleration fb_read_acc;
static FbReadCommandPosition fb_read_cmd_pos;
static FbReadCommandVelocity fb_read_cmd_vel;
static FbReadCommandAcceleration fb_read_cmd_acc;

// log data
static char column_string[] = "FbMoveVelocity.Execute,\
              FbMoveVelocity.InVelocity,\
              FbMoveVelocity.Active,\
              FbMoveVelocity.Busy,\
              FbMoveVelocity.Error,\
              FbReadActualPosition.Enable,\
              FbReadActualPosition.Valid,\
              FbReadActualPosition.Busy,\
              FbReadActualPosition.Error,\
              FbReadActualPosition.Value,\
              FbReadActualVelocity.Enable,\
              FbReadActualVelocity.Valid,\
              FbReadActualVelocity.Busy,\
              FbReadActualVelocity.Error,\
              FbReadActualVelocity.Value,\
              FbReadActualAcceleration.Enable,\
              FbReadActualAcceleration.Valid,\
              FbReadActualAcceleration.Busy,\
              FbReadActualAcceleration.Error,\
              FbReadActualAcceleration.Value,\
              FbReadCommandPosition.Enable,\
              FbReadCommandPosition.Valid,\
              FbReadCommandPosition.Busy,\
              FbReadCommandPosition.Error,\
              FbReadCommandPosition.Value,\
              FbReadCommandVelocity.Enable,\
              FbReadCommandVelocity.Valid,\
              FbReadCommandVelocity.Busy,\
              FbReadCommandVelocity.Error,\
              FbReadCommandVelocity.Value,\
              FbReadCommandAcceleration.Enable,\
              FbReadCommandAcceleration.Valid,\
              FbReadCommandAcceleration.Busy,\
              FbReadCommandAcceleration.Error,\
              FbReadCommandAcceleration.Value";
static char log_file_name[] = "solo_mc_move_velocity_test_results.csv";
static FILE* log_fptr       = nullptr;
typedef struct
{
  mcBOOL execute;
  mcBOOL in_velocity;
  mcBOOL active;
  mcBOOL busy;
  mcBOOL error;
} fb_move_signal;
typedef struct
{
  mcBOOL enable;
  mcBOOL valid;
  mcBOOL busy;
  mcBOOL error;
  mcREAL value;
} fb_read_signal;
static fb_move_signal* fb_move_vel_signal     = nullptr;
static fb_read_signal* fb_read_pos_signal     = nullptr;
static fb_read_signal* fb_read_vel_signal     = nullptr;
static fb_read_signal* fb_read_acc_signal     = nullptr;
static fb_read_signal* fb_read_cmd_pos_signal = nullptr;
static fb_read_signal* fb_read_cmd_vel_signal = nullptr;
static fb_read_signal* fb_read_cmd_acc_signal = nullptr;
mcBOOL fb_move_execute_state;
mcULINT record_cycle       = 30000;
mcULINT record_cycle_count = 0;

// RT thread function
void* my_thread(void* /*arg*/)
{
  struct timespec next_period, dc_period;
  mcBOOL powered_on  = mcFALSE;
  mcUINT cycle_count = 0;

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
    fb_move.runCycle();
    fb_read_pos.runCycle();
    fb_read_vel.runCycle();
    fb_read_acc.runCycle();
    fb_read_cmd_pos.runCycle();
    fb_read_cmd_vel.runCycle();
    fb_read_cmd_acc.runCycle();

    if (powered_on == mcFALSE && fb_power.getPowerStatus() == mcTRUE)
      printf("Axis is powered on. Continue to execute fb_move.\n");

    fb_move.setExecute(fb_power.getPowerStatus());
    powered_on = fb_move_execute_state = fb_power.getPowerStatus();

    if (cycle_count % 10000 == 0)
      fb_move.setVelocity(-fb_move.getVelocity());

    if (0 < cycle_count % 10000 && cycle_count % 10000 < 2000)
    {
      fb_move.setExecute(mcFALSE);
      fb_move_execute_state = mcFALSE;
    }

    if (cycle_count % 10000 == 2000)
      printf("fb_move is execute, Set velocity:%f,\tCurrent position: "
             "%f,\tCurrent velocity: %f \n",
             fb_move.getVelocity(), fb_read_pos.getFloatValue(),
             fb_read_vel.getFloatValue());

    if (cycle_count > 2000)
    {
      fb_read_pos.setEnable(mcTRUE);
      fb_read_vel.setEnable(mcTRUE);
      fb_read_acc.setEnable(mcTRUE);
      fb_read_cmd_pos.setEnable(mcTRUE);
      fb_read_cmd_vel.setEnable(mcTRUE);
      fb_read_cmd_acc.setEnable(mcTRUE);

      if (cycle_count > 25000 && cycle_count < 30000)
      {
        fb_read_pos.setEnable(mcFALSE);
        fb_read_vel.setEnable(mcFALSE);
        fb_read_acc.setEnable(mcFALSE);
        fb_read_cmd_pos.setEnable(mcFALSE);
        fb_read_cmd_vel.setEnable(mcFALSE);
        fb_read_cmd_acc.setEnable(mcFALSE);
        if (verbose == mcTRUE)
          printf("Disable test of FbReadActualVelocity and others\n");
      }
      else if (verbose == mcTRUE)
      {
        printf("Current position: %f,\tvelocity: %f\n",
               fb_read_pos.getFloatValue(), fb_read_vel.getFloatValue());
      }
    }

    clock_gettime(CLOCK_MONOTONIC, &dc_period);
    motion_servo_sync_dc(master->master, TIMESPEC2NS(dc_period));
    motion_servo_send_process(master->master, static_cast<uint8_t*>(domain));

    /* Write fb inputs and outputs to .cvs file*/
    if (log_flag == mcTRUE)
    {
      /* Save RT data to memory array */
      if (record_cycle_count < record_cycle)
      {
        /* IO signals of fb_move_velocity */
        fb_move_vel_signal[record_cycle_count].execute = fb_move_execute_state;
        fb_move_vel_signal[record_cycle_count].in_velocity =
            fb_move.isInVelocity();
        fb_move_vel_signal[record_cycle_count].active = fb_move.isActive();
        fb_move_vel_signal[record_cycle_count].busy   = fb_move.isBusy();
        fb_move_vel_signal[record_cycle_count].error  = fb_move.isError();
        /* IO signals of fb_read_actual_position */
        fb_read_pos_signal[record_cycle_count].enable = fb_read_pos.isEnabled();
        fb_read_pos_signal[record_cycle_count].valid  = fb_read_pos.isValid();
        fb_read_pos_signal[record_cycle_count].busy   = fb_read_pos.isBusy();
        fb_read_pos_signal[record_cycle_count].error  = fb_read_pos.isError();
        fb_read_pos_signal[record_cycle_count].value =
            fb_read_pos.getFloatValue();
        /* IO signals of fb_read_acutal_velocity */
        fb_read_vel_signal[record_cycle_count].enable = fb_read_vel.isEnabled();
        fb_read_vel_signal[record_cycle_count].valid  = fb_read_vel.isValid();
        fb_read_vel_signal[record_cycle_count].busy   = fb_read_vel.isBusy();
        fb_read_vel_signal[record_cycle_count].error  = fb_read_vel.isError();
        fb_read_vel_signal[record_cycle_count].value =
            fb_read_vel.getFloatValue();
        /* IO signals of fb_read_acutal_acceleration */
        fb_read_acc_signal[record_cycle_count].enable = fb_read_acc.isEnabled();
        fb_read_acc_signal[record_cycle_count].valid  = fb_read_acc.isValid();
        fb_read_acc_signal[record_cycle_count].busy   = fb_read_acc.isBusy();
        fb_read_acc_signal[record_cycle_count].error  = fb_read_acc.isError();
        fb_read_acc_signal[record_cycle_count].value =
            fb_read_acc.getFloatValue();
        /* IO signals of fb_read_command_position */
        fb_read_cmd_pos_signal[record_cycle_count].enable =
            fb_read_cmd_pos.isEnabled();
        fb_read_cmd_pos_signal[record_cycle_count].valid =
            fb_read_cmd_pos.isValid();
        fb_read_cmd_pos_signal[record_cycle_count].busy =
            fb_read_cmd_pos.isBusy();
        fb_read_cmd_pos_signal[record_cycle_count].error =
            fb_read_cmd_pos.isError();
        fb_read_cmd_pos_signal[record_cycle_count].value =
            fb_read_cmd_pos.getFloatValue();
        /* IO signals of fb_read_command_velocity */
        fb_read_cmd_vel_signal[record_cycle_count].enable =
            fb_read_cmd_vel.isEnabled();
        fb_read_cmd_vel_signal[record_cycle_count].valid =
            fb_read_cmd_vel.isValid();
        fb_read_cmd_vel_signal[record_cycle_count].busy =
            fb_read_cmd_vel.isBusy();
        fb_read_cmd_vel_signal[record_cycle_count].error =
            fb_read_cmd_vel.isError();
        fb_read_cmd_vel_signal[record_cycle_count].value =
            fb_read_cmd_vel.getFloatValue();
        /* IO signals of fb_read_command_acceleration */
        fb_read_cmd_acc_signal[record_cycle_count].enable =
            fb_read_cmd_acc.isEnabled();
        fb_read_cmd_acc_signal[record_cycle_count].valid =
            fb_read_cmd_acc.isValid();
        fb_read_cmd_acc_signal[record_cycle_count].busy =
            fb_read_cmd_acc.isBusy();
        fb_read_cmd_acc_signal[record_cycle_count].error =
            fb_read_cmd_acc.isError();
        fb_read_cmd_acc_signal[record_cycle_count].value =
            fb_read_cmd_acc.getFloatValue();
        record_cycle_count++;
      }
    }
    cycle_count++;
  }
  return nullptr;
}

static void getOptions(int argc, char** argv)
{
  int index;
  static struct option long_options[] = {
    // name		 has_arg				flag	val
    { "eni", required_argument, nullptr, 'n' },
    { "interval", required_argument, nullptr, 'i' },
    { "ratio", required_argument, nullptr, 'r' },
    { "verbose", no_argument, nullptr, 'v' },
    { "log", no_argument, nullptr, 'l' },
    { "help", no_argument, nullptr, 'h' },
    {}
  };
  do
  {
    index = getopt_long(argc, argv, "n:i:r:vlh", long_options, nullptr);
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
        printf("    --eni       -n  Specify ENI/XML file\n");
        printf("    --int       -i  Specify RT cycle time\n");
        printf("    --rat       -r  Specify encoder ratio\n");
        printf("    --ver       -v  Specify verbose print\n");
        printf("    --log       -l  Enable data log.\n");
        printf("    --help      -h  Show this help.\n");
        exit(0);
        break;
    }
  } while (index != -1);
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

  fb_move.setAxis(axis);
  fb_move.setVelocity(50);
  fb_move.setAcceleration(20);
  fb_move.setDeceleration(20);
  fb_move.setJerk(500);
  fb_move.setBufferMode(mcAborting);
  fb_move.setExecute(mcFALSE);
  fb_move_execute_state = mcFALSE;

  fb_read_pos.setAxis(axis);

  fb_read_vel.setAxis(axis);

  fb_read_acc.setAxis(axis);

  fb_read_cmd_pos.setAxis(axis);

  fb_read_cmd_vel.setAxis(axis);

  fb_read_cmd_acc.setAxis(axis);

  /* Create csv output */
  if (log_flag == mcTRUE)
  {
    fb_move_vel_signal =
        (fb_move_signal*)malloc(sizeof(fb_move_signal) * record_cycle);
    memset(fb_move_vel_signal, 0, sizeof(fb_move_signal) * record_cycle);
    fb_read_pos_signal =
        (fb_read_signal*)malloc(sizeof(fb_read_signal) * record_cycle);
    memset(fb_read_pos_signal, 0, sizeof(fb_read_signal) * record_cycle);
    fb_read_vel_signal =
        (fb_read_signal*)malloc(sizeof(fb_read_signal) * record_cycle);
    memset(fb_read_vel_signal, 0, sizeof(fb_read_signal) * record_cycle);
    fb_read_acc_signal =
        (fb_read_signal*)malloc(sizeof(fb_read_signal) * record_cycle);
    memset(fb_read_acc_signal, 0, sizeof(fb_read_signal) * record_cycle);
    fb_read_cmd_pos_signal =
        (fb_read_signal*)malloc(sizeof(fb_read_signal) * record_cycle);
    memset(fb_read_cmd_pos_signal, 0, sizeof(fb_read_signal) * record_cycle);
    fb_read_cmd_vel_signal =
        (fb_read_signal*)malloc(sizeof(fb_read_signal) * record_cycle);
    memset(fb_read_cmd_vel_signal, 0, sizeof(fb_read_signal) * record_cycle);
    fb_read_cmd_acc_signal =
        (fb_read_signal*)malloc(sizeof(fb_read_signal) * record_cycle);
    memset(fb_read_cmd_acc_signal, 0, sizeof(fb_read_signal) * record_cycle);
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
              static_cast<bool>(fb_move_vel_signal[i].execute),
              static_cast<bool>(fb_move_vel_signal[i].in_velocity),
              static_cast<bool>(fb_move_vel_signal[i].active),
              static_cast<bool>(fb_move_vel_signal[i].busy),
              static_cast<bool>(fb_move_vel_signal[i].error));
      fprintf(fptr, "%d,%d,%d,%d,%f,",
              static_cast<bool>(fb_read_pos_signal[i].enable),
              static_cast<bool>(fb_read_pos_signal[i].valid),
              static_cast<bool>(fb_read_pos_signal[i].busy),
              static_cast<bool>(fb_read_pos_signal[i].error),
              fb_read_pos_signal[i].value);
      fprintf(fptr, "%d,%d,%d,%d,%f,",
              static_cast<bool>(fb_read_vel_signal[i].enable),
              static_cast<bool>(fb_read_vel_signal[i].valid),
              static_cast<bool>(fb_read_vel_signal[i].busy),
              static_cast<bool>(fb_read_vel_signal[i].error),
              fb_read_vel_signal[i].value);
      fprintf(fptr, "%d,%d,%d,%d,%f,",
              static_cast<bool>(fb_read_acc_signal[i].enable),
              static_cast<bool>(fb_read_acc_signal[i].valid),
              static_cast<bool>(fb_read_acc_signal[i].busy),
              static_cast<bool>(fb_read_acc_signal[i].error),
              fb_read_acc_signal[i].value);
      fprintf(fptr, "%d,%d,%d,%d,%f,",
              static_cast<bool>(fb_read_cmd_pos_signal[i].enable),
              static_cast<bool>(fb_read_cmd_pos_signal[i].valid),
              static_cast<bool>(fb_read_cmd_pos_signal[i].busy),
              static_cast<bool>(fb_read_cmd_pos_signal[i].error),
              fb_read_cmd_pos_signal[i].value);
      fprintf(fptr, "%d,%d,%d,%d,%f,",
              static_cast<bool>(fb_read_cmd_vel_signal[i].enable),
              static_cast<bool>(fb_read_cmd_vel_signal[i].valid),
              static_cast<bool>(fb_read_cmd_vel_signal[i].busy),
              static_cast<bool>(fb_read_cmd_vel_signal[i].error),
              fb_read_cmd_vel_signal[i].value);
      fprintf(fptr, "%d,%d,%d,%d,%f\n",
              static_cast<bool>(fb_read_cmd_acc_signal[i].enable),
              static_cast<bool>(fb_read_cmd_acc_signal[i].valid),
              static_cast<bool>(fb_read_cmd_acc_signal[i].busy),
              static_cast<bool>(fb_read_cmd_acc_signal[i].error),
              fb_read_cmd_acc_signal[i].value);
    }
    fclose(fptr);
  }

  /* Post processing */
  pthread_join(cyclic_thread, nullptr);
  motion_servo_master_release(master);
  delete my_servo;
  delete axis;
  free(fb_move_vel_signal);
  free(fb_read_pos_signal);
  free(fb_read_vel_signal);
  free(fb_read_acc_signal);
  free(fb_read_cmd_pos_signal);
  free(fb_read_cmd_vel_signal);
  free(fb_read_cmd_acc_signal);
  printf("End of Program\n");
  return 0;
}
