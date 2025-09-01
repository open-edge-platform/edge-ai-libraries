// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file rt.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */
#include <fb/common/include/axis.hpp>
#include <fb/public/include/fb_move_relative.hpp>
#include <fb/public/include/fb_power.hpp>
#include <fb/public/include/fb_move_absolute.hpp>
#include <fb/private/include/fb_set_position.hpp>
#include <fb/public/include/fb_read_actual_position.hpp>
#include <fb/public/include/fb_read_actual_velocity.hpp>
#include <fb/common/include/global.hpp>
#include <ecrt_config.hpp>
#include <ecrt_servo.hpp>
#include <errno.h>
#include <error.h>
#include <getopt.h>
#include <limits.h>
#include <motionentry.h>
#include <mqueue.h>
#include <pthread.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/sysinfo.h>
#include <sys/time.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>
#include <cstdio>
#include <thread>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <pthread.h>
#include <getopt.h>
#include <math.h>
#include <execinfo.h>
#include <unistd.h>
#include <shmringbuf.h>


/* Shm related data types
 * s_buf, handle_s: data sent from RT domain
 * r_buf, handle_r: data sent to RT domain
 */
#define MSG_LEN 150000
#define JOINT_NUM 6
#define POINT_NUM 100
static char s_buf[MSG_LEN];
static char r_buf[MSG_LEN];
static shm_handle_t handle_s, handle_r;


struct TrajPoint
{
  double positions[JOINT_NUM] = {};
  double velocities[JOINT_NUM] = {};
  double accelerations[JOINT_NUM] = {};
  double effort[JOINT_NUM] = {};
  double time_from_start;
};

struct TrajCmd
{
  uint32_t point_num = 0;
  TrajPoint points[POINT_NUM]= {};
};

struct JointState
{
  double joint_pos[JOINT_NUM] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
  double joint_vel[JOINT_NUM] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
  bool traj_done = false;
  bool error = false;
};

#define CONVEYOR_RATIO (2.0 * M_PI)
#define SERVO_ENCODER_ACCURACY (0x400000)
#define NSEC_PER_SEC (1000000000L)
#ifndef DIFF_NS
#define DIFF_NS(A,B)    		(((B).tv_sec - (A).tv_sec)*NSEC_PER_SEC + ((B).tv_nsec)-(A).tv_nsec)
#endif
static volatile int run = 1;
static pthread_t cyclic_thread, log_thread;
static int cpu_id       = 1;
// static unsigned int count = 0;
static TrajCmd traj_cmd;
static JointState joint_state;

/* RT to NRT data */
struct TimeStat
{
  int64_t latency_ns_rt     = 0;
  uint64_t cycle_count_rt   = 0;
  uint64_t cycle_poweron_rt = 0;
  uint64_t exec_time_rt     = 0;
  uint64_t recv_time_rt     = 0;
  uint64_t calc_time_rt     = 0;
  uint64_t send_time_rt     = 0;
  uint64_t l2_hit_rt        = 0;
  uint64_t l2_miss_rt       = 0;
  uint64_t l3_hit_rt        = 0;
  uint64_t l3_miss_rt       = 0;
  uint32_t dc_diff_rt       = 0;
  uint64_t instr_count_rt   = 0;
};

/* Time domain statistics */
#define MEM_BLK_NUM 2
static int64_t latency_min_ns                 = 1000000;
static int64_t latency_max_ns                 = -1000000;
static int64_t latency_avg_ns                 = 0;
static uint64_t exec_min_ns                   = 1000000;
static uint64_t exec_max_ns                   = 0;
static uint64_t exec_avg_ns                   = 0;
static uint64_t cycle_count                   = 0;
static uint64_t cycle_poweron                 = 0;
static uint64_t spike_count                   = 0;
static uint64_t spike_max                     = 0;
static int64_t* latency_ptr[MEM_BLK_NUM]      = { nullptr };
static int64_t* exec_time_ptr[MEM_BLK_NUM]    = { nullptr };
static int64_t* recv_time_ptr[MEM_BLK_NUM]    = { nullptr };
static int64_t* calc_time_ptr[MEM_BLK_NUM]    = { nullptr };
static int64_t* send_time_ptr[MEM_BLK_NUM]    = { nullptr };
static uint64_t* l2_hit_ptr[MEM_BLK_NUM]      = { nullptr };
static uint64_t* l2_miss_ptr[MEM_BLK_NUM]     = { nullptr };
static uint64_t* l3_hit_ptr[MEM_BLK_NUM]      = { nullptr };
static uint64_t* l3_miss_ptr[MEM_BLK_NUM]     = { nullptr };
static uint32_t* dc_diff_ptr[MEM_BLK_NUM]     = { nullptr };
static uint64_t* instr_count_ptr[MEM_BLK_NUM] = { nullptr };
static bool save_to_file                      = false;
static uint8_t save_to_file_id                = 0;
static uint8_t save_to_mem_id                 = 0;

/* Ethercat master related */
static servo_master* master = nullptr;
static uint8_t* domain1;
static void* domain;
static bool servo_ready = false;

/* Command line arguments */
static char* eni_file         = nullptr;
static bool verbose           = false;
static bool log_data          = false;
static bool output            = false;
static bool real_servo        = false;
static bool cache_stat_enable = false;
static unsigned int cycle_us  = 1000;
static unsigned int spike     = 250;
// static unsigned int axis_num  = 6;
static int trace_limit        = 0;
static bool count_instruction = false;

/* Record and output to file */
static double running_time_t = 0;
static unsigned int running_cycle_all =
    (unsigned int)(CYCLE_COUNTER_PERSEC(cycle_us) * running_time_t);
static unsigned int running_cycle_30min =
    (unsigned int)(CYCLE_COUNTER_PERSEC(cycle_us) * 1800);
static unsigned int recorded_cycle = 0;
static char* log_late_file         = nullptr;
static char* log_exec_file         = nullptr;
static char* log_recv_file         = nullptr;
static char* log_calc_file         = nullptr;
static char* log_send_file         = nullptr;
static char* log_l2_miss_file      = nullptr;
static char* log_l3_miss_file      = nullptr;
static char* log_dc_diff_file      = nullptr;
static char* log_instruction_file  = nullptr;
enum LOGTYPE
{
  LOGINT64,
  LOGUINT64,
  LOGUINT32,
};

using namespace RTmotion;

/* Get the PMU counter value */
__attribute__((always_inline)) inline uint64_t __rdmpc(uint32_t counter)
{
  volatile uint32_t high, low;
  asm volatile("rdpmc\n\t" : "=a"(low), "=d"(high) : "c"(counter));
  return (((uint64_t)high << 32) | low);
}

static int init_ethercat_master()
{
  /* Create EtherCAT master by ENI*/
  if (real_servo)
  {
    if (!eni_file)
    {
      printf("Error: Unspecify ENI/XML file\n");
      exit(0);
    }
    master = motion_servo_master_create(eni_file);
    free(eni_file);
    eni_file = nullptr;
    if (master == nullptr)
      return 1;

    /* Motion domain_ create */
    if (motion_servo_domain_entry_register(master, &domain))
      return 1;

    if (!motion_servo_driver_register(master, domain))
      return 1;

    motion_servo_set_send_interval(master);
    motion_servo_register_dc(master);
    struct timespec dc_period;
    clock_gettime(CLOCK_MONOTONIC, &dc_period);
    motion_master_set_application_time(master, TIMESPEC2NS(dc_period));

    if (motion_servo_master_activate(master->master))
    {
      printf("fail to activate master_\n");
      return 1;
    }

    domain1 = motion_servo_domain_data(domain);
    if (!domain1)
    {
      printf("fail to get domain_ data\n");
      return 1;
    }
  }

  return 0;
}

static void init_rtmotion(Servo** servo, EcrtServo** my_servo,
                          AxisConfig** config, AXIS_REF* axis,
                          FbPower** fbPower, FbReadActualPosition** readPos,
                          FbReadActualVelocity** readVel,FbSetPosition** fb_set_position,
                          FbMoveAbsolute** moveAbs)
{
  for (size_t i = 0; i < JOINT_NUM; i++)
  {
    if (real_servo)  // Using real servo
    {
      my_servo[i] = new EcrtServo();
      my_servo[i]->setMaster(master);
      my_servo[i]->setDomain(domain1);
      my_servo[i]->initialize(0, i);
      servo[i] = (Servo*)my_servo[i];
    }
    else  // Using virtual servo
      servo[i] = new Servo();

    config[i] = new AxisConfig();
    config[i]->encoder_count_per_unit_ =
        SERVO_ENCODER_ACCURACY / CONVEYOR_RATIO;
    config[i]->frequency_ = 1.0 / cycle_us * 1000000;

    axis[i] = new Axis();
    axis[i]->setAxisId(i);
    axis[i]->setAxisConfig(config[i]);
    axis[i]->setServo(servo[i]);

    fbPower[i] = new FbPower();
    fbPower[i]->setAxis(axis[i]);
    fbPower[i]->setEnable(mcTRUE);
    fbPower[i]->setEnablePositive(mcTRUE);
    fbPower[i]->setEnableNegative(mcTRUE);

    readPos[i] = new FbReadActualPosition();
    readPos[i]->setAxis(axis[i]);
    readPos[i]->setEnable(mcTRUE);

    readVel[i] = new FbReadActualVelocity();
    readVel[i]->setAxis(axis[i]);
    readVel[i]->setEnable(mcTRUE);

    fb_set_position[i] = new FbSetPosition();
    fb_set_position[i]->setAxis(axis[i]);
    fb_set_position[i]->setMode(mcSetPositionModeRelative);
    fb_set_position[i]->setPosition(0);
    fb_set_position[i]->setEnable(mcFALSE);

    moveAbs[i] = new FbMoveAbsolute();
    moveAbs[i]->setAxis(axis[i]);
    moveAbs[i]->setPosition(0.0);
    moveAbs[i]->setVelocity(2.618);
    moveAbs[i]->setAcceleration(1.0);
    moveAbs[i]->setDeceleration(1.0);
    moveAbs[i]->setJerk(50.0);
    moveAbs[i]->setBufferMode(RTmotion::mcAborting);
    
  }
}

static void clear_rtmotion(Servo** servo, EcrtServo** my_servo,
                           AxisConfig** config, AXIS_REF* axis,
                           FbPower** fbPower, FbReadActualPosition** readPos,
                           FbReadActualVelocity** readVel,FbSetPosition** fb_set_position,
                          FbMoveAbsolute** moveAbs)
{
  for (size_t i = 0; i < JOINT_NUM; i++)
  {
    delete config[i];
    if (real_servo)
      delete my_servo[i];
    else
      delete servo[i];
    delete axis[i];
    delete fbPower[i];
    delete readPos[i];
    delete readVel[i];
    delete fb_set_position[i];
    delete moveAbs[i];
  }
}

static void process_data(TimeStat* stat)
{
  /* Record only if execution time is less than spike value */
  if (stat->exec_time_rt < spike * 1000)
  {
    /* Latency min, avg, max */
    latency_avg_ns += fabs(stat->latency_ns_rt);
    if (stat->latency_ns_rt > latency_max_ns)
      latency_max_ns = stat->latency_ns_rt;
    if (stat->latency_ns_rt < latency_min_ns)
      latency_min_ns = stat->latency_ns_rt;

    /* Exect time min, avg, max */
    exec_avg_ns += fabs(stat->exec_time_rt);
    if (stat->exec_time_rt > exec_max_ns)
      exec_max_ns = stat->exec_time_rt;
    if (stat->exec_time_rt < exec_min_ns)
      exec_min_ns = stat->exec_time_rt;

    /* Save RT data to memory array */
    if (recorded_cycle < running_cycle_30min)
    {
      latency_ptr[save_to_mem_id][recorded_cycle]     = stat->latency_ns_rt;
      exec_time_ptr[save_to_mem_id][recorded_cycle]   = stat->exec_time_rt;
      recv_time_ptr[save_to_mem_id][recorded_cycle]   = stat->recv_time_rt;
      calc_time_ptr[save_to_mem_id][recorded_cycle]   = stat->calc_time_rt;
      send_time_ptr[save_to_mem_id][recorded_cycle]   = stat->send_time_rt;
      l2_hit_ptr[save_to_mem_id][recorded_cycle]      = stat->l2_hit_rt;
      l2_miss_ptr[save_to_mem_id][recorded_cycle]     = stat->l2_miss_rt;
      l3_hit_ptr[save_to_mem_id][recorded_cycle]      = stat->l3_hit_rt;
      l3_miss_ptr[save_to_mem_id][recorded_cycle]     = stat->l3_miss_rt;
      dc_diff_ptr[save_to_mem_id][recorded_cycle]     = stat->dc_diff_rt;
      instr_count_ptr[save_to_mem_id][recorded_cycle] = stat->instr_count_rt;

      recorded_cycle++;
    }
    else
    {
      save_to_file   = true;
      recorded_cycle = 0;
      save_to_mem_id++;
      if (save_to_mem_id == MEM_BLK_NUM)
        save_to_mem_id = 0;

      latency_ptr[save_to_mem_id][recorded_cycle]     = stat->latency_ns_rt;
      exec_time_ptr[save_to_mem_id][recorded_cycle]   = stat->exec_time_rt;
      recv_time_ptr[save_to_mem_id][recorded_cycle]   = stat->recv_time_rt;
      calc_time_ptr[save_to_mem_id][recorded_cycle]   = stat->calc_time_rt;
      send_time_ptr[save_to_mem_id][recorded_cycle]   = stat->send_time_rt;
      l2_hit_ptr[save_to_mem_id][recorded_cycle]      = stat->l2_hit_rt;
      l2_miss_ptr[save_to_mem_id][recorded_cycle]     = stat->l2_miss_rt;
      l3_hit_ptr[save_to_mem_id][recorded_cycle]      = stat->l3_hit_rt;
      l3_miss_ptr[save_to_mem_id][recorded_cycle]     = stat->l3_miss_rt;
      dc_diff_ptr[save_to_mem_id][recorded_cycle]     = stat->dc_diff_rt;
      instr_count_ptr[save_to_mem_id][recorded_cycle] = stat->instr_count_rt;
    }
  }
  else  // Record abnormal spikes number and max value
  {
    spike_count++;
    if (stat->exec_time_rt > spike_max)
      spike_max = stat->exec_time_rt;
  }
  cycle_count   = stat->cycle_count_rt;
  cycle_poweron = stat->cycle_poweron_rt;
}

/* Motion control thread function */
void* rt_func(void* arg)
{
  /* Timestamps used for cycle */
  struct timespec next_period, dc_period;

  /* Variables used for time recording */
  struct TimeStat* stat           = (struct TimeStat*)arg;
  struct timespec start_time      = { 0, 0 };
  struct timespec last_start_time = { 0, 0 };
  struct timespec end_time        = { 0, 0 };
  struct timespec recv_start = { 0, 0 }, recv_end = { 0, 0 };
  struct timespec calc_start = { 0, 0 }, calc_end = { 0, 0 };
  struct timespec send_start = { 0, 0 }, send_end = { 0, 0 };
  int64_t latency_ns, latency_ns_prev             = 0;
  uint64_t cycle_count = 0;


  /* Init EtherCAT master */
  int ret = init_ethercat_master();
  if (ret)
  {
    run = 0;
    return nullptr;
  }
  servo_ready = true;

  /* RTmotion variables */
  Servo* servo[JOINT_NUM];
  EcrtServo* my_servo[JOINT_NUM];
  AxisConfig* config[JOINT_NUM];
  AXIS_REF axis[JOINT_NUM];
  FbPower* fb_power[JOINT_NUM];
  FbReadActualPosition* read_pos[JOINT_NUM];
  FbReadActualVelocity* read_vel[JOINT_NUM];
  FbSetPosition* fb_set_position[JOINT_NUM];
  FbMoveAbsolute* move_abs[JOINT_NUM];

  /* RTmotion variables */
  init_rtmotion(servo, my_servo, config, axis, fb_power, read_pos, read_vel,fb_set_position, move_abs);
  INFO_PRINT("Function blocks initialized.\n");

  /* Variables used for reading cache PMU counters */
  uint64_t cnt0_0 = 0, cnt0_1 = 0, cnt1_0 = 0, cnt1_1 = 0, cnt2_0 = 0,
           cnt2_1 = 0, cnt3_0 = 0, cnt3_1 = 0;

  //__itt_pt_region region_total = __itt_pt_region_create("region_total");

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

  /* Init cache miss variables */
  if (cache_stat_enable)
  {
    cnt0_0 = cnt0_1 = __rdpmc(0);  // L2.HIT
    cnt1_0 = cnt1_1 = __rdpmc(1);  // L2.MISS
    cnt2_0 = cnt2_1 = __rdpmc(2);  // L3.HIT
    cnt3_0 = cnt3_1 = __rdpmc(3);  // L3.MISS
  }

  /* Start motion cycles */
  clock_gettime(CLOCK_MONOTONIC, &next_period);
  last_start_time = next_period;
  struct timespec  traj_start_time, traj_current_time;
  unsigned int index = 0;
  bool traj_start = false;
  while (run)
  {
    next_period.tv_nsec += cycle_us * 1000;
    while (next_period.tv_nsec >= NSEC_PER_SEC)
    {
      next_period.tv_nsec -= NSEC_PER_SEC;
      next_period.tv_sec++;
    }
    clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &next_period, nullptr);

    /* Benchmarking for jitter and motion execution latency */
    clock_gettime(CLOCK_MONOTONIC, &start_time);
    latency_ns = DIFF_NS(next_period, start_time);

    if (cycle_count > running_cycle_all)
      run = 0;

    /* Copy the data */
    if (cycle_count > 0)
    {
      stat->latency_ns_rt  = latency_ns_prev;
      stat->cycle_count_rt = cycle_count;
      stat->exec_time_rt   = DIFF_NS(last_start_time, end_time);
      stat->recv_time_rt   = DIFF_NS(recv_start, recv_end);
      stat->calc_time_rt   = DIFF_NS(calc_start, calc_end);
      stat->send_time_rt   = DIFF_NS(send_start, send_end);
      stat->l2_hit_rt      = cnt0_1 - cnt0_0;
      stat->l2_miss_rt     = cnt1_1 - cnt1_0;
      stat->l3_hit_rt      = cnt2_1 - cnt2_0;
      stat->l3_miss_rt     = cnt3_1 - cnt3_0;

      process_data(stat);
    }
    latency_ns_prev = latency_ns;
    last_start_time = start_time;
    cnt0_0          = cnt0_1;
    cnt1_0          = cnt1_1;
    cnt2_0          = cnt2_1;
    cnt3_0          = cnt3_1;

    //__itt_mark_pt_region_begin(region_total);

    /* Update ethercat data */
    clock_gettime(CLOCK_MONOTONIC, &recv_start);
    if (real_servo)
    {
      motion_servo_recv_process(master->master, static_cast<uint8_t*>(domain));
      if (running_time_t)
        stat->dc_diff_rt = motion_servo_sync_monitor_process(master->master);
    }
    clock_gettime(CLOCK_MONOTONIC, &recv_end);


    clock_gettime(CLOCK_MONOTONIC, &calc_start);

    /* Get the trajectory commands */
    if (!shm_blkbuf_empty(handle_r))
    {
      ret = shm_blkbuf_read(handle_r, r_buf, sizeof(r_buf));
      if (ret) 
      {
        clock_gettime(CLOCK_MONOTONIC, &traj_start_time);
        index = 0;
        traj_start = true;
        joint_state.traj_done = false;
        memcpy(&traj_cmd, r_buf, sizeof(traj_cmd));
        DEBUG_PRINT("Received the trajectory command.\n");
        for (size_t i = 0; i < traj_cmd.point_num; i++)
        {
          DEBUG_PRINT("The %ldth point: ", i);
          for (size_t j = 0; j < JOINT_NUM; j++)
            DEBUG_PRINT(" %f", traj_cmd.points[i].positions[j]);
          DEBUG_PRINT("\n");
        }
      }
    }
    
    for (size_t i = 0; i < JOINT_NUM; i++)
    {
      axis[i]->runCycle();
      fb_power[i]->runCycle();
      fb_set_position[i]->runCycle();
      read_pos[i]->runCycle();
      read_vel[i]->runCycle();
    }

    /* Print axis pos and vel when verbose enabled */
    if (verbose)
    {
      for (size_t i = 0; i < JOINT_NUM; i++)
      {
        printf("Current position - %ld: %f,\tvelocity: %f\n", i,
               read_pos[i]->getFloatValue(), read_vel[i]->getFloatValue());
      }
    }

    /* Trigger axis movement when all axis are powered on */
    mcBOOL power_on = mcTRUE;
    for (size_t i = 0; i < JOINT_NUM; i++)
      power_on = (power_on == mcTRUE) &&
                         (fb_power[i]->getPowerStatus() == mcTRUE) ?
                     mcTRUE :
                     mcFALSE;

    if (power_on == mcTRUE)
    {
      for (size_t i = 0; i < JOINT_NUM; i++)
      {
        fb_set_position[i]->setEnable(mcTRUE);
        move_abs[i]->setExecute(mcTRUE);
      }

      if (!stat->cycle_poweron_rt)
        stat->cycle_poweron_rt = cycle_count;
    }

     /* Execute the trajectory */
    clock_gettime(CLOCK_MONOTONIC, &traj_current_time);
    if (traj_start)
    {
      if (DIFF_NS(traj_start_time, traj_current_time) >= traj_cmd.points[index].time_from_start)
      {
        DEBUG_PRINT("duration %ld, waypoint time: %f\n", DIFF_NS(traj_start_time, traj_current_time), traj_cmd.points[index].time_from_start);
        if (index < traj_cmd.point_num)
        {
          // Un-trigger the function block execution
          for (size_t i = 0; i < JOINT_NUM; i++)
          {
            move_abs[i]->setExecute(mcFALSE);
            move_abs[i]->runCycle();
          }

          // Trigger the function block execution
          for (size_t i = 0; i < JOINT_NUM; i ++)
          {
            move_abs[i]->setPosition(traj_cmd.points[index].positions[i]);
            move_abs[i]->setExecute(mcTRUE);
            move_abs[i]->runCycle();
          }
          
          index++;
        }
        else
        {
          bool done = true;
          for (size_t i = 0; i < JOINT_NUM; i ++)
          {
            done &= move_abs[i]->isDone() == mcTRUE;
            DEBUG_PRINT("%ldth FB is done: %d\n", i, static_cast<int>(move_abs[i]->isDone()));
          }

          if (done)
          {
            for (size_t i = 0; i < JOINT_NUM; i++)
              DEBUG_PRINT("%ldth axis: %f\n", i, read_pos[i]->getFloatValue());
            joint_state.traj_done = true;
            traj_start = false;
            DEBUG_PRINT("Trajectory done.\n");
          }
        }
      }
    }
    

    /* Update joint states */
    for (size_t i = 0; i < JOINT_NUM; i++)
      if (power_on == mcTRUE)
        joint_state.joint_pos[i] = read_pos[i]->getFloatValue();

    memcpy(s_buf, &joint_state, sizeof(joint_state));
    if (!shm_blkbuf_full(handle_s))
    {
      ret = shm_blkbuf_write(handle_s, s_buf, sizeof(s_buf));
      DEBUG_PRINT("%s: sent %d bytes\n", __FUNCTION__, ret);
    }
  
    clock_gettime(CLOCK_MONOTONIC, &calc_end);

    /* Send EtherCAT data */
    clock_gettime(CLOCK_MONOTONIC, &dc_period);
    send_start = dc_period;
    if (real_servo)
    {
      motion_servo_sync_dc(master->master,
                           TIMESPEC2NS(dc_period));  // Sync EtherCAT DC
      motion_servo_sync_monitor_process(master->master);
      motion_servo_send_process(master->master, static_cast<uint8_t*>(domain));
    }

    /* Update cache count */
    if (cache_stat_enable)
    {
      cnt0_1 = __rdpmc(0);
      cnt1_1 = __rdpmc(1);
      cnt2_1 = __rdpmc(2);
      cnt3_1 = __rdpmc(3);
    }

    clock_gettime(CLOCK_MONOTONIC, &end_time);
    send_end = end_time;
    cycle_count++;
  }

  /* Clean up */
  clear_rtmotion(servo, my_servo, config, axis, fb_power, read_pos, read_vel, fb_set_position, move_abs);

  return nullptr;
}

void save_log(void* data_ptr, unsigned int len, LOGTYPE type, char* log_file)
{
  FILE* fptr;

  // Open file
  // printf("Opening file \"%s\".\n", log_file);
  if ((fptr = fopen(log_file, "a")) == nullptr)
  {
    printf("Error when open file \"%s\".\n", log_file);
    return;
  }
  // printf("Opening file \"%s\" done.\n", log_file);

  if (len > running_cycle_30min)
  {
    printf("Error! Writing length larger than the max arry size.\n");
    fclose(fptr);
    return;
  }

  // Write data
  for (size_t i = 0; i < len; ++i)
  {
    switch (type)
    {
      case LOGINT64: {
        int64_t* data = (int64_t*)data_ptr;
        fprintf(fptr, "%ld\n", data[i]);
        break;
      }
      case LOGUINT64: {
        uint64_t* data = (uint64_t*)data_ptr;
        fprintf(fptr, "%ld\n", data[i]);
        break;
      }
      case LOGUINT32: {
        int32_t* data = (int32_t*)data_ptr;
        fprintf(fptr, "%d\n", data[i]);
        break;
      }
      default:
        break;
    }
  }

  fclose(fptr);
}

void* log_func(void* /*arg*/)
{
  while (run)
  {
    /* Save log every 30 mins */
    if (log_data)
    {
      if (save_to_file)
      {
        save_log(latency_ptr[save_to_file_id], running_cycle_30min, LOGINT64,
                 log_late_file);
        save_log(exec_time_ptr[save_to_file_id], running_cycle_30min, LOGINT64,
                 log_exec_file);
        save_log(recv_time_ptr[save_to_file_id], running_cycle_30min, LOGINT64,
                 log_recv_file);
        save_log(calc_time_ptr[save_to_file_id], running_cycle_30min, LOGINT64,
                 log_calc_file);
        save_log(send_time_ptr[save_to_file_id], running_cycle_30min, LOGINT64,
                 log_send_file);
        save_log(l2_miss_ptr[save_to_file_id], running_cycle_30min, LOGUINT64,
                 log_l2_miss_file);
        save_log(l3_miss_ptr[save_to_file_id], running_cycle_30min, LOGUINT64,
                 log_l3_miss_file);
        save_log(dc_diff_ptr[save_to_file_id], running_cycle_30min, LOGUINT32,
                 log_dc_diff_file);
        save_log(instr_count_ptr[save_to_file_id], running_cycle_30min,
                 LOGUINT64, log_instruction_file);

        save_to_file_id++;
        if (save_to_file_id >= MEM_BLK_NUM)
          save_to_file_id = 0;

        save_to_file = false;
      }
    }

    usleep(cycle_us * 10);
  }

  return nullptr;
}

/* Logging thread funtion */
static void print_stat()
{
  char* fmt_data = nullptr;

  if (output)
  {
    fmt_data = (char*)"\r%10ld [%10.3f,%10.3f,%10.3f] [%10.3f,%10.3f,%10.3f] "
                      "[%10ld,%7.3f] %14ld";
    printf(fmt_data, cycle_count / CYCLE_COUNTER_PERSEC(cycle_us),
           (float)latency_min_ns / 1000,
           (float)latency_avg_ns / cycle_count / 1000,
           (float)latency_max_ns / 1000, (float)exec_min_ns / 1000,
           (float)exec_avg_ns / cycle_count / 1000, (float)exec_max_ns / 1000,
           spike_count, (float)spike_max / 1000, cycle_poweron);
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



void init_stat()
{
  for (size_t i = 0; i < MEM_BLK_NUM; i++)
  {
    latency_ptr[i] =
        (int64_t*)malloc(sizeof(int64_t) * uint(running_cycle_30min));
    memset(latency_ptr[i], 0, sizeof(int64_t) * uint(running_cycle_30min));
    exec_time_ptr[i] =
        (int64_t*)malloc(sizeof(int64_t) * uint(running_cycle_30min));
    memset(exec_time_ptr[i], 0, sizeof(int64_t) * uint(running_cycle_30min));
    recv_time_ptr[i] =
        (int64_t*)malloc(sizeof(int64_t) * uint(running_cycle_30min));
    memset(recv_time_ptr[i], 0, sizeof(int64_t) * uint(running_cycle_30min));
    calc_time_ptr[i] =
        (int64_t*)malloc(sizeof(int64_t) * uint(running_cycle_30min));
    memset(calc_time_ptr[i], 0, sizeof(int64_t) * uint(running_cycle_30min));
    send_time_ptr[i] =
        (int64_t*)malloc(sizeof(int64_t) * uint(running_cycle_30min));
    memset(send_time_ptr[i], 0, sizeof(int64_t) * uint(running_cycle_30min));
    l2_hit_ptr[i] =
        (uint64_t*)malloc(sizeof(uint64_t) * uint(running_cycle_30min));
    memset(l2_hit_ptr[i], 0, sizeof(uint64_t) * uint(running_cycle_30min));
    l2_miss_ptr[i] =
        (uint64_t*)malloc(sizeof(uint64_t) * uint(running_cycle_30min));
    memset(l2_miss_ptr[i], 0, sizeof(uint64_t) * uint(running_cycle_30min));
    l3_hit_ptr[i] =
        (uint64_t*)malloc(sizeof(uint64_t) * uint(running_cycle_30min));
    memset(l3_hit_ptr[i], 0, sizeof(uint64_t) * uint(running_cycle_30min));
    l3_miss_ptr[i] =
        (uint64_t*)malloc(sizeof(uint64_t) * uint(running_cycle_30min));
    memset(l3_miss_ptr[i], 0, sizeof(uint64_t) * uint(running_cycle_30min));
    dc_diff_ptr[i] =
        (uint32_t*)malloc(sizeof(uint32_t) * uint(running_cycle_30min));
    memset(dc_diff_ptr[i], 0, sizeof(uint32_t) * uint(running_cycle_30min));
    instr_count_ptr[i] =
        (uint64_t*)malloc(sizeof(uint64_t) * uint(running_cycle_30min));
    memset(instr_count_ptr[i], 0, sizeof(uint64_t) * uint(running_cycle_30min));
  }
}


/* Parse arguments */
static void getOptions(int argc, char** argv)
{
  int index;
  static struct option long_options[] = {
    // name           has_arg             flag   val
    { "eni_file", required_argument, nullptr, 'n' },
    { "interval", required_argument, nullptr, 'i' },
    { "cpu_affinity", required_argument, nullptr, 'a' },
    { "break_trace", required_argument, nullptr, 'b' },
    { "cache_stat", required_argument, nullptr, 'c' },
    { "run_time", required_argument, nullptr, 't' },
    { "log_file", no_argument, nullptr, 'l' },
    { "verbose", no_argument, nullptr, 'v' },
    { "spike", required_argument, nullptr, 's' },
    { "output", no_argument, nullptr, 'o' },
    { "real_servo", no_argument, nullptr, 'r' },
    { "open_perf", no_argument, nullptr, 'p' },
    { "help", no_argument, nullptr, 'h' },
    {}
  };
  do
  {
    index =
        getopt_long(argc, argv, "n:i:a:b:ct:lvs:orph", long_options, nullptr);
    switch (index)
    {
      case 'n':
        if (eni_file)
          free(eni_file);
        eni_file = static_cast<char*>(malloc(strlen(optarg) + 1));
        memset(eni_file, 0, strlen(optarg) + 1);
        memmove(eni_file, optarg, strlen(optarg) + 1);
        printf("Using EtherCAT eni file: %s\n", eni_file);
        break;
      case 'i':
        cycle_us = (unsigned int)atof(optarg);
        printf("Cycle-time: Set cycle time to %d (us)\n", cycle_us);
        break;
      case 'a':
        cpu_id = (unsigned int)atof(optarg);
        printf("CPU affinity: Set CPU affinity of rt thread to core %d\n",
               cpu_id);
        break;
      case 'b':
        trace_limit = atoi(optarg);
        printf("Break trace: break trace when schedule latency exceeds %d us\n",
               trace_limit);
        break;
      case 'c':
        cache_stat_enable = true;
        printf("Cache Statistic enabled.\n");
        break;
      case 't':
        running_time_t = atof(optarg);
        running_cycle_all =
            CYCLE_COUNTER_PERSEC(cycle_us) * (unsigned int)running_time_t;
        printf("Time: Set running time to %f (s)\n", running_time_t);
        printf("Time: Set running cycle number to %d\n", running_cycle_all);
        break;
      case 'l':
        log_data             = true;
        log_late_file        = (char*)"latency.log";
        log_exec_file        = (char*)"exec_time.log";
        log_recv_file        = (char*)"recv_time.log";
        log_calc_file        = (char*)"calc_time.log";
        log_send_file        = (char*)"send_time.log";
        log_l2_miss_file     = (char*)"l2_miss.log";
        log_l3_miss_file     = (char*)"l3_miss.log";
        log_dc_diff_file     = (char*)"dc_diff.log";
        log_instruction_file = (char*)"instruction.log";
        printf("Output latency to log file: %s\n", log_late_file);
        printf("Output execution time to log file: %s\n", log_exec_file);
        printf("Output message receive time to log file: %s\n", log_recv_file);
        printf("Output motion calculation time to log file: %s\n",
               log_calc_file);
        printf("Output message send time to log file: %s\n", log_send_file);
        printf("Output L2 Miss to log file: %s\n", log_l2_miss_file);
        printf("Output L3 Miss to log file: %s\n", log_l3_miss_file);
        printf("Output dc offset to log file: %s\n", log_dc_diff_file);
        printf("Output instruction count to log file: %s\n",
               log_instruction_file);
        break;
      case 'v':
        verbose = true;
        printf("verbose: print pos and vel values.\n");
        break;
      case 's':
        spike = (unsigned int)atof(optarg);
        printf("Spike: Set spike value to %d (us)\n", spike);
        break;
      case 'o':
        output = true;
        printf("Output: print time statistic in %d us cycle.\n", cycle_us * 10);
        break;
      case 'r':
        real_servo = true;
        printf("Real-servo: use real servo instead of virtual servo.\n");
        break;
      case 'p':
	count_instruction = true;
	printf("Open-perf: open perf to count instruction.\n");
	break;
      case 'h':
        printf("Global options:\n");
        printf("    --eni          -n  Specify ENI/XML file.\n");
        printf("    --interval     -i  Specify RT cycle time(us).\n");
        printf("    --affinity     -a  Specify RT thread CPU affinity.\n");
        printf(
            "    --break-trace  -b  Latency threshold (us) to break trace.\n");
        printf("    --cache        -c  Enable cache miss count.\n");
        printf("    --time         -t  Specify running time(s).\n");
        printf("    --log          -l  Enable output to log file.\n");
        printf("    --verbose      -v  Be verbose.\n");
        printf("    --spike        -s  Specify spike value(us).\n");
        printf("    --output       -o  Enable output in 10ms cycle.\n");
        printf("    --real-servo   -r  User real servo instead of virtual "
               "servo.\n");
        printf("    --help         -h  Show this help.\n");
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
      /* Initialize statistics struct */
  TimeStat stat = {};
  init_stat();

  /* Register signal */
  auto signal_handler = [](int /*unused*/) { run = 0; };
  signal(SIGTERM, signal_handler);
  signal(SIGINT, signal_handler);

  mlockall(MCL_CURRENT | MCL_FUTURE);
  handle_s = shm_blkbuf_init((char*)"rtsend", 16, MSG_LEN);
  handle_r = shm_blkbuf_init((char*)"rtread", 16, MSG_LEN);
  /* Create cyclic RT-thread */
  pthread_attr_t tattr;
  setup_sched_parameters(&tattr, 99);
  if (pthread_create(&cyclic_thread, &tattr, rt_func, &stat))
  {
    fprintf(stderr, "pthread_create cyclic task failed\n");
    pthread_attr_destroy(&tattr);
    return 1;
  }

  /* Create log thread */
  pthread_attr_t lattr;
  setup_sched_parameters(&lattr, 0);
  if (pthread_create(&log_thread, &lattr, log_func, nullptr))
  {
    fprintf(stderr, "pthread_create cyclic task failed\n");
    pthread_attr_destroy(&lattr);
    return 1;
  }

  /* Wait for servo to ready */
  while (!servo_ready)
  {
    usleep(1000);
  }

  /* Print output header */
  char* fmt_head;
  fmt_head = (char*)"    Dur(s) "
                    "           Sched_lat(us)          "
                    "           Exec_time(us)          "
                    "   Spike: num"
                    ",max(us)"
                    "  Power_on_cycle\n";
  printf("%s", fmt_head);

  /* Main loop to print stat */
  while (run)
  {
    print_stat();
    usleep(cycle_us * 10);
  }

  pthread_cancel(cyclic_thread);
  pthread_cancel(log_thread);
  pthread_join(cyclic_thread, nullptr);
  pthread_join(log_thread, nullptr);
  if (real_servo)
    motion_servo_master_release(master);


  /* Open file to write execution time record */
  if (log_data && recorded_cycle > 0)
  {
    save_log(latency_ptr[save_to_mem_id], recorded_cycle, LOGINT64,
             log_late_file);
    save_log(exec_time_ptr[save_to_mem_id], recorded_cycle, LOGINT64,
             log_exec_file);
    save_log(recv_time_ptr[save_to_mem_id], recorded_cycle, LOGINT64,
             log_recv_file);
    save_log(calc_time_ptr[save_to_mem_id], recorded_cycle, LOGINT64,
             log_calc_file);
    save_log(send_time_ptr[save_to_mem_id], recorded_cycle, LOGINT64,
             log_send_file);
    save_log(l2_miss_ptr[save_to_mem_id], recorded_cycle, LOGUINT64,
             log_l2_miss_file);
    save_log(l3_miss_ptr[save_to_mem_id], recorded_cycle, LOGUINT64,
             log_l3_miss_file);
    save_log(dc_diff_ptr[save_to_mem_id], recorded_cycle, LOGUINT32,
             log_dc_diff_file);
    save_log(instr_count_ptr[save_to_mem_id], recorded_cycle, LOGUINT64,
             log_instruction_file);
  }

  for (size_t i = 0; i < MEM_BLK_NUM; i++)
  {
    free(latency_ptr[i]);
    free(exec_time_ptr[i]);
    free(recv_time_ptr[i]);
    free(calc_time_ptr[i]);
    free(send_time_ptr[i]);
    free(l2_hit_ptr[i]);
    free(l2_miss_ptr[i]);
    free(l3_hit_ptr[i]);
    free(l3_miss_ptr[i]);
    free(dc_diff_ptr[i]);
    free(instr_count_ptr[i]);
  }
  shm_blkbuf_close(handle_s);
  shm_blkbuf_close(handle_r);
  printf("\nEnd of Program\n");
  return 0;
}

/****************************************************************************/
