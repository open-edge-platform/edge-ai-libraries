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
#include <unistd.h>
#include <fstream>
#include <getopt.h>
#include <motionentry.h>
#include <ecrt_config.hpp>
#include <ecrt_servo.hpp>
#include <fb/common/include/axis.hpp>
#include <fb/common/include/global.hpp>
#include <fb/public/include/fb_power.hpp>
#include <fb/public/include/fb_move_velocity.hpp>
#include <fb/public/include/fb_halt.hpp>
#include <fb/private/include/fb_cam_in.hpp>
#include <fb/private/include/fb_cam_out.hpp>
#include <fb/private/include/fb_cam_ref.hpp>
#include <fb/private/include/fb_cam_table_select.hpp>
#include <fb/public/include/fb_read_actual_position.hpp>
#include <fb/public/include/fb_read_actual_velocity.hpp>

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
static char* eni_file  = nullptr;
static mcBOOL verbose  = mcFALSE;
static mcBOOL log_flag = mcFALSE;
static mcULINT ratio   = PER_CIRCLE_ENCODER;

using namespace RTmotion;

static AXIS_REF axis_1;
static AXIS_REF axis_2;
static FbPower fb_power_1;
static FbPower fb_power_2;
static FbMoveVelocity fb_move_vel;
static FbHalt fb_halt;
static FbCamTableSelect fb_cam_table_select;
static FbCamRef fb_cam_ref;
static FbCamIn fb_cam_in;
static FbCamOut fb_cam_out;
static FbReadActualPosition fb_read_pos_1;
static FbReadActualPosition fb_read_pos_2;
static FbReadActualVelocity fb_read_vel_1;
static FbReadActualVelocity fb_read_vel_2;

// log data
static char column_string[] = "FbCamTableSelect.Execute,\
              FbCamTableSelect.Done,\
              FbCamTableSelect.Busy,\
              FbCamTableSelect.Error,\
              FbCamIn.Execute,\
              FbCamIn.InSync,\
              FbCamIn.Busy,\
              FbCamIn.Active,\
              FbCamIn.Error,\
              FbCamOut.Execute,\
              FbCamOut.Done,\
              FbCamOut.Busy,\
              FbCamOut.Error,\
              master_vel,\
              master_pos,\
              slave_vel,\
              slave_pos,\
              slave_axis_state,\
              slave_cmd_pos,\
              slave_cmd_vel";
static char log_file_name[] = "duo_rtmotion_cam_demo_test_results.csv";
static FILE* log_fptr       = nullptr;
typedef struct
{
  mcBOOL execute;
  mcBOOL in_sync;
  mcBOOL active;
  mcBOOL done;
  mcBOOL busy;
  mcBOOL error;
} fb_cam_signal;
typedef struct
{
  mcREAL vel;
  mcREAL pos;
} axis_obj;
static fb_cam_signal* fb_cam_table_select_signal = nullptr;
static fb_cam_signal* fb_cam_in_signal           = nullptr;
static fb_cam_signal* fb_cam_out_signal          = nullptr;
static axis_obj* master_signal                   = nullptr;
static axis_obj* slave_signal                    = nullptr;
static mcUSINT* slave_axis_state_signal          = nullptr;
static mcREAL* slave_cmd_pos_signal              = nullptr;
static mcREAL* slave_cmd_vel_signal              = nullptr;
mcBOOL fb_cam_table_select_execute_state;
mcBOOL fb_cam_in_execute_state;
mcBOOL fb_cam_out_execute_state;
mcULINT record_cycle       = 40000;
mcULINT record_cycle_count = 0;

// Cycle function
void* my_thread(void* /*arg*/)
{
  struct timespec next_period, dc_period;
  mcLINT cycle             = 0;
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
    fb_halt.runCycle();
    fb_cam_table_select.runCycle();
    fb_cam_in.runCycle();
    fb_cam_out.runCycle();
    fb_read_pos_1.runCycle();
    fb_read_pos_2.runCycle();
    fb_read_vel_1.runCycle();
    fb_read_vel_2.runCycle();

    if (fb_power_1.getPowerStatus() == mcTRUE &&
        fb_power_2.getPowerStatus() == mcTRUE && cycle > 1000)
    {
      fb_move_vel.setExecute(mcTRUE);
      fb_cam_table_select.setEnable(mcTRUE);
      fb_cam_table_select_execute_state = mcTRUE;
      fb_cam_in.setExecute(mcTRUE);
      fb_cam_in_execute_state = mcTRUE;
    }

    // reset master velocity from 0
    if (cycle == 25000)
    {
      fb_move_vel.setVelocity(-0.2);
      fb_move_vel.setExecute(mcFALSE);
      fb_halt.setExecute(mcFALSE);
    }
    // set master velocity to 0
    if (cycle == 20000)
    {
      fb_halt.setExecute(mcTRUE);
    }
    else if (cycle % 10000 == 0)  // periodic change velocity
    {
      fb_move_vel.setVelocity(-fb_move_vel.getVelocity());
      fb_move_vel.setExecute(mcFALSE);
    }
    // MC_CamIn falling edge
    if (cycle > 15000 && cycle < 18000)
    {
      fb_cam_in.setExecute(mcFALSE);
      fb_cam_in_execute_state = mcFALSE;
    }
    // execute MC_CamOut
    if (cycle == 30000)
    {
      fb_cam_out.setExecute(mcTRUE);
      fb_cam_out_execute_state = mcTRUE;
    }
    // MC_CamOut falling edge
    if (cycle == 35000)
    {
      fb_cam_out.setExecute(mcFALSE);
      fb_cam_out_execute_state = mcFALSE;
    }

    if (verbose == mcTRUE)
    {
      printf("Cycle: %ld\tMaster pos: %f, vel: %f\tSlave pos: %f, vel:%f, "
             "cmd_pos: %f, "
             "cmd_vel:%f\n",
             cycle, fb_read_pos_1.getFloatValue(),
             fb_read_vel_1.getFloatValue(), fb_read_pos_2.getFloatValue(),
             fb_read_vel_2.getFloatValue(), axis_2->toUserPosCmd(),
             axis_2->toUserVelCmd());
    }

    /* Write fb inputs and outputs to .cvs file*/
    if (log_flag == mcTRUE)
    {
      /* Save RT data to memory array */
      if (record_cycle_count < record_cycle)
      {
        /* IO signals of fb_move_velocity */
        fb_cam_table_select_signal[record_cycle_count].execute =
            fb_cam_table_select_execute_state;
        fb_cam_table_select_signal[record_cycle_count].done =
            fb_cam_table_select.isDone();
        fb_cam_table_select_signal[record_cycle_count].busy =
            fb_cam_table_select.isBusy();
        fb_cam_table_select_signal[record_cycle_count].error =
            fb_cam_table_select.isError();
        fb_cam_in_signal[record_cycle_count].execute = fb_cam_in_execute_state;
        fb_cam_in_signal[record_cycle_count].in_sync = fb_cam_in.getInSync();
        fb_cam_in_signal[record_cycle_count].active  = fb_cam_in.isActive();
        fb_cam_in_signal[record_cycle_count].busy    = fb_cam_in.isBusy();
        fb_cam_in_signal[record_cycle_count].error   = fb_cam_in.isError();
        fb_cam_out_signal[record_cycle_count].execute =
            fb_cam_out_execute_state;
        fb_cam_out_signal[record_cycle_count].done  = fb_cam_out.isDone();
        fb_cam_out_signal[record_cycle_count].busy  = fb_cam_out.isBusy();
        fb_cam_out_signal[record_cycle_count].error = fb_cam_out.isError();
        master_signal[record_cycle_count].vel = fb_read_vel_1.getFloatValue();
        master_signal[record_cycle_count].pos = fb_read_pos_1.getFloatValue();
        slave_signal[record_cycle_count].vel  = fb_read_vel_2.getFloatValue();
        slave_signal[record_cycle_count].pos  = fb_read_pos_2.getFloatValue();
        slave_axis_state_signal[record_cycle_count] = axis_2->getAxisState();
        slave_cmd_pos_signal[record_cycle_count]    = axis_2->toUserPosCmd();
        slave_cmd_vel_signal[record_cycle_count]    = axis_2->toUserVelCmd();
        record_cycle_count++;
      }
    }
    cycle++;

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
    // name		 has_arg				flag	val
    { "eni", required_argument, nullptr, 'n' },
    { "interval", required_argument, nullptr, 'i' },
    { "log", no_argument, nullptr, 'l' },
    { "ratio", required_argument, nullptr, 'r' },
    { "verbose", no_argument, nullptr, 'v' },
    { "help", no_argument, nullptr, 'h' },
    {}
  };
  do
  {
    index = getopt_long(argc, argv, "n:i:h:r:lvh", long_options, nullptr);
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
      case 'l':
        log_flag = mcTRUE;
        printf("log: record fb signals in a csv file.\n");
        break;
      case 'v':
        verbose = mcTRUE;
        printf("verbose: print pos and vel values.\n");
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
    printf("fail to activate master\n");
    return -1;
  }

  domain1 = motion_servo_domain_data(domain);
  if (!domain1)
  {
    printf("fail to get domain data\n");
    return 0;
  }

  /* Create motion servo */
  my_servo_1 = new EcrtServo();
  my_servo_2 = new EcrtServo();
  my_servo_1->setMaster(master);
  my_servo_2->setMaster(master);
  my_servo_1->setDomain(domain1);
  my_servo_2->setDomain(domain1);
  my_servo_1->initialize(0, 0);
  my_servo_2->initialize(0, 1);
  Servo* servo_1 = (Servo*)my_servo_1;
  Servo* servo_2 = (Servo*)my_servo_2;

  AxisConfig config_1;
  config_1.encoder_count_per_unit_ = ratio;
  config_1.frequency_              = 1.0 / cycle_us * 1000000;
  AxisConfig config_2;
  config_2.encoder_count_per_unit_ = ratio;
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
  fb_move_vel.setVelocity(-0.2);
  fb_move_vel.setAcceleration(10);
  fb_move_vel.setDeceleration(10);
  fb_move_vel.setJerk(500);
  fb_move_vel.setBufferMode(mcAborting);
  fb_move_vel.setExecute(mcFALSE);

  fb_halt.setAxis(axis_1);
  fb_halt.setAcceleration(1);
  fb_halt.setDeceleration(1);
  fb_halt.setJerk(500);
  fb_halt.setBufferMode(mcAborting);
  fb_halt.setExecute(mcFALSE);

  static McCamXYVA cam_table[361] = { { 0, 0, NAN, NAN, polyFive },
                                      { 0.0028, -0.01271, NAN, NAN, polyFive },
                                      { 0.0056, -0.03337, NAN, NAN, polyFive },
                                      { 0.0083, -0.03353, NAN, NAN, polyFive },
                                      { 0.0111, -0.04147, NAN, NAN, polyFive },
                                      { 0.0139, -0.05724, NAN, NAN, polyFive },
                                      { 0.0167, -0.08087, NAN, NAN, polyFive },
                                      { 0.0194, -0.11235, NAN, NAN, polyFive },
                                      { 0.0222, -0.15168, NAN, NAN, polyFive },
                                      { 0.025, -0.16943, NAN, NAN, polyFive },
                                      { 0.0278, -0.19465, NAN, NAN, polyFive },
                                      { 0.0306, -0.22729, NAN, NAN, polyFive },
                                      { 0.0333, -0.26724, NAN, NAN, polyFive },
                                      { 0.0361, -0.31439, NAN, NAN, polyFive },
                                      { 0.0389, -0.3385, NAN, NAN, polyFive },
                                      { 0.0417, -0.39948, NAN, NAN, polyFive },
                                      { 0.0444, -0.43682, NAN, NAN, polyFive },
                                      { 0.0472, -0.48041, NAN, NAN, polyFive },
                                      { 0.05, -0.53003, NAN, NAN, polyFive },
                                      { 0.0528, -0.58544, NAN, NAN, polyFive },
                                      { 0.0556, -0.6155, NAN, NAN, polyFive },
                                      { 0.0583, -0.68154, NAN, NAN, polyFive },
                                      { 0.0611, -0.72141, NAN, NAN, polyFive },
                                      { 0.0639, -0.79684, NAN, NAN, polyFive },
                                      { 0.0667, -0.84523, NAN, NAN, polyFive },
                                      { 0.0694, -0.89729, NAN, NAN, polyFive },
                                      { 0.0722, -0.95266, NAN, NAN, polyFive },
                                      { 0.075, -1.01096, NAN, NAN, polyFive },
                                      { 0.0778, -1.07179, NAN, NAN, polyFive },
                                      { 0.0806, -1.13474, NAN, NAN, polyFive },
                                      { 0.0833, -1.19939, NAN, NAN, polyFive },
                                      { 0.0861, -1.26533, NAN, NAN, polyFive },
                                      { 0.0889, -1.33213, NAN, NAN, polyFive },
                                      { 0.0917, -1.39936, NAN, NAN, polyFive },
                                      { 0.0944, -1.4666, NAN, NAN, polyFive },
                                      { 0.0972, -1.53341, NAN, NAN, polyFive },
                                      { 0.1, -1.59939, NAN, NAN, polyFive },
                                      { 0.1028, -1.66411, NAN, NAN, polyFive },
                                      { 0.1056, -1.72718, NAN, NAN, polyFive },
                                      { 0.1083, -1.8202, NAN, NAN, polyFive },
                                      { 0.1111, -1.87879, NAN, NAN, polyFive },
                                      { 0.1139, -1.93457, NAN, NAN, polyFive },
                                      { 0.1167, -2.01916, NAN, NAN, polyFive },
                                      { 0.1194, -2.06828, NAN, NAN, polyFive },
                                      { 0.1222, -2.14548, NAN, NAN, polyFive },
                                      { 0.125, -2.2185, NAN, NAN, polyFive },
                                      { 0.1278, -2.28703, NAN, NAN, polyFive },
                                      { 0.1306, -2.35081, NAN, NAN, polyFive },
                                      { 0.1333, -2.40958, NAN, NAN, polyFive },
                                      { 0.1361, -2.4631, NAN, NAN, polyFive },
                                      { 0.1389, -2.54273, NAN, NAN, polyFive },
                                      { 0.1417, -2.58507, NAN, NAN, polyFive },
                                      { 0.1444, -2.65302, NAN, NAN, polyFive },
                                      { 0.1472, -2.71483, NAN, NAN, polyFive },
                                      { 0.15, -2.77037, NAN, NAN, polyFive },
                                      { 0.1528, -2.81951, NAN, NAN, polyFive },
                                      { 0.1556, -2.89322, NAN, NAN, polyFive },
                                      { 0.1583, -2.92919, NAN, NAN, polyFive },
                                      { 0.1611, -2.98938, NAN, NAN, polyFive },
                                      { 0.1639, -3.04267, NAN, NAN, polyFive },
                                      { 0.1667, -3.08902, NAN, NAN, polyFive },
                                      { 0.1694, -3.12841, NAN, NAN, polyFive },
                                      { 0.1722, -3.19126, NAN, NAN, polyFive },
                                      { 0.175, -3.21661, NAN, NAN, polyFive },
                                      { 0.1778, -3.26522, NAN, NAN, polyFive },
                                      { 0.1806, -3.30669, NAN, NAN, polyFive },
                                      { 0.1833, -3.34104, NAN, NAN, polyFive },
                                      { 0.1861, -3.39819, NAN, NAN, polyFive },
                                      { 0.1889, -3.41838, NAN, NAN, polyFive },
                                      { 0.1917, -3.46125, NAN, NAN, polyFive },
                                      { 0.1944, -3.49702, NAN, NAN, polyFive },
                                      { 0.1972, -3.5258, NAN, NAN, polyFive },
                                      { 0.2, -3.54765, NAN, NAN, polyFive },
                                      { 0.2028, -3.5627, NAN, NAN, polyFive },
                                      { 0.2056, -3.59999, NAN, NAN, polyFive },
                                      { 0.2083, -3.63044, NAN, NAN, polyFive },
                                      { 0.2111, -3.65415, NAN, NAN, polyFive },
                                      { 0.2139, -3.67124, NAN, NAN, polyFive },
                                      { 0.2167, -3.68185, NAN, NAN, polyFive },
                                      { 0.2194, -3.68609, NAN, NAN, polyFive },
                                      { 0.2222, -3.68408, NAN, NAN, polyFive },
                                      { 0.225, -3.70406, NAN, NAN, polyFive },
                                      { 0.2278, -3.71782, NAN, NAN, polyFive },
                                      { 0.2306, -3.7255, NAN, NAN, polyFive },
                                      { 0.2333, -3.72723, NAN, NAN, polyFive },
                                      { 0.2361, -3.72317, NAN, NAN, polyFive },
                                      { 0.2389, -3.71343, NAN, NAN, polyFive },
                                      { 0.2417, -3.72555, NAN, NAN, polyFive },
                                      { 0.2444, -3.7048, NAN, NAN, polyFive },
                                      { 0.2472, -3.70596, NAN, NAN, polyFive },
                                      { 0.25, -3.7018, NAN, NAN, polyFive },
                                      { 0.2528, -3.69246, NAN, NAN, polyFive },
                                      { 0.2556, -3.67809, NAN, NAN, polyFive },
                                      { 0.2583, -3.65883, NAN, NAN, polyFive },
                                      { 0.2611, -3.63483, NAN, NAN, polyFive },
                                      { 0.2639, -3.60623, NAN, NAN, polyFive },
                                      { 0.2667, -3.59959, NAN, NAN, polyFive },
                                      { 0.2694, -3.56212, NAN, NAN, polyFive },
                                      { 0.2722, -3.54669, NAN, NAN, polyFive },
                                      { 0.275, -3.52706, NAN, NAN, polyFive },
                                      { 0.2778, -3.4773, NAN, NAN, polyFive },
                                      { 0.2806, -3.44975, NAN, NAN, polyFive },
                                      { 0.2833, -3.41841, NAN, NAN, polyFive },
                                      { 0.2861, -3.38342, NAN, NAN, polyFive },
                                      { 0.2889, -3.34494, NAN, NAN, polyFive },
                                      { 0.2917, -3.30309, NAN, NAN, polyFive },
                                      { 0.2944, -3.28357, NAN, NAN, polyFive },
                                      { 0.2972, -3.23536, NAN, NAN, polyFive },
                                      { 0.3, -3.18421, NAN, NAN, polyFive },
                                      { 0.3028, -3.1556, NAN, NAN, polyFive },
                                      { 0.3056, -3.09894, NAN, NAN, polyFive },
                                      { 0.3083, -3.06496, NAN, NAN, polyFive },
                                      { 0.3111, -3.00335, NAN, NAN, polyFive },
                                      { 0.3139, -2.96458, NAN, NAN, polyFive },
                                      { 0.3167, -2.89857, NAN, NAN, polyFive },
                                      { 0.3194, -2.85559, NAN, NAN, polyFive },
                                      { 0.3222, -2.81068, NAN, NAN, polyFive },
                                      { 0.325, -2.73912, NAN, NAN, polyFive },
                                      { 0.3278, -2.69086, NAN, NAN, polyFive },
                                      { 0.3306, -2.64111, NAN, NAN, polyFive },
                                      { 0.3333, -2.56528, NAN, NAN, polyFive },
                                      { 0.3361, -2.51304, NAN, NAN, polyFive },
                                      { 0.3389, -2.45975, NAN, NAN, polyFive },
                                      { 0.3417, -2.40557, NAN, NAN, polyFive },
                                      { 0.3444, -2.35064, NAN, NAN, polyFive },
                                      { 0.3472, -2.27052, NAN, NAN, polyFive },
                                      { 0.35, -2.21456, NAN, NAN, polyFive },
                                      { 0.3528, -2.15831, NAN, NAN, polyFive },
                                      { 0.3556, -2.10192, NAN, NAN, polyFive },
                                      { 0.3583, -2.021, NAN, NAN, polyFive },
                                      { 0.3611, -1.96479, NAN, NAN, polyFive },
                                      { 0.3639, -1.9089, NAN, NAN, polyFive },
                                      { 0.3667, -1.82898, NAN, NAN, polyFive },
                                      { 0.3694, -1.77419, NAN, NAN, polyFive },
                                      { 0.3722, -1.7202, NAN, NAN, polyFive },
                                      { 0.375, -1.64267, NAN, NAN, polyFive },
                                      { 0.3778, -1.59075, NAN, NAN, polyFive },
                                      { 0.3806, -1.51559, NAN, NAN, polyFive },
                                      { 0.3833, -1.46639, NAN, NAN, polyFive },
                                      { 0.3861, -1.39426, NAN, NAN, polyFive },
                                      { 0.3889, -1.34845, NAN, NAN, polyFive },
                                      { 0.3917, -1.28001, NAN, NAN, polyFive },
                                      { 0.3944, -1.21365, NAN, NAN, polyFive },
                                      { 0.3972, -1.14955, NAN, NAN, polyFive },
                                      { 0.4, -1.08789, NAN, NAN, polyFive },
                                      { 0.4028, -1.02882, NAN, NAN, polyFive },
                                      { 0.4056, -0.97253, NAN, NAN, polyFive },
                                      { 0.4083, -0.9192, NAN, NAN, polyFive },
                                      { 0.4111, -0.86902, NAN, NAN, polyFive },
                                      { 0.4139, -0.82216, NAN, NAN, polyFive },
                                      { 0.4167, -0.75384, NAN, NAN, polyFive },
                                      { 0.4194, -0.71413, NAN, NAN, polyFive },
                                      { 0.4222, -0.65323, NAN, NAN, polyFive },
                                      { 0.425, -0.59628, NAN, NAN, polyFive },
                                      { 0.4278, -0.56869, NAN, NAN, polyFive },
                                      { 0.4306, -0.52027, NAN, NAN, polyFive },
                                      { 0.4333, -0.47639, NAN, NAN, polyFive },
                                      { 0.4361, -0.41178, NAN, NAN, polyFive },
                                      { 0.4389, -0.37745, NAN, NAN, polyFive },
                                      { 0.4417, -0.34822, NAN, NAN, polyFive },
                                      { 0.4444, -0.29859, NAN, NAN, polyFive },
                                      { 0.4472, -0.25429, NAN, NAN, polyFive },
                                      { 0.45, -0.24139, NAN, NAN, polyFive },
                                      { 0.4528, -0.20841, NAN, NAN, polyFive },
                                      { 0.4556, -0.15525, NAN, NAN, polyFive },
                                      { 0.4583, -0.13417, NAN, NAN, polyFive },
                                      { 0.4611, -0.11938, NAN, NAN, polyFive },
                                      { 0.4639, -0.08466, NAN, NAN, polyFive },
                                      { 0.4667, -0.05638, NAN, NAN, polyFive },
                                      { 0.4694, -0.03473, NAN, NAN, polyFive },
                                      { 0.4722, -0.0199, NAN, NAN, polyFive },
                                      { 0.475, -0.01206, NAN, NAN, polyFive },
                                      { 0.4778, -0.01137, NAN, NAN, polyFive },
                                      { 0.4806, 0.00912, NAN, NAN, polyFive },
                                      { 0.4833, 0.02236, NAN, NAN, polyFive },
                                      { 0.4861, 0.02821, NAN, NAN, polyFive },
                                      { 0.4889, 0.02653, NAN, NAN, polyFive },
                                      { 0.4917, 0.01716, NAN, NAN, polyFive },
                                      { 0.4944, 0.02779, NAN, NAN, polyFive },
                                      { 0.4972, 0.03076, NAN, NAN, polyFive },
                                      { 0.5, 0.02596, NAN, NAN, polyFive },
                                      { 0.5028, -0.01271, NAN, NAN, polyFive },
                                      { 0.5056, -0.03337, NAN, NAN, polyFive },
                                      { 0.5083, -0.03353, NAN, NAN, polyFive },
                                      { 0.5111, -0.04147, NAN, NAN, polyFive },
                                      { 0.5139, -0.05724, NAN, NAN, polyFive },
                                      { 0.5167, -0.08087, NAN, NAN, polyFive },
                                      { 0.5194, -0.11235, NAN, NAN, polyFive },
                                      { 0.5222, -0.15168, NAN, NAN, polyFive },
                                      { 0.525, -0.16943, NAN, NAN, polyFive },
                                      { 0.5278, -0.19465, NAN, NAN, polyFive },
                                      { 0.5306, -0.22729, NAN, NAN, polyFive },
                                      { 0.5333, -0.26724, NAN, NAN, polyFive },
                                      { 0.5361, -0.31439, NAN, NAN, polyFive },
                                      { 0.5389, -0.3385, NAN, NAN, polyFive },
                                      { 0.5417, -0.39948, NAN, NAN, polyFive },
                                      { 0.5444, -0.43682, NAN, NAN, polyFive },
                                      { 0.5472, -0.48041, NAN, NAN, polyFive },
                                      { 0.55, -0.53003, NAN, NAN, polyFive },
                                      { 0.5528, -0.58544, NAN, NAN, polyFive },
                                      { 0.5556, -0.6155, NAN, NAN, polyFive },
                                      { 0.5583, -0.68154, NAN, NAN, polyFive },
                                      { 0.5611, -0.72141, NAN, NAN, polyFive },
                                      { 0.5639, -0.79684, NAN, NAN, polyFive },
                                      { 0.5667, -0.84523, NAN, NAN, polyFive },
                                      { 0.5694, -0.89729, NAN, NAN, polyFive },
                                      { 0.5722, -0.95266, NAN, NAN, polyFive },
                                      { 0.575, -1.01096, NAN, NAN, polyFive },
                                      { 0.5778, -1.07179, NAN, NAN, polyFive },
                                      { 0.5806, -1.13474, NAN, NAN, polyFive },
                                      { 0.5833, -1.19939, NAN, NAN, polyFive },
                                      { 0.5861, -1.26533, NAN, NAN, polyFive },
                                      { 0.5889, -1.33213, NAN, NAN, polyFive },
                                      { 0.5917, -1.39936, NAN, NAN, polyFive },
                                      { 0.5944, -1.4666, NAN, NAN, polyFive },
                                      { 0.5972, -1.53341, NAN, NAN, polyFive },
                                      { 0.6, -1.59939, NAN, NAN, polyFive },
                                      { 0.6028, -1.66411, NAN, NAN, polyFive },
                                      { 0.6056, -1.72718, NAN, NAN, polyFive },
                                      { 0.6083, -1.8202, NAN, NAN, polyFive },
                                      { 0.6111, -1.87879, NAN, NAN, polyFive },
                                      { 0.6139, -1.93457, NAN, NAN, polyFive },
                                      { 0.6167, -2.01916, NAN, NAN, polyFive },
                                      { 0.6194, -2.06828, NAN, NAN, polyFive },
                                      { 0.6222, -2.14548, NAN, NAN, polyFive },
                                      { 0.625, -2.2185, NAN, NAN, polyFive },
                                      { 0.6278, -2.28703, NAN, NAN, polyFive },
                                      { 0.6306, -2.35081, NAN, NAN, polyFive },
                                      { 0.6333, -2.40958, NAN, NAN, polyFive },
                                      { 0.6361, -2.4631, NAN, NAN, polyFive },
                                      { 0.6389, -2.54273, NAN, NAN, polyFive },
                                      { 0.6417, -2.58507, NAN, NAN, polyFive },
                                      { 0.6444, -2.65302, NAN, NAN, polyFive },
                                      { 0.6472, -2.71483, NAN, NAN, polyFive },
                                      { 0.65, -2.77037, NAN, NAN, polyFive },
                                      { 0.6528, -2.81951, NAN, NAN, polyFive },
                                      { 0.6556, -2.89322, NAN, NAN, polyFive },
                                      { 0.6583, -2.92919, NAN, NAN, polyFive },
                                      { 0.6611, -2.98938, NAN, NAN, polyFive },
                                      { 0.6639, -3.04267, NAN, NAN, polyFive },
                                      { 0.6667, -3.08902, NAN, NAN, polyFive },
                                      { 0.6694, -3.12841, NAN, NAN, polyFive },
                                      { 0.6722, -3.19126, NAN, NAN, polyFive },
                                      { 0.675, -3.21661, NAN, NAN, polyFive },
                                      { 0.6778, -3.26522, NAN, NAN, polyFive },
                                      { 0.6806, -3.30669, NAN, NAN, polyFive },
                                      { 0.6833, -3.34104, NAN, NAN, polyFive },
                                      { 0.6861, -3.39819, NAN, NAN, polyFive },
                                      { 0.6889, -3.41838, NAN, NAN, polyFive },
                                      { 0.6917, -3.46125, NAN, NAN, polyFive },
                                      { 0.6944, -3.49702, NAN, NAN, polyFive },
                                      { 0.6972, -3.5258, NAN, NAN, polyFive },
                                      { 0.7, -3.54765, NAN, NAN, polyFive },
                                      { 0.7028, -3.5627, NAN, NAN, polyFive },
                                      { 0.7056, -3.59999, NAN, NAN, polyFive },
                                      { 0.7083, -3.63044, NAN, NAN, polyFive },
                                      { 0.7111, -3.65415, NAN, NAN, polyFive },
                                      { 0.7139, -3.67124, NAN, NAN, polyFive },
                                      { 0.7167, -3.68185, NAN, NAN, polyFive },
                                      { 0.7194, -3.68609, NAN, NAN, polyFive },
                                      { 0.7222, -3.68408, NAN, NAN, polyFive },
                                      { 0.725, -3.70406, NAN, NAN, polyFive },
                                      { 0.7278, -3.71782, NAN, NAN, polyFive },
                                      { 0.7306, -3.7255, NAN, NAN, polyFive },
                                      { 0.7333, -3.72723, NAN, NAN, polyFive },
                                      { 0.7361, -3.72317, NAN, NAN, polyFive },
                                      { 0.7389, -3.71343, NAN, NAN, polyFive },
                                      { 0.7417, -3.72555, NAN, NAN, polyFive },
                                      { 0.7444, -3.7048, NAN, NAN, polyFive },
                                      { 0.7472, -3.70596, NAN, NAN, polyFive },
                                      { 0.75, -3.7018, NAN, NAN, polyFive },
                                      { 0.7528, -3.69246, NAN, NAN, polyFive },
                                      { 0.7556, -3.67809, NAN, NAN, polyFive },
                                      { 0.7583, -3.65883, NAN, NAN, polyFive },
                                      { 0.7611, -3.63483, NAN, NAN, polyFive },
                                      { 0.7639, -3.60623, NAN, NAN, polyFive },
                                      { 0.7667, -3.59959, NAN, NAN, polyFive },
                                      { 0.7694, -3.56212, NAN, NAN, polyFive },
                                      { 0.7722, -3.54669, NAN, NAN, polyFive },
                                      { 0.775, -3.52706, NAN, NAN, polyFive },
                                      { 0.7778, -3.4773, NAN, NAN, polyFive },
                                      { 0.7806, -3.44975, NAN, NAN, polyFive },
                                      { 0.7833, -3.41841, NAN, NAN, polyFive },
                                      { 0.7861, -3.38342, NAN, NAN, polyFive },
                                      { 0.7889, -3.34494, NAN, NAN, polyFive },
                                      { 0.7917, -3.30309, NAN, NAN, polyFive },
                                      { 0.7944, -3.28357, NAN, NAN, polyFive },
                                      { 0.7972, -3.23536, NAN, NAN, polyFive },
                                      { 0.8, -3.18421, NAN, NAN, polyFive },
                                      { 0.8028, -3.1556, NAN, NAN, polyFive },
                                      { 0.8056, -3.09894, NAN, NAN, polyFive },
                                      { 0.8083, -3.06496, NAN, NAN, polyFive },
                                      { 0.8111, -3.00335, NAN, NAN, polyFive },
                                      { 0.8139, -2.96458, NAN, NAN, polyFive },
                                      { 0.8167, -2.89857, NAN, NAN, polyFive },
                                      { 0.8194, -2.85559, NAN, NAN, polyFive },
                                      { 0.8222, -2.81068, NAN, NAN, polyFive },
                                      { 0.825, -2.73912, NAN, NAN, polyFive },
                                      { 0.8278, -2.69086, NAN, NAN, polyFive },
                                      { 0.8306, -2.64111, NAN, NAN, polyFive },
                                      { 0.8333, -2.56528, NAN, NAN, polyFive },
                                      { 0.8361, -2.51304, NAN, NAN, polyFive },
                                      { 0.8389, -2.45975, NAN, NAN, polyFive },
                                      { 0.8417, -2.40557, NAN, NAN, polyFive },
                                      { 0.8444, -2.35064, NAN, NAN, polyFive },
                                      { 0.8472, -2.27052, NAN, NAN, polyFive },
                                      { 0.85, -2.21456, NAN, NAN, polyFive },
                                      { 0.8528, -2.15831, NAN, NAN, polyFive },
                                      { 0.8556, -2.10192, NAN, NAN, polyFive },
                                      { 0.8583, -2.021, NAN, NAN, polyFive },
                                      { 0.8611, -1.96479, NAN, NAN, polyFive },
                                      { 0.8639, -1.9089, NAN, NAN, polyFive },
                                      { 0.8667, -1.82898, NAN, NAN, polyFive },
                                      { 0.8694, -1.77419, NAN, NAN, polyFive },
                                      { 0.8722, -1.7202, NAN, NAN, polyFive },
                                      { 0.875, -1.64267, NAN, NAN, polyFive },
                                      { 0.8778, -1.59075, NAN, NAN, polyFive },
                                      { 0.8806, -1.51559, NAN, NAN, polyFive },
                                      { 0.8833, -1.46639, NAN, NAN, polyFive },
                                      { 0.8861, -1.39426, NAN, NAN, polyFive },
                                      { 0.8889, -1.34845, NAN, NAN, polyFive },
                                      { 0.8917, -1.28001, NAN, NAN, polyFive },
                                      { 0.8944, -1.21365, NAN, NAN, polyFive },
                                      { 0.8972, -1.14955, NAN, NAN, polyFive },
                                      { 0.9, -1.08789, NAN, NAN, polyFive },
                                      { 0.9028, -1.02882, NAN, NAN, polyFive },
                                      { 0.9056, -0.97253, NAN, NAN, polyFive },
                                      { 0.9083, -0.9192, NAN, NAN, polyFive },
                                      { 0.9111, -0.86902, NAN, NAN, polyFive },
                                      { 0.9139, -0.82216, NAN, NAN, polyFive },
                                      { 0.9167, -0.75384, NAN, NAN, polyFive },
                                      { 0.9194, -0.71413, NAN, NAN, polyFive },
                                      { 0.9222, -0.65323, NAN, NAN, polyFive },
                                      { 0.925, -0.59628, NAN, NAN, polyFive },
                                      { 0.9278, -0.56869, NAN, NAN, polyFive },
                                      { 0.9306, -0.52027, NAN, NAN, polyFive },
                                      { 0.9333, -0.47639, NAN, NAN, polyFive },
                                      { 0.9361, -0.41178, NAN, NAN, polyFive },
                                      { 0.9389, -0.37745, NAN, NAN, polyFive },
                                      { 0.9417, -0.34822, NAN, NAN, polyFive },
                                      { 0.9444, -0.29859, NAN, NAN, polyFive },
                                      { 0.9472, -0.25429, NAN, NAN, polyFive },
                                      { 0.95, -0.24139, NAN, NAN, polyFive },
                                      { 0.9528, -0.20841, NAN, NAN, polyFive },
                                      { 0.9556, -0.15525, NAN, NAN, polyFive },
                                      { 0.9583, -0.13417, NAN, NAN, polyFive },
                                      { 0.9611, -0.11938, NAN, NAN, polyFive },
                                      { 0.9639, -0.08466, NAN, NAN, polyFive },
                                      { 0.9667, -0.05638, NAN, NAN, polyFive },
                                      { 0.9694, -0.03473, NAN, NAN, polyFive },
                                      { 0.9722, -0.0199, NAN, NAN, polyFive },
                                      { 0.975, -0.01206, NAN, NAN, polyFive },
                                      { 0.9778, -0.01137, NAN, NAN, polyFive },
                                      { 0.9806, 0.00912, NAN, NAN, polyFive },
                                      { 0.9833, 0.02236, NAN, NAN, polyFive },
                                      { 0.9861, 0.02821, NAN, NAN, polyFive },
                                      { 0.9889, 0.02653, NAN, NAN, polyFive },
                                      { 0.9917, 0.01716, NAN, NAN, polyFive },
                                      { 0.9944, 0.02779, NAN, NAN, polyFive },
                                      { 0.9972, 0.03076, NAN, NAN, polyFive },
                                      { 1.0, 0.02596, NAN, NAN,
                                        noNextSegment } };

  fb_cam_ref.setType(xyva);
  fb_cam_ref.setElementNum(361);
  fb_cam_ref.setMasterRangeStart(0.0);
  fb_cam_ref.setMasterRangeEnd(1.0);
  fb_cam_ref.setElements((unsigned char*)cam_table);

  fb_cam_table_select.setMaster(axis_1);
  fb_cam_table_select.setSlave(axis_2);
  fb_cam_table_select.setCamTable(&fb_cam_ref);
  fb_cam_table_select.setMasterAbsolute(mcTRUE);
  fb_cam_table_select.setSlaveAbsolute(mcTRUE);
  fb_cam_table_select.setPeriodic(mcTRUE);
  fb_cam_table_select.setEnable(mcFALSE);
  fb_cam_table_select_execute_state = mcFALSE;

  fb_cam_in.setMaster(axis_1);
  fb_cam_in.setSlave(axis_2);
  fb_cam_in.setCamTableID(fb_cam_table_select.getCamTableID());
  fb_cam_in.setStartMode(mcAbsolute);
  fb_cam_in.setSlaveScaling(0.3);
  fb_cam_in.setPosThreshold(1.0);
  fb_cam_in.setVelThreshold(10);
  fb_cam_in.setVelocity(50);
  fb_cam_in.setAcceleration(250);
  fb_cam_in.setDeceleration(250);
  fb_cam_in.setExecute(mcFALSE);
  fb_cam_in_execute_state = mcFALSE;

  fb_cam_out.setSlave(axis_2);
  fb_cam_out.setExecute(mcFALSE);
  fb_cam_out_execute_state = mcFALSE;

  fb_read_pos_1.setAxis(axis_1);
  fb_read_pos_1.setEnable(mcTRUE);

  fb_read_vel_1.setAxis(axis_1);
  fb_read_vel_1.setEnable(mcTRUE);

  fb_read_pos_2.setAxis(axis_2);
  fb_read_pos_2.setEnable(mcTRUE);

  fb_read_vel_2.setAxis(axis_2);
  fb_read_vel_2.setEnable(mcTRUE);

  /* Create csv output */
  if (log_flag == mcTRUE)
  {
    fb_cam_table_select_signal =
        (fb_cam_signal*)malloc(sizeof(fb_cam_signal) * record_cycle);
    memset(fb_cam_table_select_signal, 0, sizeof(fb_cam_signal) * record_cycle);
    fb_cam_in_signal =
        (fb_cam_signal*)malloc(sizeof(fb_cam_signal) * record_cycle);
    memset(fb_cam_in_signal, 0, sizeof(fb_cam_signal) * record_cycle);
    fb_cam_out_signal =
        (fb_cam_signal*)malloc(sizeof(fb_cam_signal) * record_cycle);
    memset(fb_cam_out_signal, 0, sizeof(fb_cam_signal) * record_cycle);
    master_signal = (axis_obj*)malloc(sizeof(axis_obj) * record_cycle);
    memset(master_signal, 0, sizeof(axis_obj) * record_cycle);
    slave_signal = (axis_obj*)malloc(sizeof(axis_obj) * record_cycle);
    memset(slave_signal, 0, sizeof(axis_obj) * record_cycle);
    slave_axis_state_signal = (mcUSINT*)malloc(sizeof(mcUSINT) * record_cycle);
    memset(slave_axis_state_signal, 0, sizeof(mcUSINT) * record_cycle);
    slave_cmd_pos_signal = (mcREAL*)malloc(sizeof(mcREAL) * record_cycle);
    memset(slave_cmd_pos_signal, 0, sizeof(mcREAL) * record_cycle);
    slave_cmd_vel_signal = (mcREAL*)malloc(sizeof(mcREAL) * record_cycle);
    memset(slave_cmd_vel_signal, 0, sizeof(mcREAL) * record_cycle);
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
      fprintf(fptr, "%d,%d,%d,%d,",
              static_cast<bool>(fb_cam_table_select_signal[i].execute),
              static_cast<bool>(fb_cam_table_select_signal[i].done),
              static_cast<bool>(fb_cam_table_select_signal[i].busy),
              static_cast<bool>(fb_cam_table_select_signal[i].error));
      fprintf(fptr, "%d,%d,%d,%d,%d,",
              static_cast<bool>(fb_cam_in_signal[i].execute),
              static_cast<bool>(fb_cam_in_signal[i].in_sync),
              static_cast<bool>(fb_cam_in_signal[i].busy),
              static_cast<bool>(fb_cam_in_signal[i].active),
              static_cast<bool>(fb_cam_in_signal[i].error));
      fprintf(fptr, "%d,%d,%d,%d,",
              static_cast<bool>(fb_cam_out_signal[i].execute),
              static_cast<bool>(fb_cam_out_signal[i].done),
              static_cast<bool>(fb_cam_out_signal[i].busy),
              static_cast<bool>(fb_cam_out_signal[i].error));
      fprintf(fptr, "%f,%f,%f,%f,%d,%f,%f\n", master_signal[i].vel,
              master_signal[i].pos, slave_signal[i].vel, slave_signal[i].pos,
              slave_axis_state_signal[i], slave_cmd_pos_signal[i],
              slave_cmd_vel_signal[i]);
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
  free(fb_cam_table_select_signal);
  free(fb_cam_in_signal);
  free(fb_cam_out_signal);
  free(master_signal);
  free(slave_signal);
  free(slave_axis_state_signal);
  free(slave_cmd_pos_signal);
  free(slave_cmd_vel_signal);
  printf("End of Program\n");
  return 0;
}
