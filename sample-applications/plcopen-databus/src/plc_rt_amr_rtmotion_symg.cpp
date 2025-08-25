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
#include <vector>
#include <unistd.h>
#include <getopt.h>

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
#include <symg_servo.hpp>

// Thread related
#define CYCLE_US 1000
#define NSEC_PER_SEC (1000000000L)

using namespace RTmotion;

static volatile int run = 1;
static pthread_t cyclic_thread;

// Option related
static bool move_vel = false;   // velocity move flag
static bool move_rel = false;   // relative move flag
static double move_x = 0.0;   // move value along x axis
static double move_y = 0.0;   // move value along y axis
static double move_rz = 0.0;  // move value around z axis

// Servo related
static RTmotion::Servo* servos[4];
static AXIS_REF axis[4];

static Slave_Data ec_slave0;
static Ctrl_Data ec_motor0;

static int stop_motor = 0;

static ec_master_t *master = NULL;
static ec_domain_t *domain = NULL;
static uint8_t *domain_pd = NULL;
static ec_slave_config_t *sc;
const static ec_pdo_entry_reg_t domain_regs[] = 
{
  {SLAVE00_POS, SLAVE00_ID, 0x2200, 0x01, &ec_slave0.control, NULL},
  {SLAVE00_POS, SLAVE00_ID, 0x2200, 0x02, &ec_slave0.speed1, NULL},
  {SLAVE00_POS, SLAVE00_ID, 0x2200, 0x03, &ec_slave0.speed2, NULL},
  {SLAVE00_POS, SLAVE00_ID, 0x2200, 0x04, &ec_slave0.speed3, NULL},
  {SLAVE00_POS, SLAVE00_ID, 0x2200, 0x05, &ec_slave0.speed4, NULL},
  {SLAVE00_POS, SLAVE00_ID, 0x2200, 0x06, &ec_slave0.pio_out, NULL},
  {SLAVE00_POS, SLAVE00_ID, 0x2100, 0x01, &ec_slave0.status, NULL},
  {SLAVE00_POS, SLAVE00_ID, 0x2100, 0x02, &ec_slave0.enc1, NULL},
  {SLAVE00_POS, SLAVE00_ID, 0x2100, 0x03, &ec_slave0.enc2, NULL},
  {SLAVE00_POS, SLAVE00_ID, 0x2100, 0x04, &ec_slave0.enc3, NULL},
  {SLAVE00_POS, SLAVE00_ID, 0x2100, 0x05, &ec_slave0.enc4, NULL},
  {SLAVE00_POS, SLAVE00_ID, 0x2100, 0x06, &ec_slave0.pio_in, NULL},
  {}
};

static void data_init(void)
{
  memset(&ec_slave0, 0, sizeof(Slave_Data));
  sc = NULL;
}

static void ec_readmotordata(Ctrl_Data* ec_motor, Slave_Data ec_slave)
{
  ec_motor->stat  	= EC_READ_S32(domain_pd + ec_slave.status);
  ec_motor->en1       = EC_READ_S32(domain_pd + ec_slave.enc1);
  ec_motor->en2       = EC_READ_S32(domain_pd + ec_slave.enc2);
  ec_motor->en3       = EC_READ_S32(domain_pd + ec_slave.enc3);
  ec_motor->en4       = EC_READ_S32(domain_pd + ec_slave.enc4);
}

int ethercat_init()
{
  struct timespec dc_period;

  data_init();

  printf("Requesting master...\n");
  master = ecrt_request_master(0);
  if (!master) {
    return -1;
  }

  printf("Creating domain ...\n");
  domain = ecrt_master_create_domain(master);
  if (!domain){
    return -1;
  }

  // Create configuration for bus coupler
  sc = ecrt_master_slave_config(master, SLAVE00_POS, SLAVE00_ID);
  if (!sc) {
    printf("Slave1 sc is NULL \n");
    return -1;
  }

  printf("Creating slave configurations...\n");
  //ec_slave_config_init(sc);

  if (ecrt_slave_config_pdos(sc, EC_END, slave_syncs)) {
    fprintf(stderr, "Failed to configure PDOs.  1 \n");
    return -1;
  }

  ecrt_master_set_send_interval(master, CYCLE_US);

  if (ecrt_domain_reg_pdo_entry_list(domain, domain_regs)) {
    fprintf(stderr, "PDO entry registration failed!\n");
    return -1;
  }

  /*Configuring DC signal*/
  ecrt_slave_config_dc(sc, 0x0300, PERIOD_NS, PERIOD_NS/2, 0, 0);
  clock_gettime(CLOCK_MONOTONIC, &dc_period);
  ecrt_master_application_time(master, TIMESPEC2NS(dc_period));

  int ret = ecrt_master_select_reference_clock(master, sc);
  if (ret < 0) {
    fprintf(stderr, "Failed to select reference clock: %s\n",
            strerror(-ret));
    return ret;
  }

  printf("Activating master...\n");
  if (ecrt_master_activate(master)) {
    return -1;
  }

  if (!(domain_pd = ecrt_domain_data(domain))) {
    fprintf(stderr, "Failed to get domain data pointer.\n");
    return -1;
  }

  return 0;
}

void ethercat_receive()
{
  ecrt_master_receive(master);
  ecrt_domain_process(domain);
  ec_readmotordata(&ec_motor0,ec_slave0);
}

void ethercat_send()
{
  struct timespec dc_period;
  clock_gettime(CLOCK_MONOTONIC, &dc_period);
  ecrt_master_application_time(master, TIMESPEC2NS(dc_period));
  ecrt_master_sync_reference_clock(master);
  ecrt_master_sync_slave_clocks(master);
  ecrt_domain_queue(domain);
  ecrt_master_send(master);    
}

/* Shm related data types
 * s_buf, handle_s: data sent from RT domain, AMR state info
 * c_buf, handle_c: data sent to RT domain, AMR commands
 */
#define MSG_LEN 512
static char s_buf[MSG_LEN];
static char c_buf[MSG_LEN];
static shm_handle_t handle_s, handle_c;

// Global variables
#define AXIS_NUM 4
const double AxisVelLimit = 0.3;      // (*wheels velocity limit(m/s)*)
const double AxisAccLimit = 0.5;      // (*wheels acceleration limit(m/s^2)*)
const double RotMin = 0.3;           // (*mimnimum rotation velocity(rad)*)
const double VelMin = 0.3;          // (*minimum translation velocity(m)*)
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
  double 	Ratio = 1.0, VelMax;
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
  bool PowStat = false, SHM_Error = false, SHM_RelMove = false, SHM_CancelRelMove = false, SHM_Enable = false, SHM_EmergStop = false,
       INIT = true, ENABLE_FLAG = false, MoveRel = false;
	// uint32_t AxisUL = 0, AxisUR = 1, AxisLL = 2, AxisLR = 3;
  uint32_t AxisULErr, AxisURErr, AxisLLErr, AxisLRErr, Mode = 0;
	double VAxisULVel, VAxisURVel, VAxisLLVel, VAxisLRVel; 

  double SHM_VelX = 0, SHM_VelY = 0, SHM_VelRZ = 0, SHM_PosX = 0, SHM_PosY = 0, SHM_PosRZ = 0,
         SHM_RelPosRZ = 0, SHM_RelMoveBusy = 0, SHM_TransX = 0, SHM_TransY = 0, SHM_TransRZ = 0,
         SHM_RelPosX = 0, SHM_RelPosY = 0;
  double TransX = 0.0, TransY = 0.0, TransRZ = 0.0, TransX_R = 0.0, TransY_R = 0.0, TransRZ_R = 0.0;
  double RealRZDiff, RZXImpact, RZYImpact, YXImpact, XYImpact, XRZImpact, YRZImpact;
  double VelRatio = 1, X, Y;

  agvmVelCartesian2Wheels AGVM_Cartesian2Wheels_1;
  agvmVelWheels2Cartesian AGVM_Wheels2Cartesian_1;
  agvm2DRotate AGVM_2DRotate_1;

  /* Init PLCopen motion related components */
  AxisConfig cfg[AXIS_NUM];
  for (size_t i = 0; i < AXIS_NUM; i ++)
  {
    cfg[i].encoder_count_per_unit_ = PER_CIRCLE_ENCODER; //fb user unit = servo device unit
    cfg[i].pos_positive_limit_ = 1000;
    cfg[i].pos_negative_limit_ = -1000;
    axis[i] = new Axis();
    axis[i]->setAxisId(i);
    axis[i]->setAxisConfig(&cfg[i]);
    axis[i]->setServo(servos[i]);    
  }
  printf("%d axis initialized.\n", AXIS_NUM);

  // Init FBs
  FbPower mc_power[AXIS_NUM];
  for (size_t i = 0; i < AXIS_NUM; i++)
  {
    mc_power[i].setAxis(axis[i]);
    mc_power[i].setEnablePositive(mcTRUE);
    mc_power[i].setEnableNegative(mcTRUE);
  }

  FbStop mc_stop[AXIS_NUM];
  for(size_t i = 0;i < AXIS_NUM; i++)
  {
    mc_stop[i].setAxis(axis[i]);
    mc_stop[i].setAcceleration(20);
    mc_stop[i].setDeceleration(20);
    mc_stop[i].setJerk(5000);
  }

  FbReset mc_reset[AXIS_NUM];
  for (size_t i = 0; i < AXIS_NUM; i++)
    mc_reset[i].setAxis(axis[i]);

  FbHalt mc_halt[AXIS_NUM];
  for (size_t i = 0; i < AXIS_NUM; i++)
  {
    mc_halt[i].setAxis(axis[i]);
    mc_halt[i].setAcceleration(0.5);
    mc_halt[i].setJerk(10);
    mc_halt[i].setBufferMode(mcAborting);
  }

  FbMoveVelocity mc_move_velocity[AXIS_NUM];
  for (size_t i = 0; i < AXIS_NUM; i++)
  {
    mc_move_velocity[i].setAxis(axis[i]);
    mc_move_velocity[i].setBufferMode(mcAborting);
  }

  FbReadAxisError mc_read_axis_error[AXIS_NUM];
  for (size_t i = 0; i < AXIS_NUM; i++)
    mc_read_axis_error[i].setAxis(axis[i]);

  FbReadActualVelocity mc_read_actual_velocity[AXIS_NUM];
  for (size_t i = 0; i < AXIS_NUM; i++)
  {
    mc_read_actual_velocity[i].setAxis(axis[i]);
    mc_read_actual_velocity[i].setEnable(mcTRUE);
  }

  FbMoveAbsolute mc_move_absolute[AXIS_NUM];
  for (size_t i = 0; i < AXIS_NUM; i++)
    mc_move_absolute[i].setAxis(axis[i]);

  FbMoveRelative mc_move_relative[AXIS_NUM];
  for (size_t i = 0; i < AXIS_NUM; i++)
    mc_move_relative[i].setAxis(axis[i]);

  /* Init cycle related variables */
  struct timespec next_period;
  unsigned int cycle_counter = 0;
  int ret;
  
  /* Init thread */
  struct sched_param param = {};
  param.sched_priority = 99;
  pthread_setschedparam(pthread_self(), SCHED_FIFO, &param);
  clock_gettime(CLOCK_MONOTONIC, &next_period);
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

    ethercat_receive();

    /* Get the AMR commands */
    if (!shm_blkbuf_empty(handle_c))
    {
      ret = shm_blkbuf_read(handle_c, c_buf, sizeof(c_buf));
      if (ret) {
        memcpy(&ctrl, c_buf, sizeof(ctrl));
        printf("Receive command: %f, %f, %f\n",  ctrl.mTransV, ctrl.mTransH, ctrl.mTwist);
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
    TransX = agvmLimitVel(SHM_TransX, VelMin);
    TransY = agvmLimitVel(SHM_TransY, VelMin);
    TransRZ = agvmLimitVel(SHM_TransRZ, RotMin);
    if(fabs(TransX - TransX_R) < 0.001 && fabs(TransY - TransY_R) < 0.001 && fabs(TransRZ - TransRZ_R) < 0.001)
        newSignal = false;
    else newSignal = true;
    TransX_R = TransX;
    TransY_R = TransY;
    TransRZ_R = TransRZ;

    if (move_vel)
    {
      TransX = move_x;
      TransY = move_y;
      TransRZ = move_rz;
    }

    if (move_rel)
    {
      SHM_RelMove = true;
      SHM_RelPosX = move_x;
      SHM_RelPosY = move_y;
      SHM_RelPosRZ = move_rz;
    }
    
    /* Init motion */
    if (INIT)
    {
      printf("INIT\n");
      SHM_PosX = 0.0;
      SHM_PosY = 0.0;
      SHM_PosRZ = 0.0;
      INIT = false;
      SHM_EmergStop = false;
    }

    /* Emergency stop */
    if (SHM_EmergStop)
    {
      printf("EmergStop\n");
      SHM_TransX = 0.0;
      SHM_TransY = 0.0;
      SHM_TransRZ = 0.0;

      SHM_EmergStop = false;
      SHM_Enable = false;
      ENABLE_FLAG = false;
      Mode = 0;

      for (size_t i = 0; i < AXIS_NUM; i++)
      {
        mc_stop[i].setExecute(mcFALSE);
        mc_stop[i].runCycle();
        mc_stop[i].setExecute(mcTRUE);
        mc_stop[i].runCycle();
      }
    }

    /* Enable operation */
    if (SHM_Enable)
    {
      printf("SHM_Enable\n");
      SHM_Enable = false;
      if (!PowStat)
      {
        for (size_t i = 0; i < AXIS_NUM; i++)
        {
          mc_reset[i].setEnable(mcFALSE);
          mc_reset[i].runCycle();
        }
        ENABLE_FLAG = true;
      }
    }

    if (ENABLE_FLAG)
    {
      printf("ENABLE_FLAG\n");
      for (size_t i = 0; i < AXIS_NUM; i++)
      {
        mc_reset[i].setEnable(mcTRUE);
        mc_reset[i].runCycle();
      }

      if (mc_reset[0].isDone() == mcTRUE && mc_reset[1].isDone() == mcTRUE && 
          mc_reset[2].isDone() == mcTRUE&& mc_reset[3].isDone() == mcTRUE)
        ENABLE_FLAG = false;
    }

    if (Mode == 0)
      SHM_RelMoveBusy = false;

    for (size_t i = 0; i < AXIS_NUM; i++)
    {
      mc_power[i].setEnable(mcTRUE);
      mc_power[i].runCycle();
    }

    PowStat = mc_power[0].getPowerStatus() == mcTRUE &&
              mc_power[1].getPowerStatus() == mcTRUE &&
              mc_power[2].getPowerStatus() == mcTRUE &&
              mc_power[3].getPowerStatus() == mcTRUE;

    if (PowStat)
    {
      if (SHM_CancelRelMove)
      {
        printf("SHM_CancelRelMove\n");
        for (size_t i = 0; i < AXIS_NUM; i++)
        {
          mc_halt[i].setExecute(mcFALSE);
          mc_halt[i].runCycle();
        }
        MoveRel = false;
        SHM_CancelRelMove = false;
        Mode = 100;
      }

      double axis_vel[AXIS_NUM] = {AGVM_Cartesian2Wheels_1.UL,
                                   AGVM_Cartesian2Wheels_1.UR,
                                   AGVM_Cartesian2Wheels_1.LL,
                                   AGVM_Cartesian2Wheels_1.LR};
      printf("MoveRel: %d\n", MoveRel);
      for (size_t i = 0; i < AXIS_NUM; i++)
      {
        mc_move_relative[i].setExecute(MoveRel ? mcTRUE : mcFALSE);
        mc_move_relative[i].setDistance(axis_vel[i]);
        mc_move_relative[i].setVelocity(fabs(axis_vel[i]) * VelRatio);
        mc_move_relative[i].setAcceleration(AxisAccLimit);
        mc_move_relative[i].setDeceleration(AxisAccLimit);
        mc_move_relative[i].runCycle();
      }

      if (mc_move_relative[0].isBusy() != mcTRUE && mc_move_relative[1].isBusy() != mcTRUE && 
          mc_move_relative[2].isBusy() != mcTRUE && mc_move_relative[3].isBusy() !=mcTRUE)
      {
        for (size_t i = 0; i < AXIS_NUM; i++)
        {
          mc_move_relative[i].setExecute(mcFALSE);
          mc_move_relative[i].runCycle();
        }
        MoveRel = false;
      }
      switch (Mode)
      {
      case 0:
        {
          printf("Mode 0\n");
          if (SHM_RelMove)
          {
            AGVM_Cartesian2Wheels_1.call(SHM_RelPosX, SHM_RelPosY, SHM_RelPosRZ / RatioRZ);
            VelRatio = agvmGetRatioByVelLimit(AxisVelLimit, 
                        AGVM_Cartesian2Wheels_1.UL,
                        AGVM_Cartesian2Wheels_1.UR,
                        AGVM_Cartesian2Wheels_1.LL,
                        AGVM_Cartesian2Wheels_1.LR);
            printf("AMR velocity-0: %f, %f, %f, %f\n", AGVM_Cartesian2Wheels_1.UL,
                                                       AGVM_Cartesian2Wheels_1.UR, 
                                                       AGVM_Cartesian2Wheels_1.LL,
                                                       AGVM_Cartesian2Wheels_1.LR);
            MoveRel = true;
            move_rel = false;
            SHM_RelMove = false;
            SHM_RelMoveBusy = true;
            Mode = 10;
          }
          else
          {
            printf("AMR velocity-1: %f, %f, %f\n", TransX, TransY, TransRZ);
            AGVM_Cartesian2Wheels_1.call(TransX, TransY, TransRZ);
            VAxisULVel = AGVM_Cartesian2Wheels_1.UL;
            VAxisURVel = AGVM_Cartesian2Wheels_1.UR;
            VAxisLLVel = AGVM_Cartesian2Wheels_1.LL;
            VAxisLRVel = AGVM_Cartesian2Wheels_1.LR;

            VelRatio = agvmGetRatioByVelLimit(AxisVelLimit, VAxisULVel, VAxisURVel, VAxisLLVel, VAxisLRVel);
            // if (VelRatio > 1.0)
            //   VelRatio = 1.0;
            VelRatio = 1.0;
            // printf("VelRatio: %f\n", VelRatio);
            double axis_vel[AXIS_NUM] = {VAxisULVel, VAxisURVel, VAxisLLVel, VAxisLRVel};
            for (size_t i = 0; i < AXIS_NUM; i++)
            {
              if (axis_vel[i] == 0.0)
              {
                if(newSignal)
                {
                  mc_halt[i].setExecute(mcFALSE);
                  mc_halt[i].runCycle();
                  mc_halt[i].setDeceleration(AxisAccLimit);
                }
                mc_halt[i].setExecute(mcTRUE);
                mc_halt[i].runCycle();
              }
              else
              {
                printf("Wheels axis_vel[%zu]: %f\n", i, axis_vel[i] * VelRatio);
                if(newSignal)
                {
                  mc_move_velocity[i].setExecute(mcFALSE);
                  mc_move_velocity[i].runCycle();
                  mc_move_velocity[i].setVelocity(axis_vel[i] * VelRatio);
                  mc_move_velocity[i].setAcceleration(AxisAccLimit);
                  mc_move_velocity[i].setDeceleration(AxisAccLimit);
                  mc_move_velocity[i].setJerk(10);
                }
                mc_move_velocity[i].setExecute(mcTRUE);
                mc_move_velocity[i].runCycle();
              }
            }
          }
        }
        break;
      case 10:
        {
          printf("Mode 10\n");
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

            X = AGVM_2DRotate_1.OutX / RatioX - AGVM_2DRotate_1.OutY * YXImpact;
            Y = AGVM_2DRotate_1.OutY / RatioY - AGVM_2DRotate_1.OutX * XYImpact;
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
          printf("Mode 20\n");
          if (!MoveRel)
            Mode = 0;
        }
        break;
      case 100:
        {
          printf("Mode 100\n");
          for (size_t i = 0; i < AXIS_NUM; i++)
          {
            mc_halt[i].setExecute(mcTRUE);
            mc_halt[i].setDeceleration(AxisAccLimit);
            mc_halt[i].runCycle();
          }

          if (mc_halt[0].isBusy() == mcFALSE && mc_halt[1].isBusy() == mcFALSE && 
              mc_halt[2].isBusy() == mcFALSE && mc_halt[3].isBusy() == mcFALSE)
            Mode = 0;
        }
        break;
      default:
          Mode = 0;
        break;
      }
    }

    for (size_t i = 0; i < AXIS_NUM; i++)
    {
      mc_read_actual_velocity[i].runCycle();
    }

    /* Compute pose and velocity */
    AGVM_Wheels2Cartesian_1.call(mc_read_actual_velocity[0].getFloatValue(),
                                 -mc_read_actual_velocity[1].getFloatValue(),
                                 mc_read_actual_velocity[2].getFloatValue(),
                                 -mc_read_actual_velocity[3].getFloatValue());
    printf("Wheels velocity-2: %f, %f, %f, %f\n", 
              mc_read_actual_velocity[0].getFloatValue(),
              mc_read_actual_velocity[1].getFloatValue(),
              mc_read_actual_velocity[2].getFloatValue(),
              mc_read_actual_velocity[3].getFloatValue());

    SHM_VelX = AGVM_Wheels2Cartesian_1.VelX;
    SHM_VelY = AGVM_Wheels2Cartesian_1.VelY;
    SHM_VelRZ = AGVM_Wheels2Cartesian_1.VelRZ;

    printf("AMR velocity: %f, %f, %f\n", SHM_VelX, SHM_VelY, SHM_VelRZ);
    
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

    printf("AMR pose: %f, %f, %f\n\n", SHM_PosX, SHM_PosY, SHM_PosRZ);

    mc_read_axis_error[0].setEnable(mcTRUE);
    mc_read_axis_error[0].runCycle();
    AxisULErr = mc_read_axis_error[0].getErrorID();

    mc_read_axis_error[1].setEnable(mcTRUE);
    mc_read_axis_error[1].runCycle();
    AxisURErr = mc_read_axis_error[1].getErrorID();

    mc_read_axis_error[2].setEnable(mcTRUE);
    mc_read_axis_error[2].runCycle();
    AxisLLErr = mc_read_axis_error[2].getErrorID();

    mc_read_axis_error[3].setEnable(mcTRUE);
    mc_read_axis_error[3].runCycle();
    AxisLRErr = mc_read_axis_error[3].getErrorID();

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

    /* Capture estop signal */
    if((ec_motor0.stat >> 30 | 0x0)  == 1  ){
      printf("Please release the emergency button and try again\n");
      EC_WRITE_U32(domain_pd+ec_slave0.control,0x100);
    }

    if (stop_motor == 1)
    {
      for (size_t i = 0; i < AXIS_NUM; i++)
        servos[i]->emergStop();
    }
    ethercat_send();

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
  return NULL;
}

static void getOptions(int argc, char**argv)
{
    int index;
    static struct option longOptions[] = {
        //name		has_arg				flag	val
        {"velocity",	required_argument,	NULL,	'v'},
        {"relative",    required_argument,	NULL,	'r'},
        {"x",    required_argument,	NULL,	'x'},
        {"y",    required_argument,	NULL,	'y'},
        {"z",    required_argument,	NULL,	'z'},
        {"help",	no_argument,		NULL,	'h'},
        {}
    };
    do {
        index = getopt_long(argc, argv, "vrxyz:h", longOptions, NULL);
        switch(index){
            case 'v':
                move_vel = true;
                printf("Velocity Move Mode\n");
                break;
            case 'r':
                move_rel = true;
                printf("Relative Move Mode\n");
                break;
            case 'x':
                move_x = atof(optarg);
                printf("Move along X: %f\n", move_x);
                break;
            case 'y':
                move_y = atof(optarg);
                printf("Move along Y: %f\n", move_y);
                break;
            case 'z':
                move_rz = atof(optarg);
                printf("Rotate around Z: %f\n", move_rz);
                break;
            case 'h':
                printf("Global options:\n");
                printf("    --velocity  -v  Set velocity move mode \n");
                printf("    --relative  -r  Set relative move mode \n");
                printf("    --x         -x  Move value along x axis \n");
                printf("    --y         -y  Move value along y axis \n");
                printf("    --z         -z  Rotate value aroung z axis \n");
                printf("    --help      -h  Show this help.\n");
                exit(0);
                break;
        }
    } while(index != -1);
}

/****************************************************************************
 * Main function
 ***************************************************************************/
int main(int argc, char* argv[])
{
  getOptions(argc, argv);
  auto signal_handler = [](int){
    stop_motor = 1; sleep(1); run = 0; };
  signal(SIGTERM, signal_handler);
  signal(SIGINT, signal_handler);
  mlockall(MCL_CURRENT | MCL_FUTURE);

  ethercat_init();

  static EcrtServo* servo_ul = new EcrtServo();
  static EcrtServo* servo_ur = new EcrtServo();
  static EcrtServo* servo_ll = new EcrtServo();
  static EcrtServo* servo_lr = new EcrtServo();

  servo_ul->setDomain(domain_pd);
  servo_ur->setDomain(domain_pd);
  servo_ll->setDomain(domain_pd);
  servo_lr->setDomain(domain_pd);

  servo_ul->setId(UL);
  servo_ur->setId(UR);
  servo_ll->setId(LL);
  servo_lr->setId(LR);

  servo_ul->setControlSlaveData(&ec_motor0, &ec_slave0);
  servo_ur->setControlSlaveData(&ec_motor0, &ec_slave0);
  servo_ll->setControlSlaveData(&ec_motor0, &ec_slave0);
  servo_lr->setControlSlaveData(&ec_motor0, &ec_slave0);

  servos[0] = (Servo*)servo_ul;
  servos[1] = (Servo*)servo_ur;
  servos[2] = (Servo*)servo_ll;
  servos[3] = (Servo*)servo_lr;
  // for(size_t i=0;i<AXIS_NUM;i++)
  //   servos[i] = std::make_shared<Servo>();

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
  ecrt_release_master(master);
  delete servo_ul;
  delete servo_ur;
  delete servo_ll;
  delete servo_lr;
  for (size_t i = 0; i < AXIS_NUM; i ++)
    delete axis[i];
  printf("\nEnd of Program\n");
  return 0;
}

/****************************************************************************/
