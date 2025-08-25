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
#include <error.h>
#include <getopt.h>
#include <limits.h>
#include <motionentry.h>
#include <mqueue.h>
#include <pthread.h>
#include <semaphore.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/ipc.h>
#include <sys/mman.h>
#include <sys/shm.h>
#include <sys/sysinfo.h>
#include <sys/time.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

//#include <ittnotify.h>

// macro
#define AXIS_NUM (6)
#define CONVEYOR_RATIO (5)
#define SERVO_ENCODER_ACCURACY (0x100000)

// X1/X2/Y1/Y2 moving range [MIN, MAX]
#define X_MIN_POS_MM (30)
#define X_MAX_POS_MM (70)
#define Y_MIN_POS_MM (40)
#define Y_MAX_POS_MM (140)
static int32_t axis_pos_min[4] = { X_MIN_POS_MM, X_MIN_POS_MM, Y_MIN_POS_MM,
                                   Y_MIN_POS_MM };
static int32_t axis_pos_max[4] = { X_MAX_POS_MM, X_MAX_POS_MM, Y_MAX_POS_MM,
                                   Y_MAX_POS_MM };

#define X1_SERVO_POS (0)
#define X2_SERVO_POS (1)
#define Y1_SERVO_POS (2)
#define Y2_SERVO_POS (3)
#define Z1_SERVO_POS (4)
#define Z2_SERVO_POS (5)
static uint16_t servo_pos[AXIS_NUM] = { X1_SERVO_POS, X2_SERVO_POS,
                                        Y1_SERVO_POS, Y2_SERVO_POS,
                                        Z1_SERVO_POS, Z2_SERVO_POS };

#define LEFT_SWITCH_OFFSET (0x1)
#define HOME_SWITCH_OFFSET (0x4)
#define RIGHT_SWITCH_OFFSET (0x2)

#define NSEC_PER_SEC (1000000000L)
#define DIFF_NS(A, B)                                                          \
  (((B).tv_sec - (A).tv_sec) * NSEC_PER_SEC + ((B).tv_nsec) - (A).tv_nsec)
#define CYCLE_COUNTER_PERSEC(X) (NSEC_PER_SEC / 1000 / X)

// Ethercat servo related
typedef enum
{
  Fsm_Servo_Go_Home = 0,
  FSM_SERVO_MOVE_MIN,
  FSM_SERVO_MOVE_MAX,
} Servo_Status_t;
#define x1_servo_status Fsm_Servo_Go_Home
#define x2_servo_status Fsm_Servo_Go_Home
#define y1_servo_status Fsm_Servo_Go_Home
#define y2_servo_status Fsm_Servo_Go_Home
static Servo_Status_t servo_status[4] = { x1_servo_status, x2_servo_status,
                                          y1_servo_status, y2_servo_status };
#define digital_input_x1 (0)
#define digital_input_x2 (0)
#define digital_input_y1 (0)
#define digital_input_y2 (0)
static uint32_t digital_input[4] = { digital_input_x1, digital_input_x2,
                                     digital_input_y1, digital_input_y2 };
static EcrtServo* my_servo[AXIS_NUM];

/* Motion thread related */
static pthread_t cyclic_thread;
static int cpu_id       = 1;
static volatile int run = 1;

/* Time domain statistics */
struct Timestat
{
  int64_t latency_min_ns_ = 1000000;
  int64_t latency_max_ns_ = -1000000;
  int64_t latency_avg_ns_ = 0;
  uint64_t exec_min_ns_   = 1000000;
  uint64_t exec_max_ns_   = 0;
  uint64_t exec_avg_ns_   = 0;
  uint64_t cycle_count_   = 0;
  uint64_t cycle_poweron_ = 0;
  uint64_t spike_count_   = 0;
  uint64_t spike_max_     = 0;
  int64_t* exec_time_;
  int64_t* recv_time_;
  int64_t* calc_time_;
  int64_t* send_time_;
  uint64_t* l2_hit_;
  uint64_t* l2_miss_;
  uint64_t* l3_hit_;
  uint64_t* l3_miss_;
};

/* Ethercat master related */
static servo_master* master = nullptr;
static uint8_t* domain1;
void* domain;

/* Command line arguments */
static char* eni_file         = nullptr;
static bool verbose           = false;
static bool log_data          = false;
static bool output            = false;
static bool cache_stat_enable = false;
static unsigned int cycle_us  = 1000;
static unsigned int spike     = 250;
static uint64_t spike_ns      = spike * 1000;
static bool io_switch         = false;

/* Record and output to file */
static double running_time = 0;
static unsigned int running_time_t =
    (unsigned int)(CYCLE_COUNTER_PERSEC(cycle_us) * running_time);
static char* log_exec_file    = nullptr;
static char* log_recv_file    = nullptr;
static char* log_calc_file    = nullptr;
static char* log_send_file    = nullptr;
static char* log_l2_miss_file = nullptr;
static char* log_l3_miss_file = nullptr;

/* RTmotion variables */
using namespace RTmotion;
static AXIS_REF axis[AXIS_NUM];
static FbPower fb_power[AXIS_NUM];
static FbMoveAbsolute move_abso[4];
static FbMoveRelative move_rel_5;
static FbMoveRelative move_rel_6;
static FbReadActualPosition read_pos[AXIS_NUM];
static FbReadActualVelocity read_vel[AXIS_NUM];

/* Get the PMU counter value */
__attribute__((always_inline)) inline uint64_t __rdmpc(uint32_t counter)
{
  volatile uint32_t high, low;
  asm volatile("rdpmc\n\t" : "=a"(low), "=d"(high) : "c"(counter));
  return (((uint64_t)high << 32) | low);
}

/* Motion control thread function */
void* my_thread(void* arg)
{
  /* Timestamps used for cycle */
  struct timespec next_period, dc_period;

  /* Variables used for motion control */
  unsigned int iter             = 0;  // Used to control z1&z2 axis pos reverse
  uint32_t cur_digital_input[4] = { 0 };  // Used to get servo pos limit I/O
                                          // value
  float zero_pos[4] = { 0.0 };            // Used to recorde home pos value

  /* Variables used for time recording */
  struct Timestat* stat           = (struct Timestat*)arg;
  struct timespec start_time      = { 0, 0 };
  struct timespec last_start_time = { 0, 0 };
  struct timespec end_time        = { 0, 0 };
  struct timespec recv_start = { 0, 0 }, recv_end = { 0, 0 };
  struct timespec calc_start = { 0, 0 }, calc_end = { 0, 0 };
  struct timespec send_start = { 0, 0 }, send_end = { 0, 0 };
  int64_t latency_ns = 0;
  uint64_t exec_ns   = 0;

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

  /* Start motion cycles */
  if (cache_stat_enable)
  {
    cnt0_0 = cnt0_1 = __rdpmc(0);  // L2.HIT
    cnt1_0 = cnt1_1 = __rdpmc(1);  // L2.MISS
    cnt2_0 = cnt2_1 = __rdpmc(2);  // L3.HIT
    cnt3_0 = cnt3_1 = __rdpmc(3);  // L3.MISS
  }
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

    /* Benchmarking for jitter and motion execution latency */
    clock_gettime(CLOCK_MONOTONIC, &start_time);
    latency_ns      = DIFF_NS(next_period, start_time);
    exec_ns         = DIFF_NS(last_start_time, end_time);
    last_start_time = start_time;

    /* Record only if execution time is less than spike value */
    if (exec_ns < spike_ns)
    {
      stat->latency_avg_ns_ += fabs(latency_ns);
      if (latency_ns > stat->latency_max_ns_)
        stat->latency_max_ns_ = latency_ns;
      if (latency_ns < stat->latency_min_ns_)
        stat->latency_min_ns_ = latency_ns;

      /* Abandon the first time execution time which is zero */
      if (stat->cycle_count_ > 0)
      {
        stat->exec_avg_ns_ += fabs(exec_ns);
        if (exec_ns > stat->exec_max_ns_)
          stat->exec_max_ns_ = exec_ns;
        if (exec_ns < stat->exec_min_ns_)
          stat->exec_min_ns_ = exec_ns;
        // printf("stat->exec_avg_ns_:  %10ld, stat->cycle_count_: %10ld\n",
        // stat->exec_avg_ns_, stat->cycle_count_);

        /* Record execution time of specified cycles */
        if (running_time)
        {
          if (stat->cycle_count_ <= running_time_t)
          {
            stat->exec_time_[stat->cycle_count_ - 1] = exec_ns;
            stat->recv_time_[stat->cycle_count_ - 1] =
                DIFF_NS(recv_start, recv_end);
            stat->calc_time_[stat->cycle_count_ - 1] =
                DIFF_NS(calc_start, calc_end);
            stat->send_time_[stat->cycle_count_ - 1] =
                DIFF_NS(send_start, send_end);
            stat->l2_hit_[stat->cycle_count_ - 1]  = cnt0_1 - cnt0_0;
            stat->l2_miss_[stat->cycle_count_ - 1] = cnt1_1 - cnt1_0;
            stat->l3_hit_[stat->cycle_count_ - 1]  = cnt2_1 - cnt2_0;
            stat->l3_miss_[stat->cycle_count_ - 1] = cnt3_1 - cnt3_0;
            cnt0_0                                 = cnt0_1;
            cnt1_0                                 = cnt1_1;
            cnt2_0                                 = cnt2_1;
            cnt3_0                                 = cnt3_1;
          }
          else
            run = 0;
        }
      }
    }
    else  // Record abnormal spikes number and max value
    {
      stat->spike_count_++;
      if (exec_ns > stat->spike_max_)
        stat->spike_max_ = exec_ns;
    }

    //__itt_mark_pt_region_begin(region_total);

    /* Update ethercat data */
    recv_start = start_time;
    motion_servo_recv_process(master->master, static_cast<uint8_t*>(domain));
    for (size_t i = 0; i < 4; i++)
      cur_digital_input[i] = MOTION_DOMAIN_READ_U32(domain1 + digital_input[i]);
    clock_gettime(CLOCK_MONOTONIC, &recv_end);

    /* Run RTmotion update */
    calc_start = recv_end;
    for (size_t i = 0; i < AXIS_NUM; i++)
    {
      axis[i]->runCycle();
      fb_power[i].runCycle();
      read_pos[i].runCycle();
      read_vel[i].runCycle();
      if (i < 4)
        move_abso[i].runCycle();
    }
    move_rel_5.runCycle();
    move_rel_6.runCycle();

    /* Print axis pos and vel when verbose enabled */
    if (verbose)
    {
      for (size_t i = 0; i < AXIS_NUM; i++)
      {
        printf("Current position - %ld: %f,\tvelocity: %f\n", i,
               read_pos[i].getFloatValue(), read_vel[i].getFloatValue());
      }
    }

    /* Trigger axis movement when all axis are powered on */
    mcBOOL power_on = mcTRUE;
    for (auto& i : fb_power)
      power_on = (power_on == mcTRUE) && (i.getPowerStatus() == mcTRUE) ?
                     mcTRUE :
                     mcFALSE;

    if (power_on == mcTRUE)
    {
      for (auto& i : move_abso)
        i.setExecute(mcTRUE);
      move_rel_5.setExecute(mcTRUE);
      move_rel_6.setExecute(mcTRUE);

      if (!stat->cycle_poweron_)
        stat->cycle_poweron_ = stat->cycle_count_;
    }

    /* Control logic for X1,X2,Y1,Y2 */
    for (size_t i = 0; i < 4; i++)
    {
      if (servo_status[i] == Fsm_Servo_Go_Home)
      {
        if (io_switch)
        {
          if (cur_digital_input[i] & LEFT_SWITCH_OFFSET)
          {
            zero_pos[i] = read_pos[i].getFloatValue();
            move_abso[i].setExecute(mcFALSE);
            move_abso[i].setVelocity(20);
            move_abso[i].setPosition(zero_pos[i] + axis_pos_min[i]);
            servo_status[i] = FSM_SERVO_MOVE_MIN;
          }
        }
        else
        {
          zero_pos[i] = read_pos[i].getFloatValue();
          move_abso[i].setExecute(mcFALSE);
          move_abso[i].setVelocity(20);
          move_abso[i].setPosition(zero_pos[i] + axis_pos_min[i]);
          servo_status[i] = FSM_SERVO_MOVE_MIN;
        }
      }
      else if (servo_status[i] == FSM_SERVO_MOVE_MIN)
      {
        if (move_abso[i].isDone() == mcTRUE)
        {
          move_abso[i].setExecute(mcFALSE);
          move_abso[i].setPosition(zero_pos[i] + axis_pos_max[i]);
          servo_status[i] = FSM_SERVO_MOVE_MAX;
        }
      }
      else if (servo_status[i] == FSM_SERVO_MOVE_MAX)
      {
        if (move_abso[i].isDone() == mcTRUE)
        {
          move_abso[i].setExecute(mcFALSE);
          move_abso[i].setPosition(zero_pos[i] + axis_pos_min[i]);
          servo_status[i] = FSM_SERVO_MOVE_MIN;
        }
      }
    }

    /* control logic for Z1&Z2 */
    if (move_rel_5.isDone() == mcTRUE && move_rel_6.isDone() == mcTRUE)
    {
      iter++;
      if (iter > 500)
      {
        move_rel_5.setExecute(mcFALSE);
        move_rel_6.setExecute(mcFALSE);
        move_rel_5.setPosition(-move_rel_5.getPosition());
        move_rel_6.setPosition(-move_rel_6.getPosition());
        iter = 0;
      }
    }
    clock_gettime(CLOCK_MONOTONIC, &calc_end);

    //__itt_mark_pt_region_end(region_total);

    /* Send EtherCAT data */
    dc_period  = calc_end;
    send_start = calc_end;
    motion_servo_sync_dc(master->master,
                         TIMESPEC2NS(dc_period));  // Sync EtherCAT DC
    motion_servo_send_process(master->master, static_cast<uint8_t*>(domain));
    clock_gettime(CLOCK_MONOTONIC, &end_time);

    if (cache_stat_enable)
    {
      cnt0_1 = __rdpmc(0);
      cnt1_1 = __rdpmc(1);
      cnt2_1 = __rdpmc(2);
      cnt3_1 = __rdpmc(3);
    }

    send_end = end_time;
    stat->cycle_count_++;
  }
  return nullptr;
}

/* Logging thread funtion */
static void print_stat(struct Timestat* arg)
{
  struct Timestat* stat = arg;
  char* fmt_data;

  if (output)
  {
    fmt_data = (char*)"\r%10ld [%10.3f,%10.3f,%10.3f] [%10.3f,%10.3f,%10.3f] "
                      "[%10ld,%7.3f] %14ld";
    printf(fmt_data, stat->cycle_count_ / CYCLE_COUNTER_PERSEC(cycle_us),
           (float)stat->latency_min_ns_ / 1000.0,
           (float)stat->latency_avg_ns_ / stat->cycle_count_ / 1000.0,
           (float)stat->latency_max_ns_ / 1000.0,
           (float)stat->exec_min_ns_ / 1000.0,
           (float)stat->exec_avg_ns_ / stat->cycle_count_ / 1000.0,
           (float)stat->exec_max_ns_ / 1000.0, stat->spike_count_,
           (float)stat->spike_max_ / 1000.0, stat->cycle_poweron_);
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
    { "eni_file", required_argument, nullptr, 'n' },
    { "interval", required_argument, nullptr, 'i' },
    { "cpu_affinity", required_argument, nullptr, 'a' },
    { "cache_stat", required_argument, nullptr, 'c' },
    { "run_time", required_argument, nullptr, 't' },
    { "log_file", no_argument, nullptr, 'l' },
    { "verbose", no_argument, nullptr, 'v' },
    { "swtich", no_argument, nullptr, 's' },
    { "spike", required_argument, nullptr, 'p' },
    { "output", no_argument, nullptr, 'o' },
    { "help", no_argument, nullptr, 'h' },
    {}
  };
  do
  {
    index = getopt_long(argc, argv, "n:i:a:ct:lvsp:oh", long_options, nullptr);
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
      case 'c':
        cache_stat_enable = true;
        printf("Cache Statistic enabled.\n");
        break;
      case 't':
        running_time = atof(optarg);
        running_time_t =
            CYCLE_COUNTER_PERSEC(cycle_us) * (unsigned int)running_time;
        printf("Time: Set running time to %f (s)\n", running_time);
        printf("Time: Set running cycle number to %d\n", running_time_t);
        break;
      case 'l':
        log_data         = true;
        log_exec_file    = (char*)"exec_time.log";
        log_recv_file    = (char*)"recv_time.log";
        log_calc_file    = (char*)"calc_time.log";
        log_send_file    = (char*)"send_time.log";
        log_l2_miss_file = (char*)"l2_miss.log";
        log_l3_miss_file = (char*)"l3_miss.log";
        printf("Output execution time to log file: %s\n", log_exec_file);
        printf("Output message receive time to log file: %s\n", log_recv_file);
        printf("Output motion calculation time to log file: %s\n",
               log_calc_file);
        printf("Output message send time to log file: %s\n", log_send_file);
        printf("Output L2 Miss to log file: %s\n", log_l2_miss_file);
        printf("Output L3 Miss to log file: %s\n", log_l3_miss_file);
        break;
      case 'v':
        verbose = true;
        printf("verbose: print pos and vel values.\n");
        break;
      case 's':
        io_switch = true;
        printf("Switch: Enable I/O signal switch.\n");
        break;
      case 'p':
        spike    = (unsigned int)atof(optarg);
        spike_ns = (uint64_t)spike * 1000;
        printf("Spike: Set spike value to %d (us)\n", spike);
        break;
      case 'o':
        output = true;
        printf("Output: print time statistic in 10ms cycle.\n");
        break;
      case 'h':
        printf("Global options:\n");
        printf("    --eni       -n  Specify ENI/XML file.\n");
        printf("    --interval  -i  Specify RT cycle time(us).\n");
        printf("    --affinity  -a  Specify RT thread CPU affinity.\n");
        printf("    --time      -t  Specify running time(s).\n");
        printf("    --log       -l  Enable output to log file.\n");
        printf("    --verbose   -v  Be verbose.\n");
        printf("    --switch    -s  Enable I/O switch.\n");
        printf("    --spike     -p  Specify spike value(us).\n");
        printf("    --output    -o  Enable output in 10ms cycle.\n");
        printf("    --help      -h  Show this help.\n");
        exit(0);
        break;
    }
  } while (index != -1);
}

/* Main thread */
int main(int argc, char* argv[])
{
  struct timespec dc_period;
  auto signal_handler = [](int /*unused*/) { run = 0; };
  pthread_attr_t tattr;
  getOptions(argc, argv);
  struct Timestat* stat = new Timestat();
  // stat = (struct timestat *)malloc(sizeof(struct timestat));
  stat->exec_time_ = (int64_t*)malloc(sizeof(int64_t) * uint(running_time_t));
  memset(stat->exec_time_, 0, sizeof(int64_t) * uint(running_time_t));
  stat->recv_time_ = (int64_t*)malloc(sizeof(int64_t) * uint(running_time_t));
  memset(stat->recv_time_, 0, sizeof(int64_t) * uint(running_time_t));
  stat->calc_time_ = (int64_t*)malloc(sizeof(int64_t) * uint(running_time_t));
  memset(stat->calc_time_, 0, sizeof(int64_t) * uint(running_time_t));
  stat->send_time_ = (int64_t*)malloc(sizeof(int64_t) * uint(running_time_t));
  memset(stat->send_time_, 0, sizeof(int64_t) * uint(running_time_t));
  stat->l2_miss_ = (uint64_t*)malloc(sizeof(uint64_t) * uint(running_time_t));
  memset(stat->l2_miss_, 0, sizeof(uint64_t) * uint(running_time_t));
  stat->l3_miss_ = (uint64_t*)malloc(sizeof(uint64_t) * uint(running_time_t));
  memset(stat->l3_miss_, 0, sizeof(uint64_t) * uint(running_time_t));
  signal(SIGTERM, signal_handler);
  signal(SIGINT, signal_handler);

  mlockall(MCL_CURRENT | MCL_FUTURE);

  /* Create EtherCAT master by ENI*/
  if (!eni_file)
  {
    printf("Error: Unspecify ENI/XML file\n");
    exit(0);
  }
  master = motion_servo_master_create(eni_file);
  free(eni_file);
  eni_file = nullptr;
  if (master == nullptr)
    return -1;

  /* Motion domain_ create */
  if (motion_servo_domain_entry_register(master, &domain))
    return -1;

  if (!motion_servo_driver_register(master, domain))
    return -1;

  motion_servo_set_send_interval(master);

  motion_servo_register_dc(master);
  clock_gettime(CLOCK_MONOTONIC, &dc_period);
  motion_master_set_application_time(master, TIMESPEC2NS(dc_period));

  for (auto& i : my_servo)
  {
    i = new EcrtServo();
    i->setMaster(master);
  }

  if (motion_servo_master_activate(master->master))
  {
    printf("fail to activate master_\n");
    return -1;
  }

  domain1 = motion_servo_domain_data(domain);
  if (!domain1)
  {
    printf("fail to get domain_ data\n");
    return 0;
  }

  for (size_t i = 0; i < 4; i++)
  {
    digital_input[i] = motion_servo_get_domain_offset(
        master->master, 0, servo_pos[i], 0x60FD, 0x00);
    if (digital_input[i] == DOMAIN_INVAILD_OFFSET)
    {
      printf("fail to get digital input x1 offset\n");
      return 0;
    }
  }

  Servo* servo[AXIS_NUM];
  AxisConfig config[AXIS_NUM];
  for (size_t i = 0; i < AXIS_NUM; i++)
  {
    my_servo[i]->setDomain(domain1);
    my_servo[i]->initialize(0, servo_pos[i]);
    servo[i] = (Servo*)my_servo[i];

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
    read_pos[i].setAxis(axis[i]);
    read_pos[i].setEnable(mcTRUE);

    if (i < 4)
    {
      move_abso[i].setAxis(axis[i]);
      move_abso[i].setPosition(-150);
      move_abso[i].setVelocity(20);
      move_abso[i].setAcceleration(50);
      move_abso[i].setDeceleration(50);
      move_abso[i].setJerk(500);
      move_abso[i].setBufferMode(mcAborting);
      move_abso[i].setExecute(mcFALSE);
    }
  }

  move_rel_5.setAxis(axis[4]);
  move_rel_5.setPosition(-50);
  move_rel_5.setVelocity(100);
  move_rel_5.setAcceleration(50);
  move_rel_5.setDeceleration(50);
  move_rel_5.setJerk(500);
  move_rel_5.setBufferMode(mcAborting);
  move_rel_5.setExecute(mcFALSE);

  move_rel_6.setAxis(axis[5]);
  move_rel_6.setPosition(-50);
  move_rel_6.setVelocity(100);
  move_rel_6.setAcceleration(50);
  move_rel_6.setDeceleration(50);
  move_rel_6.setJerk(500);
  move_rel_6.setBufferMode(mcAborting);
  move_rel_6.setExecute(mcFALSE);

  /* Create cyclic RT-thread */
  setup_sched_parameters(&tattr, 99);
  if (pthread_create(&cyclic_thread, &tattr, my_thread, stat))
  {
    fprintf(stderr, "pthread_create cyclic task failed\n");
    pthread_attr_destroy(&tattr);
    return 1;
  }

  char* fmt_head;
  fmt_head = (char*)"    Dur(s) "
                    "           Sched_lat(us)          "
                    "           Exec_time(us)          "
                    "   Spike: num"
                    ",max(us)"
                    "  Power_on_cycle\n";
  printf("%s", fmt_head);
  while (run)
  {
    print_stat(stat);
    usleep(10000);
  }

  pthread_join(cyclic_thread, nullptr);
  motion_servo_master_release(master);

  /* Open file to write execution time record */
  if (log_data && running_time > 0)
  {
    FILE* fptr;
    // Write data execution time
    if ((fptr = fopen(log_exec_file, "wb")) == nullptr)
    {
      printf("Error! opening file: data.log");
      exit(1);
    }
    for (size_t i = 0; i < running_time_t; ++i)
      fprintf(fptr, "%ld\n", stat->exec_time_[i]);
    fclose(fptr);

    // Write data receiving time
    if ((fptr = fopen(log_recv_file, "wb")) == nullptr)
    {
      printf("Error! opening file: data.log");
      exit(1);
    }
    for (size_t i = 0; i < running_time_t; ++i)
      fprintf(fptr, "%ld\n", stat->recv_time_[i]);
    fclose(fptr);

    // Write motion calculation time
    if ((fptr = fopen(log_calc_file, "wb")) == nullptr)
    {
      printf("Error! opening file: data.log");
      exit(1);
    }
    for (size_t i = 0; i < running_time_t; ++i)
      fprintf(fptr, "%ld\n", stat->calc_time_[i]);
    fclose(fptr);

    // Write data sending time
    if ((fptr = fopen(log_send_file, "wb")) == nullptr)
    {
      printf("Error! opening file: data.log");
      exit(1);
    }
    for (size_t i = 0; i < running_time_t; ++i)
      fprintf(fptr, "%ld\n", stat->send_time_[i]);
    fclose(fptr);

    // Write L2 miss
    if ((fptr = fopen(log_l2_miss_file, "wb")) == nullptr)
    {
      printf("Error! opening file: data.log");
      exit(1);
    }
    for (size_t i = 0; i < running_time_t; ++i)
      fprintf(fptr, "%ld\n", stat->l2_miss_[i]);
    fclose(fptr);

    // Write L3 miss
    if ((fptr = fopen(log_l3_miss_file, "wb")) == nullptr)
    {
      printf("Error! opening file: data.log");
      exit(1);
    }
    for (size_t i = 0; i < running_time_t; ++i)
      fprintf(fptr, "%ld\n", stat->l3_miss_[i]);
    fclose(fptr);
  }

  /* Clean up */
  for (size_t i = 0; i < AXIS_NUM; i++)
  {
    delete my_servo[i];
    delete axis[i];
  }
  free(stat->exec_time_);
  free(stat->recv_time_);
  free(stat->calc_time_);
  free(stat->send_time_);
  free(stat->l2_miss_);
  free(stat->l3_miss_);
  delete stat;
  printf("\nEnd of Program\n");
  return 0;
}
