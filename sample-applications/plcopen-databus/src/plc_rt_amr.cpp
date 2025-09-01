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
#include <math.h>

#include <shmringbuf.h>

#define CYCLE_US 1000
#define NSEC_PER_SEC (1000000000L)

static volatile int run = 1;
static pthread_t cyclic_thread;

/* Shm related data types
 * s_buf, handle_s: data sent from RT domain, AMR state info
 * c_buf, handle_c: data sent to RT domain, AMR commands
 */
#define MSG_LEN 512
static char s_buf[MSG_LEN];
static char c_buf[MSG_LEN];
static shm_handle_t handle_s, handle_c;

typedef struct
{
  uint8_t mEnable;
  uint8_t mEmergStop;
  float mTransH;
  float mTransV;
  float mTwist;
  uint8_t mRelMove;
  uint8_t mCancelRelMove;
  float mRelX;
  float mRelY;
  float mRelRZ;
}PLCShmCtrlType;

typedef struct
{
  float mPosX;
  float mPosY;
  float mPosRZ;
  float mVelX;
  float mVelY;
  float mVelRZ;
  uint8_t mError;
  uint8_t mRelMoveBusy;
}PLCShmAgvmInfoType;

static PLCShmCtrlType ctrl;
static PLCShmAgvmInfoType agvmInfo;

const double WheelVDistance = 0.483;
const double WheelHDistance = 0.371;
const double PLC_Period = 0.001;

/* Cartesian velocity to wheels velocity */
void agvmVelCartesian2Wheels(const double VelX, const double VelY, const double VelRZ,
                             double& UL, double& UR, double& LL, double& LR)
{
  double distance = WheelVDistance + WheelHDistance;
  double VelLZ = VelRZ * distance / 2.0;

  UL = VelX - VelY - VelLZ;
  UR = VelX + VelY + VelLZ;
  LL = VelX + VelY - VelLZ;
  LR = VelX - VelY + VelLZ;
}

/* Wheels velocity to cartesian velocity */
void agvmVelWheels2Cartesian(const double UL, const double UR, const double LL, const double LR, 
                             double& VelX, double& VelY, double& VelRZ)
{
  double distance = WheelVDistance + WheelHDistance;
  double DimX = UL + UR + LL + LR;
  double DimY = -UL + UR + LL - LR;
  double DimZ = -UL + UR - LL + LR;
  
  VelX = DimX / 4.0;
  VelY = DimY / 4.0;
  VelRZ= DimZ / 4.0 / distance * 2.0;
}

/* */
void agvm2DRotate(const double InX, const double InY, const double RZ, double& OutX, double& OutY)
{
  OutX = InX * cos(RZ) - InY * sin(RZ);
  OutY = InX * sin(RZ) + InY * cos(RZ);
}

void* my_thread(void* /*arg*/)
{
  double UL, UR, LL, LR;
  double SHM_PosX = 0.0, SHM_PosY = 0.0, SHM_PosRZ = 0.0;

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

    /* Get the AMR commands */
    if (!shm_blkbuf_empty(handle_c))
    {
      ret = shm_blkbuf_read(handle_c, c_buf, sizeof(c_buf));
      if (ret) {
        memcpy(&ctrl, c_buf, sizeof(ctrl));
        // printf("Receive command: %f, %f, %f\n",  ctrl.mTransV, ctrl.mTransH, ctrl.mTwist);
      }      
    }

    /* Compute wheels velocity */
    agvmVelCartesian2Wheels(ctrl.mTransV, ctrl.mTransH, ctrl.mTwist, UL, UR, LL, LR);
    // printf("Wheels velocity: %f, %f, %f, %f\n", UL, UR, LL, LR);

    /* Compute pose and velocity */
    double SHM_VelX, SHM_VelY, SHM_VelRZ;
    agvmVelWheels2Cartesian(UL, UR, LL, LR, SHM_VelX, SHM_VelY, SHM_VelRZ);
    // printf("Cartesian velocity: %f, %f, %f\n", SHM_VelX, SHM_VelY, SHM_VelRZ);
    double RealRZDiff = SHM_VelRZ * PLC_Period;
    double OutX, OutY;
    agvm2DRotate(SHM_VelX * PLC_Period, SHM_VelY * PLC_Period, SHM_PosRZ + RealRZDiff / 2.0, OutX, OutY);

    SHM_PosX = SHM_PosX + OutX;
    SHM_PosY = SHM_PosY + OutY;
    SHM_PosRZ = SHM_PosRZ + RealRZDiff;

    /* Send the AMR states */
    agvmInfo.mPosX = SHM_PosX;
    agvmInfo.mPosY = SHM_PosY;
    agvmInfo.mPosRZ = SHM_PosRZ;
    agvmInfo.mVelX = SHM_VelX;
    agvmInfo.mVelY = SHM_VelY;
    agvmInfo.mVelRZ = SHM_VelRZ;
    memcpy(s_buf, &agvmInfo, sizeof(agvmInfo));

    if (!shm_blkbuf_full(handle_s))
    {
      ret = shm_blkbuf_write(handle_s, s_buf, sizeof(s_buf));
      // printf("%s: sent %d bytes\n", __FUNCTION__, ret);
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

  handle_s = shm_blkbuf_init((char*)"amr_state", 16, MSG_LEN);
  handle_c = shm_blkbuf_init((char*)"amr_cmd", 16, MSG_LEN);

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
