// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

#include <errno.h>
#include <getopt.h>
#include <limits.h>
#include <math.h>
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

#include <fb/common/include/axis.hpp>
#include <fb/public/include/fb_move_velocity.hpp>
#include <fb/public/include/fb_power.hpp>
#include <fb/public/include/fb_read_actual_position.hpp>
#include <fb/public/include/fb_read_actual_velocity.hpp>
#include <fb/common/include/global.hpp>
#include <symg_servo.hpp>

using namespace RTmotion;

// RTmotion related
static AXIS_REF axis;
static FbPower fbPower;
static FbMoveVelocity fbMoveVelocity;
static FbReadActualPosition readPos;
static FbReadActualVelocity readVel;

static pthread_t cyclic_thread;
static volatile int run = 1;

static EcrtServo* servo;

static Slave_Data ec_slave0;
static Ctrl_Data ec_motor0;

static int stop_motor = 0;

static ec_master_t* master = NULL;
static ec_domain_t* domain = NULL;
static uint8_t* domain_pd  = NULL;
static ec_slave_config_t* sc;

static void data_init(void)
{
  memset(&ec_slave0, 0, sizeof(Slave_Data));
  sc = NULL;
}

static void ec_readmotordata(Ctrl_Data* ec_motor, Slave_Data ec_slave)
{
  ec_motor->stat = EC_READ_S32(domain_pd + ec_slave.status);
  ec_motor->en1  = EC_READ_S32(domain_pd + ec_slave.enc1);
  ec_motor->en2  = EC_READ_S32(domain_pd + ec_slave.enc2);
  ec_motor->en3  = EC_READ_S32(domain_pd + ec_slave.enc3);
  ec_motor->en4  = EC_READ_S32(domain_pd + ec_slave.enc4);

  if ((ec_motor->stat >> 30 | 0x0) == 1)
  {
    printf("Please release the emergency button and try again\n");
    EC_WRITE_U32(domain_pd + ec_slave0.control, 0x100);
    run = 0;
  }
}

void* my_thread(void* /*arg*/)
{
  struct timespec next_period, dc_period;
  struct sched_param param = {};
  param.sched_priority     = 99;
  pthread_setschedparam(pthread_self(), SCHED_FIFO, &param);
  clock_gettime(CLOCK_MONOTONIC, &next_period);
  memset(&ec_motor0, 0, sizeof(Ctrl_Data));

  while (run != 0)
  {
    next_period.tv_nsec += CYCLE_US * 1000;
    while (next_period.tv_nsec >= NSEC_PER_SEC)
    {
      next_period.tv_nsec -= NSEC_PER_SEC;
      next_period.tv_sec++;
    }
    clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &next_period, NULL);
    ecrt_master_receive(master);
    ecrt_domain_process(domain);

    ec_readmotordata(&ec_motor0, ec_slave0);

    axis->runCycle();
    fbPower.runCycle();
    fbMoveVelocity.runCycle();
    readPos.runCycle();
    readVel.runCycle();

    printf("Current position: %f,\tvelocity: %f \n", readPos.getFloatValue(),
           readVel.getFloatValue());

    if (fbPower.getPowerStatus() && fbPower.getPowerStatusValid())
      fbMoveVelocity.setExecute(true);

    if (stop_motor == 1)
      servo->emergStop();

    clock_gettime(CLOCK_MONOTONIC, &dc_period);
    ecrt_master_application_time(master, TIMESPEC2NS(dc_period));
    ecrt_master_sync_reference_clock(master);
    ecrt_master_sync_slave_clocks(master);
    ecrt_domain_queue(domain);
    ecrt_master_send(master);
  }

  return NULL;
}

/****************************************************************************
 * Main function
 ***************************************************************************/
int main(int argc, char* argv[])
{
  struct timespec dc_period;
  auto signal_handler = [](int) {
    stop_motor = 1;
    sleep(1);
    run = 0;
  };
  data_init();
  signal(SIGTERM, signal_handler);
  signal(SIGINT, signal_handler);
  mlockall(MCL_CURRENT | MCL_FUTURE);

  printf("Requesting master...\n");
  master = ecrt_request_master(0);
  if (!master)
  {
    return -1;
  }

  printf("Creating domain ...\n");
  domain = ecrt_master_create_domain(master);
  if (!domain)
  {
    return -1;
  }

  // Create configuration for bus coupler
  sc = ecrt_master_slave_config(master, SLAVE00_POS, SLAVE00_ID);
  if (!sc)
  {
    printf("Slave1 sc is NULL \n");
    return -1;
  }

  printf("Creating slave configurations...\n");
  // ec_slave_config_init(sc);

  if (ecrt_slave_config_pdos(sc, EC_END, slave_syncs))
  {
    fprintf(stderr, "Failed to configure PDOs.  1 \n");
    return -1;
  }

  ecrt_master_set_send_interval(master, CYCLE_US);

  if (ecrt_domain_reg_pdo_entry_list(domain, domain_regs))
  {
    fprintf(stderr, "PDO entry registration failed!\n");
    return -1;
  }

  /*Configuring DC signal*/
  ecrt_slave_config_dc(sc, 0x0300, PERIOD_NS, PERIOD_NS / 2, 0, 0);
  clock_gettime(CLOCK_MONOTONIC, &dc_period);
  ecrt_master_application_time(master, TIMESPEC2NS(dc_period));

  int ret = ecrt_master_select_reference_clock(master, sc);
  if (ret < 0)
  {
    fprintf(stderr, "Failed to select reference clock: %s\n", strerror(-ret));
    return ret;
  }

  printf("Activating master...\n");
  if (ecrt_master_activate(master))
  {
    return -1;
  }

  if (!(domain_pd = ecrt_domain_data(domain)))
  {
    fprintf(stderr, "Failed to get domain data pointer.\n");
    return -1;
  }

  servo = new EcrtServo();
  servo->setDomain(domain_pd);
  servo->setId(LL);
  servo->setControlSlaveData(&ec_motor0, &ec_slave0);

  std::shared_ptr<Servo> servo_ptr;
  servo_ptr.reset(servo);

  AxisConfig config;
  config.mode                    = mcServoControlModePosition;
  config.encoder_count_per_unit_ = PER_CIRCLE_ENCODER;
  sched->setAxisConfig(axis, config);

  axis = std::make_shared<Axis>();
  axis->setAxisId(1);
  axis->setAxisName("X");
  axis->setAxisConfig(&config);
  axis->setServo(servo);

  fbPower.setAxis(axis);
  fbPower.setExecute(true);
  fbPower.setEnablePositive(true);
  fbPower.setEnableNegative(true);

  fbMoveVelocity.setAxis(axis);
  fbMoveVelocity.setVelocity(0.5);
  fbMoveVelocity.setAcceleration(2.0);
  fbMoveVelocity.setDeceleration(2.0);
  fbMoveVelocity.setJerk(500);
  fbMoveVelocity.setBufferMode(mcAborting);
  fbMoveVelocity.setExecute(false);

  readPos.setAxis(axis);
  readPos.setExecute(true);

  readVel.setAxis(axis);
  readVel.setExecute(true);

  /* Create cyclic RT-thread */
  pthread_attr_t thattr;
  pthread_attr_init(&thattr);
  pthread_attr_setdetachstate(&thattr, PTHREAD_CREATE_JOINABLE);

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
  ecrt_release_master(master);
  printf("End of Program\n");

  return 0;
}

/****************************************************************************/