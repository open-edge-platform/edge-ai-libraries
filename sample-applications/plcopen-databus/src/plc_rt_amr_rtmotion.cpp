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

#include <fb/common/include/axis.hpp>
#include <fb/common/include/global.hpp>
#include <fb/public/include/fb_halt.hpp>
#include <fb/public/include/fb_stop.hpp>
#include <fb/public/include/fb_power.hpp>
#include <fb/public/include/fb_reset.hpp>
#include <fb/public/include/fb_read_axis_error.hpp>
#include <fb/public/include/fb_read_actual_velocity.hpp>
#include <fb/public/include/fb_move_velocity.hpp>
#include <fb/public/include/fb_move_absolute.hpp>
#include <fb/public/include/fb_move_relative.hpp>

#define CYCLE_US 1000
#define NSEC_PER_SEC (1000000000L)

static volatile int run = 1;
static pthread_t cyclic_thread;

#define AXIS_NUM 4

/* Shm related data types
 * s_buf, handle_s: data sent from RT domain, AMR state info
 * c_buf, handle_c: data sent to RT domain, AMR commands
 */
#define MSG_LEN 512
static char s_buf[MSG_LEN];
static char c_buf[MSG_LEN];
static shm_handle_t handle_s, handle_c;

// Global variables
const double AxisVelLimit = 0.3;      // (*wheels velocity limit(m/s)*)
const double AxisAccLimit = 0.5;      // (*wheels acceleration limit(m/s^2)*)
const double RotMin = 0.06;           // (*mimnimum rotation velocity(rad)*)
const double VelMin = 0.5;          // (*minimum translation velocity(m)*)
const double WheelVDistance = 0.485;  // (*distance between front and back wheels m（wheels center to center）*)
const double WheelHDistance = 0.415;  // (*distance between two side wheels m（wheels center to center）*)
const double RatioX = 0.97;           // (*measured X direction encoder ratio*)
const double RatioY = 0.942;          // (*measured Y direction encoder ratio*)
const double RatioRZ = 1.0;           // (*measured RZ direction encoder ratio*)
const double XPosYImpect = 0.0;       // (*influence to Y by X direction go forward 1*)
const double XNegYImpect = 0.0;       // (*influence to Y by X direction go back 1*)
const double XPosRZImpect = 0.0;      // (*influence to RZ by X direction go forward 1*)
const double XNegRZImpect = 0.0;      // (*influence to RZ by X direction go back 1*)
const double YPosXImpect = 0.0;       // (*influence to X by Y direction go forward 1*)
const double YNegXImpect = 0.0;       // (*influence to X by Y direction go back 1*)
const double YPosRZImpect = 0.0;      // (*influence to RZ by Y direction go forward 1*)
const double YNegRZImpect = 0.0;      // (*influence to RZ by Y direction go back 1*)
const double RZPosXImpect = 0.0;      // (*influence to X by RZ rotate un-clockwise 1*)
const double RZPosYImpect = 0.0;      // (*influence to X by RZ rotate clockwise 1*)
const double RZNegXImpect = 0.0;      // (*influence to Y by RZ rotate un-clockwise 1*)
const double RZNegYImpect = 0.0;      // (*influence to Y by RZ rotate clockwise 1*)

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

const double PLC_Period = 0.001;

/* Cartesian velocity to wheels velocity */
class agvmVelCartesian2Wheels
{
public:

  agvmVelCartesian2Wheels()
  : UL(0.0), UR(0.0), LL(0.0), LR(0.0)
  {}
  
  
  void call(const double VelX, const double VelY, const double VelRZ)
  {
    double distance = WheelVDistance + WheelHDistance;
    double VelLZ = VelRZ * distance / 2.0;

    UL = VelX - VelY - VelLZ;
    UR = VelX + VelY + VelLZ;
    LL = VelX + VelY - VelLZ;
    LR = VelX - VelY + VelLZ;
  }

  double UL, UR, LL, LR;
};

/* Wheels velocity to cartesian velocity */
class agvmVelWheels2Cartesian
{
public:

  agvmVelWheels2Cartesian()
  : VelX(0.0), VelY(0.0), VelRZ(0.0)
  {}
  
  void call(const double UL, const double UR, const double LL, const double LR)
  {
    double distance = WheelVDistance + WheelHDistance;
    double DimX = UL + UR + LL + LR;
    double DimY = -UL + UR + LL - LR;
    double DimZ = -UL + UR - LL + LR;
    
    VelX = DimX / 4.0;
    VelY = DimY / 4.0;
    VelRZ= DimZ / 4.0 / distance * 2.0;
  }

  double VelX, VelY, VelRZ;
};

/* */

class agvm2DRotate
{
public:
  agvm2DRotate()
  : OutX(0.0), OutY(0.0)
  {}
  
  void call(const double InX, const double InY, const double RZ)
  {
    OutX = InX * cos(RZ) - InY * sin(RZ);
    OutY = InX * sin(RZ) + InY * cos(RZ);
  }

  double OutX, OutY;
};

/* */
double agvmGetRatioByVelLimit(const double VelLimit, const double Vel1, const double Vel2, const double Vel3, const double Vel4)
{
  double Ratio = 0.0, VelMax = 0.0;
  VelMax = fabs(Vel1);

  if (VelMax < fabs(Vel2))
    VelMax = fabs(Vel2);

  if (VelMax < fabs(Vel3))
    VelMax = fabs(Vel3);

  if (VelMax < fabs(Vel4))
    VelMax = fabs(Vel4);

  if (VelMax > 0.0)
    Ratio = VelLimit / VelMax;

  return Ratio;
}

double agvmLimitVel(const double Vel, const double VelMin)
{
  double res = Vel;
  if (Vel > 0.0 && Vel > VelMin)
    res = VelMin;
  if (Vel < 0.0 && Vel < -VelMin)
    res = -VelMin;

  return res;
}

void* my_thread(void* /*arg*/)
{
  /* Init variables */
  bool PowStat = false, SHM_Error = false, SHM_CancelRelMove = false, SHM_Enable = false, SHM_EmergStop = false,
       INIT = true, ENABLE_FLAG = false, MoveRel = false;
  uint32_t AxisULErr, AxisURErr, AxisLLErr, AxisLRErr, Mode = 0;
  double VAxisULVel, VAxisURVel, VAxisLLVel, VAxisLRVel; 

  double SHM_VelX = 0, SHM_VelY = 0, SHM_VelRZ = 0, SHM_PosX = 0, SHM_PosY = 0, SHM_PosRZ = 0,
         SHM_RelPosRZ = 0, SHM_RelMoveBusy = 0, SHM_TransX = 0, SHM_TransY = 0, SHM_TransRZ = 0,
         SHM_RelMove = 0, SHM_RelPosX = 0, SHM_RelPosY = 0;
  double TransX = 0.0, TransY = 0.0, TransRZ = 0.0;
  double RealRZDiff, RZXImpact, RZYImpact, YXImpact, XYImpact, XRZImpact, YRZImpact;
  // double VelRatio = 1, X, Y;
  double VelRatio = 1;

  agvmVelCartesian2Wheels AGVM_Cartesian2Wheels_1;
  agvmVelWheels2Cartesian AGVM_Wheels2Cartesian_1;
  agvm2DRotate AGVM_2DRotate_1;

  /* Init PLCopen motion related components */
  using namespace RTmotion;  
  RTmotion::AXIS_REF axis[AXIS_NUM];
  RTmotion::AxisConfig config[AXIS_NUM];
  RTmotion::Servo* servo[AXIS_NUM];
  for (size_t i = 0; i < AXIS_NUM; i ++)
  {    
    config[i].encoder_count_per_unit_ = 13798;//fb user unit = servo device unit
    axis[i] = new RTmotion::Axis();
    axis[i]->setAxisId(i);
    axis[i]->setAxisConfig(&config[i]);
    servo[i] = new RTmotion::Servo();
    axis[i]->setServo(servo[i]);
  }
  printf("%d axis initialized.\n", AXIS_NUM);

  // Init FBs
  RTmotion::FbPower fbPower[AXIS_NUM];
  for(size_t i=0; i<AXIS_NUM; i++)
  {
    fbPower[i].setAxis(axis[i]);
    fbPower[i].setEnablePositive(mcTRUE);
    fbPower[i].setEnableNegative(mcTRUE);
  }
  
  RTmotion::FbStop stop[AXIS_NUM];
  for(size_t i=0; i<AXIS_NUM; i++)
  {
    stop[i].setAxis(axis[i]);
    stop[i].setAcceleration(20);
    stop[i].setDeceleration(20);
    stop[i].setJerk(5000);
  }
  
  RTmotion::FbReset reset[AXIS_NUM];
  for(size_t i=0;i<AXIS_NUM;i++)
  {
    reset[i].setAxis(axis[i]);
  }

  RTmotion::FbHalt halt[AXIS_NUM];
  for(size_t i=0;i<AXIS_NUM;i++)
  {
    halt[i].setAxis(axis[i]);
    halt[i].setAcceleration(0.5);
    halt[i].setJerk(10);
    halt[i].setBufferMode(RTmotion::mcAborting);
  }

  RTmotion::FbMoveVelocity moveVel[AXIS_NUM];
  for(size_t i=0;i<AXIS_NUM;i++)
  {
    moveVel[i].setAxis(axis[i]);
    moveVel[i].setBufferMode(RTmotion::mcAborting);
  }

  RTmotion::FbReadAxisError axisError[AXIS_NUM];
  for(size_t i=0;i<AXIS_NUM;i++)
  {
    axisError[i].setAxis(axis[i]);
  }

  RTmotion::FbReadActualVelocity actualVelocity[AXIS_NUM];
  for(size_t i=0;i<AXIS_NUM;i++)
  {
    actualVelocity[i].setAxis(axis[i]);
    actualVelocity[i].setEnable(mcTRUE);
  }

  RTmotion::FbMoveAbsolute moveAbsolute[AXIS_NUM];
  for(size_t i=0;i<AXIS_NUM;i++)
  {
    moveAbsolute[i].setAxis(axis[i]);
  }

  RTmotion::FbMoveRelative moveRelative[AXIS_NUM];
  for(size_t i=0;i<AXIS_NUM;i++)
  {
    moveRelative[i].setAxis(axis[i]);
  }
  /* Init cycle related variables */
  struct timespec next_period;
#ifdef MEASURE_TIMING 
  struct timespec prev_time, end_time;
  int64_t latency_ns = 0;
  int64_t latency_min_ns = 1000000, latency_max_ns = -1000000;
#endif
  unsigned int cycle_counter = 0;
  int ret;
  
  /* Init thread */
  struct sched_param param = {};
  param.sched_priority = 99;
  pthread_setschedparam(pthread_self(), SCHED_FIFO, &param);
  clock_gettime(CLOCK_MONOTONIC, &next_period);
#ifdef MEASURE_TIMING
  clock_gettime(CLOCK_MONOTONIC, &prev_time);
#endif  
  bool newSignal = false;
  /* Start RT cycle */
  while (run != 0)
  {
    next_period.tv_nsec += CYCLE_US * 1000;
    while (next_period.tv_nsec >= NSEC_PER_SEC)
    {
      next_period.tv_nsec -= NSEC_PER_SEC;
      next_period.tv_sec++;
    }
    clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &next_period, NULL);
#ifdef  MEASURE_TIMING
    clock_gettime(CLOCK_MONOTONIC, &end_time);
    latency_ns = DIFF_NS(prev_time, end_time) - CYCLE_US*1000;
    if (latency_ns > latency_max_ns)
        latency_max_ns = latency_ns;
    if (latency_ns < latency_min_ns)
        latency_min_ns = latency_ns;
    prev_time = end_time;
#endif
    /* Get the AMR commands */
    if (!shm_blkbuf_empty(handle_c))
    {
      ret = shm_blkbuf_read(handle_c, c_buf, sizeof(c_buf));
      if (ret) {
        memcpy(&ctrl, c_buf, sizeof(ctrl));
        DEBUG_PRINT("Receive command: %f, %f, %f\n",  ctrl.mTransV, ctrl.mTransH, ctrl.mTwist);
      }
    }
    SHM_Enable = ctrl.mEnable;
    SHM_EmergStop = ctrl.mEmergStop;
    SHM_TransY = ctrl.mTransH;
    SHM_TransX = ctrl.mTransV;
    SHM_TransRZ = ctrl.mTwist;
    SHM_RelMove = ctrl.mRelMove;
    SHM_RelPosX = ctrl.mRelX;
    SHM_RelPosY = ctrl.mRelY;
    SHM_RelPosRZ = ctrl.mRelRZ;

    /* Scheduler cyclic processing */
    for(size_t i=0;i<AXIS_NUM;i++)
    {
      axis[i]->runCycle();
    }

    /* Start motion */
    // TransX = agvmLimitVel(SHM_TransX, VelMin);
    // TransY = agvmLimitVel(SHM_TransY, VelMin);
    // TransRZ = agvmLimitVel(SHM_TransRZ, RotMin);
    if(fabs(TransX - SHM_TransX) < 0.001 && fabs(TransY - SHM_TransY) < 0.001 && fabs(TransRZ - SHM_TransRZ) < 0.001)
        newSignal = false;
    else newSignal = true;
    
    TransX = SHM_TransX;
    TransY = SHM_TransY;
    TransRZ = SHM_TransRZ;

    /* Init motion */
    if (INIT)
    {
      DEBUG_PRINT("INIT\n");
      SHM_PosX = 0.0;
      SHM_PosY = 0.0;
      SHM_PosRZ = 0.0;
      INIT = false;
      SHM_EmergStop = false;
    }

    /* Emergency stop */
    if (SHM_EmergStop)
    {
      DEBUG_PRINT("EmergStop\n");
      SHM_TransX = 0.0;
      SHM_TransY = 0.0;
      SHM_TransRZ = 0.0;

      SHM_EmergStop = false;
      SHM_Enable = false;
      ENABLE_FLAG = false;
      Mode = 0;

      for (size_t i = 0; i < AXIS_NUM; i++)
      {
        stop->setExecute(mcFALSE);
        stop->runCycle();
        stop->setExecute(mcTRUE);
        stop->runCycle(); //上升沿
      }
    }

    /* Enable operation */
    if (SHM_Enable)
    {
      DEBUG_PRINT("SHM_Enable\n");
      SHM_Enable = false;
      if (!PowStat)
      {
        for (size_t i = 0; i < AXIS_NUM; i++)
        {
          reset[i].setEnable(mcFALSE);
          reset[i].runCycle();
        }
        ENABLE_FLAG = true;
      }
    }

    if (ENABLE_FLAG)
    {
      DEBUG_PRINT("ENABLE_FLAG\n");
      for (size_t i = 0; i < AXIS_NUM; i++)
      {
        reset[i].setEnable(mcTRUE);
        reset[i].runCycle();
      }

      if(reset[0].isDone() == mcTRUE && reset[1].isDone() == mcTRUE && 
         reset[2].isDone() == mcTRUE && reset[3].isDone() == mcTRUE)
        ENABLE_FLAG = false;
    }

    if (Mode == 0)
      SHM_RelMoveBusy = false;

    for (size_t i = 0; i < AXIS_NUM; i++)
    {
      fbPower[i].setEnable(mcTRUE);
      fbPower[i].runCycle();
    }

    PowStat = fbPower[0].getPowerStatus() == mcTRUE && 
              fbPower[1].getPowerStatus() == mcTRUE && 
              fbPower[2].getPowerStatus() == mcTRUE && 
              fbPower[3].getPowerStatus() == mcTRUE;
    if (PowStat)
    {
      if (SHM_CancelRelMove)
      {
        DEBUG_PRINT("SHM_CancelRelMove\n");
        for (size_t i = 0; i < AXIS_NUM; i++)
        {
          halt[i].setExecute(mcFALSE);
          halt[i].runCycle();
        }
        MoveRel = false;
        SHM_CancelRelMove = false;
        Mode = 100;
      }

      double axis_vel[AXIS_NUM] = {AGVM_Cartesian2Wheels_1.UL,
                                   AGVM_Cartesian2Wheels_1.UR,
                                   AGVM_Cartesian2Wheels_1.LL,
                                   AGVM_Cartesian2Wheels_1.LR};
      DEBUG_PRINT("MoveRel: %d\n", MoveRel);
      for (size_t i = 0; i < AXIS_NUM; i++)
      {
        moveRelative[i].setExecute(MoveRel ? mcTRUE : mcFALSE);
        moveRelative[i].setDistance(axis_vel[i]);
        moveRelative[i].setVelocity(fabs(axis_vel[i])*VelRatio);
        moveRelative[i].setAcceleration(AxisAccLimit);
        moveRelative[i].setDeceleration(AxisAccLimit);
        moveRelative[i].runCycle();
      }

      if (moveRelative[0].isBusy() == mcFALSE && moveRelative[1].isBusy() == mcFALSE && 
          moveRelative[2].isBusy() == mcFALSE && moveRelative[3].isBusy() == mcFALSE)
      {
        for (size_t i = 0; i < AXIS_NUM; i++)
        {
          moveRelative[i].setExecute(mcFALSE);
          moveRelative[i].runCycle();
        }
        MoveRel = false;
      }

      switch (Mode)
      {
      case 0:
        {
          DEBUG_PRINT("Mode 0\n");
          if (SHM_RelMove)
          {
            AGVM_Cartesian2Wheels_1.call(0.0, 0.0, SHM_RelPosRZ / RatioRZ);
            VelRatio = agvmGetRatioByVelLimit(AxisVelLimit, 
                        AGVM_Cartesian2Wheels_1.UL,
                        AGVM_Cartesian2Wheels_1.UR,
                        AGVM_Cartesian2Wheels_1.LL,
                        AGVM_Cartesian2Wheels_1.LR);
            MoveRel = true;
            SHM_RelMove = false;
            SHM_RelMoveBusy = true;
            Mode = 10;
          }
          else
          {
            DEBUG_PRINT("AMR velocity-1: %f, %f, %f\n", TransX, TransY, TransRZ);
            AGVM_Cartesian2Wheels_1.call(TransX, TransY, TransRZ);
            VAxisULVel = AGVM_Cartesian2Wheels_1.UL;
            VAxisURVel = AGVM_Cartesian2Wheels_1.UR;
            VAxisLLVel = AGVM_Cartesian2Wheels_1.LL;
            VAxisLRVel = AGVM_Cartesian2Wheels_1.LR;

            VelRatio = agvmGetRatioByVelLimit(AxisVelLimit, VAxisULVel, VAxisURVel, VAxisLLVel, VAxisLRVel);
            // if (VelRatio > 1.0)
            //   VelRatio = 1.0;
            VelRatio = 1.0;
            double axis_vel[AXIS_NUM] = {VAxisULVel, VAxisURVel, VAxisLLVel, VAxisLRVel};
            for (size_t i = 0; i < AXIS_NUM; i++)
            {
              if (axis_vel[i] == 0.0)
              {
                if(newSignal)
                {
                  halt[i].setExecute(mcFALSE);
                  halt[i].runCycle();
                  halt[i].setDeceleration(AxisAccLimit);
                }
                halt[i].setExecute(mcTRUE);
                halt[i].runCycle();
              }
              else
              {
                DEBUG_PRINT("Wheels axis_vel[%zu]: %f\n", i, axis_vel[i] * VelRatio);
                
                if(newSignal)
                {
                  moveVel[i].setExecute(mcFALSE);
                  moveVel[i].runCycle();
                  moveVel[i].setVelocity(axis_vel[i]*VelRatio);
                  moveVel[i].setAcceleration(AxisAccLimit);
                  moveVel[i].setDeceleration(AxisAccLimit);
                  moveVel[i].setJerk(10);
                }
                moveVel[i].setExecute(mcTRUE);
                moveVel[i].runCycle();
              }
            }
          }
        }
        break;
      case 10:
        {
          DEBUG_PRINT("Mode 10\n");
          if (!MoveRel)
          {
            AGVM_2DRotate_1.call(SHM_RelPosX, SHM_RelPosY, -SHM_RelPosRZ);

            if (AGVM_2DRotate_1.OutX > 0.0)
              XYImpact = XPosYImpect;
            else
              XYImpact = XNegYImpect;

            if (AGVM_2DRotate_1.OutY > 0.0)
              YXImpact = YPosXImpect;
            else
              YXImpact = YNegXImpect;

            // X = AGVM_2DRotate_1.OutX / RatioX - AGVM_2DRotate_1.OutY * YXImpact;
            // Y = AGVM_2DRotate_1.OutY / RatioY - AGVM_2DRotate_1.OutX * XYImpact;
            AGVM_Cartesian2Wheels_1.call(AGVM_2DRotate_1.OutX / RatioX,
                                         AGVM_2DRotate_1.OutY / RatioY,
                                         0.0);

            VelRatio = agvmGetRatioByVelLimit(AxisVelLimit,
                                              AGVM_Cartesian2Wheels_1.UL,
                                              AGVM_Cartesian2Wheels_1.UR,
                                              AGVM_Cartesian2Wheels_1.LL,
                                              AGVM_Cartesian2Wheels_1.LR);
            MoveRel = true;
            Mode = 20;
          }
        }
        break;
      case 20:
        {
          DEBUG_PRINT("Mode 20\n");
          if (!MoveRel)
            Mode = 0;
        }
        break;
      case 100:
        {
          DEBUG_PRINT("Mode 100\n");
          for (size_t i = 0; i < AXIS_NUM; i++)
          {
            halt[i].setExecute(mcTRUE);
            halt[i].setDeceleration(AxisAccLimit);
            halt[i].runCycle();
          }

          if (halt[0].isBusy() == mcFALSE && halt[1].isBusy() == mcFALSE &&
              halt[2].isBusy() == mcFALSE && halt[3].isBusy() == mcFALSE)
            Mode = 0;
        }
        break;
      default:
          Mode = 0;
        break;
      }
    }

    for (size_t i = 0; i < AXIS_NUM; i++)
      actualVelocity[i].runCycle();

    /* Compute pose and velocity */
    AGVM_Wheels2Cartesian_1.call(actualVelocity[0].getFloatValue(),
                                 actualVelocity[1].getFloatValue(),
                                 actualVelocity[2].getFloatValue(),
                                 actualVelocity[3].getFloatValue());
    DEBUG_PRINT("Wheels velocity-2: %f, %f, %f, %f\n", 
              actualVelocity[0].getFloatValue(),
              actualVelocity[1].getFloatValue(),
              actualVelocity[2].getFloatValue(),
              actualVelocity[3].getFloatValue());


    SHM_VelX = AGVM_Wheels2Cartesian_1.VelX;
    SHM_VelY = AGVM_Wheels2Cartesian_1.VelY;
    SHM_VelRZ = AGVM_Wheels2Cartesian_1.VelRZ;

    DEBUG_PRINT("AMR velocity: %f, %f, %f\n\n", SHM_VelX, SHM_VelY, SHM_VelRZ);
    
    RealRZDiff = AGVM_Wheels2Cartesian_1.VelRZ * PLC_Period * RatioRZ;

    AGVM_2DRotate_1.call(AGVM_Wheels2Cartesian_1.VelX * PLC_Period * RatioX,
                         AGVM_Wheels2Cartesian_1.VelY * PLC_Period * RatioY,
                         SHM_PosRZ + RealRZDiff / 2.0);

    if (AGVM_2DRotate_1.OutX > 0.0)
    {
      XYImpact = XPosYImpect;
      XRZImpact = XPosRZImpect;
    }
    else
    {
      XYImpact = XNegYImpect;
      XRZImpact = XNegRZImpect;
    }

    if(AGVM_2DRotate_1.OutY > 0.0)
    {
      YXImpact = YPosXImpect;
      YRZImpact = XPosRZImpect;
    }
    else
    {
      YXImpact = YNegXImpect;
      YRZImpact = XNegRZImpect;
    }

    if(RealRZDiff > 0.0)
    {
      RZXImpact = RZPosXImpect;
      RZYImpact = RZPosYImpect;
    }
    else
    {
      RZXImpact = RZNegXImpect;
      RZYImpact = RZNegYImpect;
    }

    SHM_PosX = SHM_PosX + AGVM_2DRotate_1.OutX + RealRZDiff * RZXImpact + AGVM_2DRotate_1.OutY * YXImpact;
    SHM_PosY = SHM_PosY + AGVM_2DRotate_1.OutY + RealRZDiff * RZYImpact + AGVM_2DRotate_1.OutX * XYImpact;
    SHM_PosRZ = SHM_PosRZ + RealRZDiff + AGVM_2DRotate_1.OutX * XRZImpact + AGVM_2DRotate_1.OutY * YRZImpact;

    axisError[0].setEnable(mcTRUE);
    axisError[0].runCycle();
    AxisULErr = axisError[0].getErrorID();

    axisError[1].setEnable(mcTRUE);
    axisError[1].runCycle();
    AxisURErr = axisError[1].getErrorID();

    axisError[2].setEnable(mcTRUE);
    axisError[2].runCycle();
    AxisLLErr = axisError[2].getErrorID();

    axisError[3].setEnable(mcTRUE);
    axisError[3].runCycle();
    AxisLRErr = axisError[3].getErrorID();

    if (AxisULErr == 0 ||
        AxisURErr == 0 ||
        AxisLLErr == 0 ||
        AxisLRErr == 0)
    {
      SHM_Error = true;
    }
    else
    {
      SHM_Error = false;
    }

    /* Send the AMR states */
    agvmInfo.mPosX = SHM_PosX;
    agvmInfo.mPosY = SHM_PosY;
    agvmInfo.mPosRZ = SHM_PosRZ;
    agvmInfo.mVelX = SHM_VelX;
    agvmInfo.mVelY = SHM_VelY;
    agvmInfo.mVelRZ = SHM_VelRZ;
    agvmInfo.mError = SHM_Error;
    agvmInfo.mRelMoveBusy = SHM_RelMoveBusy;
    memcpy(s_buf, &agvmInfo, sizeof(agvmInfo));

    if (!shm_blkbuf_full(handle_s))
    {
      ret = shm_blkbuf_write(handle_s, s_buf, sizeof(s_buf));
      // printf("%s: sent %d bytes\n", __FUNCTION__, ret);
    }
    cycle_counter++;
  }
#ifdef MEASURE_TIMING
  printf("*********************************************\n");
  printf("jitter time         %10.3f ... %10.3f\n", (float)latency_min_ns/1000, (float)latency_max_ns/1000);
  printf("*********************************************\n");
#endif
  for (size_t i = 0; i < AXIS_NUM; i ++)
  {
    delete servo[i];
    delete axis[i];
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
