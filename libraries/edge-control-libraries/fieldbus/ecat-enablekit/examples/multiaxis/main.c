/******************************************************************************
 *
 *  $Id$
 *
 *  Copyright (C)      2011  IgH Andreas Stewering-Bone
 *                     2012  Florian Pose <fp@igh-essen.com>
 *
 *  This file is part of the IgH EtherCAT master
 *
 *  The IgH EtherCAT Master is free software; you can redistribute it and/or
 *  modify it under the terms of the GNU General Public License version 2, as
 *  published by the Free Software Foundation.
 *
 *  The IgH EtherCAT master is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
 *  Public License for more details.
 *
 *  You should have received a copy of the GNU General Public License along
 *  with the IgH EtherCAT master. If not, see <http://www.gnu.org/licenses/>.
 *
 *  ---
 *
 *  The license mentioned above concerns the source code only. Using the
 *  EtherCAT technology and brand is only permitted in compliance with the
 *  industrial property and similar rights of Beckhoff Automation GmbH.
 *
 *****************************************************************************/

#include <errno.h>
#include <mqueue.h>
#include <signal.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include <string.h>
#include <unistd.h>
#include <limits.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/shm.h>
#include <sys/ipc.h>
#include <sys/types.h>
#include <sys/time.h>
#include <time.h>
#include <math.h>
#include "main.h"
#include "circle.h"
#include <getopt.h>
#include <motionentry.h>

#ifdef SHARE_MEM
#define BUF_SIZE                0x1000
#define BUF_READ_SIZE           0x0C00
#define MOTOR_CTL_BUF_SIZE      0x0400
#define MOTOR_STATUS_ADDRESS    0x0400
#define MOTOR_CTL_ADDRESS       0x0C00
char mem_buffer[BUF_READ_SIZE];
char motor_ctl_buffer[MOTOR_CTL_BUF_SIZE];
void *shm_addr = NULL;
int shmid;
#endif

static char *eni_file;
static double set_tar_vel = 1.0;

//static unsigned int err_value = 0xffffffff; /* 1um = 50*20/0x100000 */

circle_prop prop;
static unsigned int measure_time = 0;
static pthread_t cyclic_thread;
static volatile int run = 1;
static volatile int close_signal = 0;
static bool motor_run = true;

static servo_master* master = NULL;
void* domain;
static uint8_t* domain_pd;
static uint32_t domain_size;
static Slave_Data *ec_slave[NUM_AXIS];
int slave_pos[NUM_AXIS];

ec_domain_state_t domain_state;

#if (NUM_AXIS == 6) || (NUM_AXIS == 8)
static unsigned char motor34_vel = 5;
static unsigned char motor56_vel = 15;
static unsigned char motor78_vel = 2;
#endif

void motion_servo_data_offset(servo_master* master)
{
    if(master == NULL)
        return;
    
    Slave_Data *slave = NULL;    
    for(int i = 0; i < NUM_AXIS; i++)
    {
        slave = ec_slave[i];
        slave->ctrl_word = motion_servo_get_domain_offset(master->master, 0, slave_pos[i], 0x6040, 0x00);
        if (slave->ctrl_word == DOMAIN_INVAILD_OFFSET)
        {
            return;
        }
        slave->tar_pos = motion_servo_get_domain_offset(master->master, 0, slave_pos[i], 0x607a, 0x00);
        if (slave->tar_pos == DOMAIN_INVAILD_OFFSET)
        {
            return;
        }
        slave->mode_sel = motion_servo_get_domain_offset(master->master, 0, slave_pos[i], 0x6060, 0x00);
        if (slave->mode_sel == DOMAIN_INVAILD_OFFSET)
        {
            return;
        }
        slave->touch_probe_func = motion_servo_get_domain_offset(master->master, 0, slave_pos[i], 0x60b8, 0x00);
        if (slave->touch_probe_func == DOMAIN_INVAILD_OFFSET)
        {
            return;
        }
        slave->mode_cw = motion_servo_get_domain_offset(master->master, 0, slave_pos[i], 0x2002, 0x03);
        if (slave->mode_cw == DOMAIN_INVAILD_OFFSET)
        {
            return;
        }
        slave->error_code = motion_servo_get_domain_offset(master->master, 0, slave_pos[i], 0x603f, 0x00);
        if (slave->error_code == DOMAIN_INVAILD_OFFSET)
        {
            return;
        }
        slave->status_word = motion_servo_get_domain_offset(master->master, 0, slave_pos[i], 0x6041, 0x00);
        if (slave->status_word == DOMAIN_INVAILD_OFFSET)
        {
            return;
        }
        slave->pos_act = motion_servo_get_domain_offset(master->master, 0, slave_pos[i], 0x6064, 0x00);
        if (slave->pos_act == DOMAIN_INVAILD_OFFSET)
        {
            return;
        }
        slave->mode_display = motion_servo_get_domain_offset(master->master, 0, slave_pos[i], 0x6061, 0x00);
        if (slave->mode_display == DOMAIN_INVAILD_OFFSET)
        {
            return;
        }
        slave->touch_probe_status = motion_servo_get_domain_offset(master->master, 0, slave_pos[i], 0x60b9, 0x00);
        if (slave->touch_probe_status == DOMAIN_INVAILD_OFFSET)
        {
            return;
        }
        slave->touch_probe1_pos = motion_servo_get_domain_offset(master->master, 0, slave_pos[i], 0x60ba, 0x00);
        if (slave->touch_probe1_pos == DOMAIN_INVAILD_OFFSET)
        {
            return;
        }
        slave->touch_probe2_pos = motion_servo_get_domain_offset(master->master, 0, slave_pos[i], 0x60bc, 0x00);
        if (slave->touch_probe2_pos == DOMAIN_INVAILD_OFFSET)
        {
            return;
        }
        slave->digital_input = motion_servo_get_domain_offset(master->master, 0, slave_pos[i], 0x60fd, 0x00);
        if (slave->digital_input == DOMAIN_INVAILD_OFFSET)
        {
            return;
        }
        slave->vel_act = motion_servo_get_domain_offset(master->master, 0, slave_pos[i], 0x606c, 0x00);
        if (slave->vel_act == DOMAIN_INVAILD_OFFSET)
        {
            return;
        }
        slave->err_pos = motion_servo_get_domain_offset(master->master, 0, slave_pos[i], 0x60f4, 0x00);
        if (slave->err_pos == DOMAIN_INVAILD_OFFSET)
        {
            return;
        }
    }

}


#ifdef SHARE_MEM
static void write_buf_int16(char* dest,int16_t src)
{
    dest[1] = (char)(src>>8);
    dest[0] = (char)(src);
}

static void write_buf_int32(char* dest,int32_t src)
{
    dest[3] = (char)(src>>8);
    dest[2] = (char)(src);
    dest[1] = (char)(src>>24);
    dest[0] = (char)(src>>16);

}

static void write_buf_int64(char* dest,int64_t src)
{
    dest[7] = (char)(src>>8);
    dest[6] = (char)(src);
    dest[5] = (char)(src>>24);
    dest[4] = (char)(src>>16);
    dest[3] = (char)(src>>40);
    dest[2] = (char)(src>>32);
    dest[1] = (char)(src>>56);
    dest[0] = (char)(src>>48);
}

static void write_sharemem_ctl_data(char* dest,unsigned short int offset,Ctl_Data *data)
{
    write_buf_int16(dest+MOTOR_STATUS_ADDRESS+offset+0x00,data->statusword);
    write_buf_int32(dest+MOTOR_STATUS_ADDRESS+offset+0x02,data->actualpos);
    write_buf_int16(dest+MOTOR_STATUS_ADDRESS+offset+0x06,data->cwmode);
    write_buf_int16(dest+MOTOR_STATUS_ADDRESS+offset+0x08,data->controlword);
    write_buf_int32(dest+MOTOR_STATUS_ADDRESS+offset+0x0a,data->targetpos);
    write_buf_int16(dest+MOTOR_STATUS_ADDRESS+offset+0x0e,data->selmode);
    write_buf_int32(dest+MOTOR_STATUS_ADDRESS+offset+0x10,data->actualvel);
    write_buf_int32(dest+MOTOR_STATUS_ADDRESS+offset+0x14,data->zeroposition);
    write_buf_int32(dest+MOTOR_STATUS_ADDRESS+offset+0x18,data->minposition);
    write_buf_int32(dest+MOTOR_STATUS_ADDRESS+offset+0x1c,data->maxposition);
}
#endif

static void data_init(void)
{

    for(int i = 0; i < NUM_AXIS; i++)
    {
        ec_slave[i] = (Slave_Data *)calloc(1, sizeof(Slave_Data));
        ec_slave[i]->sc = NULL;
    }

    for(int i = 0; i < NUM_AXIS; i++)
    {
        slave_pos[i] = i;
    }

}

static void axis_circle_init(void){
    /* mm */
    prop.servo_pos1.x = 0.0;
    prop.servo_pos1.y = 300.0;
    prop.servo_pos2.x = 300.0;
    prop.servo_pos2.y = 300.0;
    prop.servo_len1 = 300.0;
    prop.servo_len2 = 280.0;
    prop.circle_radius = 150;
    circle_init(&prop);
}

#ifdef SHARE_MEM
static char sharemem_init(void)
{
    shmid = shmget((key_t)87654321, BUF_SIZE, IPC_CREAT|0666);
    printf("shmid : %u\n", shmid);
    if (shmid == -1){
        perror("shmget error!");
        return -1;
    }
    shm_addr = shmat(shmid, NULL, 0);
    if (shm_addr == (void *) -1){
        perror("shmat error!");
        return -1;
    }
    return 0;
}
#endif

/*****************************************************************************
 * Realtime task
 ****************************************************************************/
#if defined(MOTOR_8AXIS) || defined(MOTOR_2AXIS)
static double calc_len(unsigned long pos, unsigned long prevpos)
{
    long inter = pos - prevpos;
    return (double)(inter*SERVO_AXIS_SIZE/MAX_DECODER_COUNT);
}

static signed long calc_targetoffset(double target, double current)
{
    return (signed long)(((target-current)/SERVO_AXIS_SIZE)*MAX_DECODER_COUNT);
}
#endif

static void ec_readmotordata(Ctl_Data* ec_motor,Slave_Data* ec_slave)
{
    ec_motor->statusword     = MOTION_DOMAIN_READ_U16(domain_pd + ec_slave->status_word);
    ec_motor->actualpos      = MOTION_DOMAIN_READ_S32(domain_pd + ec_slave->pos_act);
    ec_motor->cwmode         = MOTION_DOMAIN_READ_U16(domain_pd + ec_slave->mode_cw);
    ec_motor->selmode        = MOTION_DOMAIN_READ_S8(domain_pd + ec_slave->mode_sel);
    ec_motor->actualvel      = MOTION_DOMAIN_READ_S32(domain_pd + ec_slave->vel_act);
    ec_motor->leftinput      = (MOTION_DOMAIN_READ_U32(domain_pd + ec_slave->digital_input))&0x1;
    ec_motor->homeinput      = (MOTION_DOMAIN_READ_U32(domain_pd + ec_slave->digital_input))&0x2;
    ec_motor->rightinput     = (MOTION_DOMAIN_READ_U32(domain_pd + ec_slave->digital_input))&0x4;
    ec_motor->errpos         = MOTION_DOMAIN_READ_U32(domain_pd + ec_slave->err_pos);
    if(ec_motor->actualvel > MAX_VELOCITY_MOTOR/2)
        ec_motor->actualvel = ec_motor->actualvel - MAX_VELOCITY_MOTOR;
    if ((ec_motor->statusword & 0x4f) == 0x40)
        ec_motor->controlword = 0x6;
    else if ((ec_motor->statusword & 0x6f) == 0x21)
        ec_motor->controlword = 0x7;
    else if ((ec_motor->statusword & 0x27f)==0x233){
        ec_motor->prevpos = ec_motor->actualpos;
        ec_motor->controlword = 0xf;
    }
    else if ((ec_motor->statusword & 0x27f)==0x237)
        ec_motor->controlword = 0x1f;
    else
        ec_motor->controlword = 0x80;
}

static void ec_writemotordata(Ctl_Data* ec_motor,Slave_Data* ec_slave)
{
    MOTION_DOMAIN_WRITE_S32(domain_pd+ec_slave->tar_pos, ec_motor->targetpos );
    MOTION_DOMAIN_WRITE_U16(domain_pd+ec_slave->ctrl_word, ec_motor->controlword );
    MOTION_DOMAIN_WRITE_U8(domain_pd+ec_slave->mode_sel, 8);
    ec_motor->prevpos = ec_motor->actualpos;
}

#if defined(MOTOR_8AXIS) || defined(MOTOR_6AXIS)
#define Pi  3.141592654
static long getCosPos(unsigned int *time, int min,int max,int index)
{
    long pos = 0;
    int A = min - max;
    float TA = motor34_vel*1000000.0/CYCLE_US;
    float TB = motor56_vel*1000000.0/CYCLE_US;

    if(time == NULL)
        return 0;
    if(index == 2) {
        if(*time == 0)
            return 0;
        pos = -A*(cos(2.0*Pi*(*time)/TA) - cos(2.0*Pi*(*time-1)/TA));
        if(*time >= TA)
            *time = 0;
        return pos;
    }
    else if(index == 3){
        if(*time == 0)
            return 0;
        pos = -A*(cos(2.0*Pi*(*time)/TB) - cos(2.0*Pi*(*time-1)/TB));
        if(*time >= TB)
            *time = 0;
        return pos;
    }
    return 0;
}

#define A   0xa00000
static long getSinPos(unsigned int time)
{
    long pos = 0;
    float T = motor78_vel*1000000.0/CYCLE_US;

    if(time == 0)
        return 0;
    else{
        pos = A*(sin(2.0*Pi*time/T) - sin(2.0*Pi*(time-1)/T));
        return pos;
    }
}
#endif

void *my_thread(void *arg)
{
    struct timespec next_period;
    unsigned int cycle_counter = 0;
    Ctl_Data ec_motor[NUM_AXIS];
    
    struct timespec dc_period;
#if defined(MOTOR_8AXIS) || defined(MOTOR_2AXIS)
    int circle_x=0;
    int circle_y=0;
    double cur_slave0_len = prop.servo_len1;
    double cur_slave1_len = prop.servo_len2;
    unsigned char circle0_run = MOTOR_START;
#endif
#if defined(MOTOR_8AXIS) || defined(MOTOR_6AXIS)
    unsigned int motor23_timecounter = 0;
    unsigned int motor45_timecounter = 0;
    unsigned char circle1_run = MOTOR_START;
    unsigned char circle2_run = MOTOR_START;
    unsigned char circle3_run = MOTOR_START;
#endif
    if(motor_run == false){
#if defined(MOTOR_8AXIS) || defined(MOTOR_2AXIS)
        circle0_run = MOTOR_STOP;
#endif
#if defined(MOTOR_8AXIS) || defined(MOTOR_6AXIS)
        circle3_run = MOTOR_STOP;
#endif
    }

#ifdef MEASURE_TIMING
    unsigned int cycle_counter_max_cycle = 0;
    unsigned int cycle_counter_max_jitter = 0;
    unsigned int last_cycle_counter = 0;
    uint8_t servo_run = 0;

    struct timespec startTime = {0, 0};
    struct timespec endTime = {0, 0};
    struct timespec lastStartTime ={0, 0};
    struct timespec rece_startTime = {0, 0};
    struct timespec pro_endTime = {0, 0};
    struct timespec send_startTime = {0, 0};
    struct timespec send_endTime = {0, 0};

    int64_t period_ns = 0, exec_ns = 0, receive_ns = 0, process_ns, send_ns,
            period_min_ns = 1000000, period_max_ns = 0,
            exec_min_ns = 1000000, exec_max_ns = 0;
    int64_t latency_ns = 0;
    int64_t latency_min_ns = 1000000, latency_max_ns = -1000000;
    int64_t total_exec_ns=0;
    int64_t total_cycle_ns=0;
    static int64_t max_cycle_persec=0, max_jitter_persec=0;
    int64_t avg_cycle_time = 0;
    int64_t min_cycle_time = 1000000;
    int64_t max_cycle_time = -1000000;
    int64_t min_jitter_time = 1000000;
    int64_t max_jitter_time = -1000000;
#endif

    struct sched_param param = {.sched_priority = 99};
    pthread_setschedparam(pthread_self(), SCHED_FIFO, &param);

    for(int i = 0; i < NUM_AXIS; i++)
    {
        memset(&ec_motor[i],0,sizeof(Ctl_Data));
    }

    clock_gettime(CLOCK_MONOTONIC, &next_period);
#ifdef MEASURE_TIMING
    lastStartTime = next_period;
    endTime = next_period;
#endif

    while ((run != 0 )||(close_signal != 0)) {
        next_period.tv_nsec += CYCLE_US * 1000;
        while (next_period.tv_nsec >= NSEC_PER_SEC) {
            next_period.tv_nsec -= NSEC_PER_SEC;
            next_period.tv_sec++;
        }

        clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &next_period, NULL);
#ifdef MEASURE_TIMING
        clock_gettime(CLOCK_MONOTONIC, &startTime);
        latency_ns = DIFF_NS(next_period, startTime);
        period_ns = DIFF_NS(lastStartTime, startTime);
        exec_ns = DIFF_NS(lastStartTime, endTime);
        process_ns = DIFF_NS(rece_startTime, pro_endTime);
        send_ns = DIFF_NS(send_startTime, send_endTime);
        lastStartTime = startTime;

        if (latency_ns > latency_max_ns) 
            latency_max_ns = latency_ns;
        if (latency_ns < latency_min_ns)
            latency_min_ns = latency_ns;
        if (period_ns > period_max_ns)
            period_max_ns = period_ns;
        if (period_ns < period_min_ns)
            period_min_ns = period_ns;
        if (exec_ns > exec_max_ns)
            exec_max_ns = exec_ns;
        if (exec_ns < exec_min_ns)
            exec_min_ns = exec_ns;
        total_exec_ns += exec_ns;
#endif
        cycle_counter++;
        if(close_signal > 0)
            close_signal--;
#ifdef MEASURE_TIMING
        clock_gettime(CLOCK_MONOTONIC, &rece_startTime);
#endif
        motion_servo_recv_process(master->master, domain);

#ifdef MEASURE_TIMING
        clock_gettime(CLOCK_MONOTONIC, &pro_endTime);
#endif
        if ((!(cycle_counter % CYCLE_COUNTER_PERSEC))&&(close_signal==0)) {

#ifdef MEASURE_TIMING
            if(min_cycle_time > exec_min_ns)
                min_cycle_time = exec_min_ns;
            if(max_cycle_time < exec_max_ns){
                cycle_counter_max_cycle = cycle_counter;
                max_cycle_time = exec_max_ns;
            }
            if(min_jitter_time > latency_min_ns)
                min_jitter_time = latency_min_ns;
            if(max_jitter_time < latency_max_ns){
                cycle_counter_max_jitter = cycle_counter;
                max_jitter_time = latency_max_ns;
            }
            last_cycle_counter = cycle_counter;
            max_cycle_persec = exec_max_ns;
            max_jitter_persec = latency_max_ns;
            period_max_ns = -1000000;
            period_min_ns = 1000000;
            exec_max_ns = -1000000;
            exec_min_ns = 1000000;
            latency_max_ns = -1000000;
            latency_min_ns = 1000000;
            total_cycle_ns += total_exec_ns;
            total_exec_ns = 0;
            if(servo_run == 0){
                cycle_counter = 0;
                total_cycle_ns = 0;
                min_jitter_time = 1000000;
                max_jitter_time = -1000000;
                min_cycle_time = 1000000;
                max_cycle_time = -1000000;
                servo_run = 1;
            }
#endif
        }

        for(int i = 0; i < NUM_AXIS; i++)
        {
            ec_readmotordata(&ec_motor[i],ec_slave[i]);
        }

#if defined(MOTOR_8AXIS) || defined(MOTOR_2AXIS)
        if ((ec_motor[0].controlword==0x1f)&&(ec_motor[1].controlword==0x1f)){
            double diff0, diff1;
            double axis0_len, axis1_len;
            if (circle0_run == MOTOR_START){
                circle0_run = MOTOR_RUN;
                ec_motor[0].targetpos = ec_motor[0].actualpos;
                ec_motor[1].targetpos = ec_motor[1].actualpos;
                ec_motor[0].prevpos = ec_motor[0].actualpos;
                ec_motor[1].prevpos = ec_motor[1].actualpos;
                ec_writemotordata(&ec_motor[0],ec_slave[0]);
                ec_writemotordata(&ec_motor[1],ec_slave[1]);
            }
            else if(circle0_run == MOTOR_RUN){
                diff0 = calc_len(ec_motor[0].actualpos, ec_motor[0].prevpos);
                cur_slave0_len += diff0;
                diff1 = calc_len(ec_motor[1].actualpos, ec_motor[1].prevpos);
                cur_slave1_len += diff1;
                circle_CurPosAdjust(&prop, cur_slave0_len, cur_slave1_len, &circle_x, &circle_y);
                circle_TargetByStep(&prop, 0.00005, &axis0_len, &axis1_len);
                ec_motor[0].targetpos = ec_motor[0].actualpos + calc_targetoffset(axis0_len, cur_slave0_len);
                ec_motor[1].targetpos = ec_motor[1].actualpos + calc_targetoffset(axis1_len, cur_slave1_len);
                ec_writemotordata(&ec_motor[0],ec_slave[0]);
                ec_writemotordata(&ec_motor[1],ec_slave[1]);
            }
        }
        else if(circle0_run == MOTOR_START){
            MOTION_DOMAIN_WRITE_U16(domain_pd+ec_slave[0]->ctrl_word, ec_motor[0].controlword);
            MOTION_DOMAIN_WRITE_U8(domain_pd+ec_slave[0]->mode_sel, 5 );
            MOTION_DOMAIN_WRITE_U16(domain_pd+ec_slave[1]->ctrl_word, ec_motor[1].controlword);
            MOTION_DOMAIN_WRITE_U8(domain_pd+ec_slave[1]->mode_sel, 5 );
        } else if(circle0_run == MOTOR_RUN)
            circle0_run = MOTOR_START;
#endif

#if defined(MOTOR_8AXIS) || defined(MOTOR_6AXIS)
        if ((ec_motor[0+AXIS_OFFSET].controlword==0x1f)&&(ec_motor[1+AXIS_OFFSET].controlword==0x1f)){
            long pos = 0;
            if (circle1_run == MOTOR_START){
                circle1_run = MOTOR_RUN;
                ec_motor[0+AXIS_OFFSET].targetpos = ec_motor[0+AXIS_OFFSET].actualpos;
                ec_motor[1+AXIS_OFFSET].targetpos = ec_motor[1+AXIS_OFFSET].actualpos;
                ec_motor[0+AXIS_OFFSET].prevpos = ec_motor[0+AXIS_OFFSET].actualpos;
                ec_motor[1+AXIS_OFFSET].prevpos = ec_motor[1+AXIS_OFFSET].actualpos;
                ec_motor[0+AXIS_OFFSET].cwmode = 0;
                ec_motor[1+AXIS_OFFSET].cwmode = 1;
                ec_writemotordata(&ec_motor[0+AXIS_OFFSET],ec_slave[0+AXIS_OFFSET]);
                ec_writemotordata(&ec_motor[1+AXIS_OFFSET],ec_slave[1+AXIS_OFFSET]);
            }
            else if(circle1_run == MOTOR_RUN){
                if((ec_motor[0+AXIS_OFFSET].gohome_history == GO_HOME_FINISH)&&(ec_motor[1+AXIS_OFFSET].gohome_history == GO_HOME_FINISH)){
                    pos = getCosPos(&motor23_timecounter,ec_motor[0+AXIS_OFFSET].minposition,ec_motor[0+AXIS_OFFSET].maxposition,2);
                    ec_motor[0+AXIS_OFFSET].targetpos = ec_motor[0+AXIS_OFFSET].targetpos - pos;
                    pos = getCosPos(&motor23_timecounter,ec_motor[1+AXIS_OFFSET].minposition,ec_motor[1+AXIS_OFFSET].maxposition,2);
                    ec_motor[1+AXIS_OFFSET].targetpos = ec_motor[1+AXIS_OFFSET].targetpos - pos;
                    motor23_timecounter++;
                    ec_writemotordata(&ec_motor[0+AXIS_OFFSET],ec_slave[0+AXIS_OFFSET]);
                    ec_writemotordata(&ec_motor[1+AXIS_OFFSET],ec_slave[1+AXIS_OFFSET]);
                }
                else{
                    if((ec_motor[0+AXIS_OFFSET].leftinput)&&(ec_motor[0+AXIS_OFFSET].gohome_history == GO_HOME)){
                        ec_motor[0+AXIS_OFFSET].zeroposition = ec_motor[0+AXIS_OFFSET].actualpos;
                        ec_motor[0+AXIS_OFFSET].minposition = ec_motor[0+AXIS_OFFSET].actualpos + 0x300000;
                        ec_motor[0+AXIS_OFFSET].maxposition = ec_motor[0+AXIS_OFFSET].actualpos + 0x700000;
                        ec_motor[1+AXIS_OFFSET].zeroposition = ec_motor[1+AXIS_OFFSET].actualpos;
                        ec_motor[1+AXIS_OFFSET].minposition = ec_motor[1+AXIS_OFFSET].actualpos - 0x300000;
                        ec_motor[1+AXIS_OFFSET].maxposition = ec_motor[1+AXIS_OFFSET].actualpos - 0x700000;
                        ec_motor[0+AXIS_OFFSET].gohome_history = GO_MINIMUM;
                        ec_writemotordata(&ec_motor[0+AXIS_OFFSET],ec_slave[0+AXIS_OFFSET]);
                        ec_writemotordata(&ec_motor[1+AXIS_OFFSET],ec_slave[1+AXIS_OFFSET]);
                    }
                    else if(ec_motor[0+AXIS_OFFSET].gohome_history == GO_MINIMUM){
                        if(((long)ec_motor[0+AXIS_OFFSET].targetpos - ec_motor[0+AXIS_OFFSET].minposition) <= 0){
                            ec_motor[0+AXIS_OFFSET].targetpos = ec_motor[0+AXIS_OFFSET].targetpos + 200;
                            ec_motor[1+AXIS_OFFSET].targetpos = ec_motor[1+AXIS_OFFSET].targetpos - 200;
                            ec_writemotordata(&ec_motor[0+AXIS_OFFSET],ec_slave[0+AXIS_OFFSET]);
                            ec_writemotordata(&ec_motor[1+AXIS_OFFSET],ec_slave[1+AXIS_OFFSET]);
                        }
                        else{
                            ec_motor[0+AXIS_OFFSET].gohome_history = GO_HOME_FINISH;
                            ec_motor[1+AXIS_OFFSET].gohome_history = GO_HOME_FINISH;
                            if(motor_run == false)
                                circle1_run = MOTOR_STOP;
                        }
                    }
                    else if(ec_motor[0+AXIS_OFFSET].gohome_history == GO_HOME){
                        ec_motor[0+AXIS_OFFSET].targetpos = ec_motor[0+AXIS_OFFSET].targetpos - 200;
                        ec_motor[1+AXIS_OFFSET].targetpos = ec_motor[1+AXIS_OFFSET].targetpos + 200;
                        ec_writemotordata(&ec_motor[0+AXIS_OFFSET],ec_slave[0+AXIS_OFFSET]);
                        ec_writemotordata(&ec_motor[1+AXIS_OFFSET],ec_slave[1+AXIS_OFFSET]);
                    }
                }
            }
        }
        else if(circle1_run == MOTOR_START){
            MOTION_DOMAIN_WRITE_U16(domain_pd+ec_slave[0+AXIS_OFFSET]->ctrl_word, ec_motor[0+AXIS_OFFSET].controlword );
            MOTION_DOMAIN_WRITE_U8(domain_pd+ec_slave[0+AXIS_OFFSET]->mode_sel, 5);
            MOTION_DOMAIN_WRITE_U16(domain_pd+ec_slave[1+AXIS_OFFSET]->ctrl_word, ec_motor[1+AXIS_OFFSET].controlword );
            MOTION_DOMAIN_WRITE_U8(domain_pd+ec_slave[1+AXIS_OFFSET]->mode_sel, 5);
        } else if(circle1_run == MOTOR_RUN)
            circle1_run = MOTOR_START;
        if ((ec_motor[2+AXIS_OFFSET].controlword==0x1f)&&(ec_motor[3+AXIS_OFFSET].controlword==0x1f)) {
            long pos = 0;
            if (circle2_run == MOTOR_START){
                circle2_run = MOTOR_RUN;
                ec_motor[2+AXIS_OFFSET].targetpos = ec_motor[2+AXIS_OFFSET].actualpos;
                ec_motor[3+AXIS_OFFSET].targetpos = ec_motor[3+AXIS_OFFSET].actualpos;
                ec_motor[2+AXIS_OFFSET].prevpos = ec_motor[2+AXIS_OFFSET].actualpos;
                ec_motor[3+AXIS_OFFSET].prevpos = ec_motor[3+AXIS_OFFSET].actualpos;
                ec_writemotordata(&ec_motor[2+AXIS_OFFSET],ec_slave[2+AXIS_OFFSET]);
                ec_writemotordata(&ec_motor[3+AXIS_OFFSET],ec_slave[3+AXIS_OFFSET]);
            }
            else if(circle2_run == MOTOR_RUN){
                if((ec_motor[2+AXIS_OFFSET].gohome_history == GO_HOME_FINISH)&&(ec_motor[3+AXIS_OFFSET].gohome_history == GO_HOME_FINISH)){
                    pos = getCosPos(&motor45_timecounter,ec_motor[2+AXIS_OFFSET].minposition,ec_motor[2+AXIS_OFFSET].maxposition,3);
                    ec_motor[2+AXIS_OFFSET].targetpos = ec_motor[2+AXIS_OFFSET].targetpos - pos;
                    pos = getCosPos(&motor45_timecounter,ec_motor[3+AXIS_OFFSET].minposition,ec_motor[3+AXIS_OFFSET].maxposition,3);
                    ec_motor[3+AXIS_OFFSET].targetpos = ec_motor[3+AXIS_OFFSET].targetpos - pos;
                    motor45_timecounter++;
                    ec_writemotordata(&ec_motor[2+AXIS_OFFSET],ec_slave[2+AXIS_OFFSET]);
                    ec_writemotordata(&ec_motor[2+AXIS_OFFSET],ec_slave[3+AXIS_OFFSET]);
                }
                else{
                    if((ec_motor[3+AXIS_OFFSET].leftinput)&&(ec_motor[3+AXIS_OFFSET].gohome_history == GO_HOME)){
                        ec_motor[2+AXIS_OFFSET].zeroposition = ec_motor[2+AXIS_OFFSET].actualpos;
                        ec_motor[2+AXIS_OFFSET].minposition = ec_motor[2+AXIS_OFFSET].actualpos + 0x400000;
                        ec_motor[2+AXIS_OFFSET].maxposition = ec_motor[2+AXIS_OFFSET].actualpos + 0x1400000;
                        ec_motor[3+AXIS_OFFSET].zeroposition = ec_motor[3+AXIS_OFFSET].actualpos;
                        ec_motor[3+AXIS_OFFSET].minposition = ec_motor[3+AXIS_OFFSET].actualpos + 0x400000;
                        ec_motor[3+AXIS_OFFSET].maxposition = ec_motor[3+AXIS_OFFSET].actualpos + 0x1400000;
                        ec_motor[3+AXIS_OFFSET].gohome_history = GO_MINIMUM;
                        ec_writemotordata(&ec_motor[2+AXIS_OFFSET],ec_slave[2+AXIS_OFFSET]);
                        ec_writemotordata(&ec_motor[3+AXIS_OFFSET],ec_slave[3+AXIS_OFFSET]);
                    }
                    else if(ec_motor[3+AXIS_OFFSET].gohome_history == GO_MINIMUM){
                        if(((long)ec_motor[3+AXIS_OFFSET].targetpos - ec_motor[3+AXIS_OFFSET].minposition) <= 0){
                            ec_motor[2+AXIS_OFFSET].targetpos = ec_motor[2+AXIS_OFFSET].targetpos + 200;
                            ec_motor[3+AXIS_OFFSET].targetpos = ec_motor[3+AXIS_OFFSET].targetpos + 200;
                            ec_writemotordata(&ec_motor[2+AXIS_OFFSET],ec_slave[2+AXIS_OFFSET]);
                            ec_writemotordata(&ec_motor[3+AXIS_OFFSET],ec_slave[3+AXIS_OFFSET]);
                        }
                        else{
                            ec_motor[2+AXIS_OFFSET].gohome_history = GO_HOME_FINISH;
                            ec_motor[3+AXIS_OFFSET].gohome_history = GO_HOME_FINISH;
                            if(motor_run == false)
                                circle2_run = MOTOR_STOP;
                        }
                    }
                    else if(ec_motor[3+AXIS_OFFSET].gohome_history == GO_HOME){
                        ec_motor[2+AXIS_OFFSET].targetpos = ec_motor[2+AXIS_OFFSET].targetpos - 200;
                        ec_motor[3+AXIS_OFFSET].targetpos = ec_motor[3+AXIS_OFFSET].targetpos - 200;
                        ec_writemotordata(&ec_motor[2+AXIS_OFFSET],ec_slave[2+AXIS_OFFSET]);
                        ec_writemotordata(&ec_motor[3+AXIS_OFFSET],ec_slave[3+AXIS_OFFSET]);
                    }
                }
            }
        }
        else if(circle2_run == MOTOR_START){
            MOTION_DOMAIN_WRITE_U16(domain_pd+ec_slave[2+AXIS_OFFSET]->ctrl_word, ec_motor[2+AXIS_OFFSET].controlword );
            MOTION_DOMAIN_WRITE_U8(domain_pd+ec_slave[2+AXIS_OFFSET]->mode_sel, 5);
            MOTION_DOMAIN_WRITE_U16(domain_pd+ec_slave[3+AXIS_OFFSET]->ctrl_word, ec_motor[3+AXIS_OFFSET].controlword );
            MOTION_DOMAIN_WRITE_U8(domain_pd+ec_slave[3+AXIS_OFFSET]->mode_sel, 5);
        } else if(circle2_run == MOTOR_RUN)
            circle2_run = MOTOR_START;
        if ((ec_motor[4+AXIS_OFFSET].controlword==0x1f)&&(ec_motor[5+AXIS_OFFSET].controlword==0x1f)) {

            long pos = 0;
            static unsigned int sin_time = 0;

            if (circle3_run == MOTOR_START){
                circle3_run = MOTOR_RUN;
                ec_motor[4+AXIS_OFFSET].targetpos = ec_motor[4+AXIS_OFFSET].actualpos;
                ec_motor[5+AXIS_OFFSET].targetpos = ec_motor[5+AXIS_OFFSET].actualpos;
                ec_motor[4+AXIS_OFFSET].prevpos = ec_motor[4+AXIS_OFFSET].actualpos;
                ec_motor[5+AXIS_OFFSET].prevpos = ec_motor[5+AXIS_OFFSET].actualpos;
                ec_writemotordata(&ec_motor[4+AXIS_OFFSET],ec_slave[4+AXIS_OFFSET]);
                ec_writemotordata(&ec_motor[5+AXIS_OFFSET],ec_slave[5+AXIS_OFFSET]);
            }
            else if(circle3_run == MOTOR_RUN){
                if(close_signal){
                    ec_motor[4+AXIS_OFFSET].targetpos = ec_motor[4+AXIS_OFFSET].targetpos + 1000*close_signal*CYCLE_US/1000000;
                    ec_motor[5+AXIS_OFFSET].targetpos = ec_motor[5+AXIS_OFFSET].targetpos - 1000*close_signal*CYCLE_US/1000000;
                }
                else{
                    pos = getSinPos(sin_time++);
                    ec_motor[4+AXIS_OFFSET].targetpos = ec_motor[4+AXIS_OFFSET].targetpos + pos;
                    ec_motor[5+AXIS_OFFSET].targetpos = ec_motor[5+AXIS_OFFSET].targetpos - pos;
                }
                ec_writemotordata(&ec_motor[4+AXIS_OFFSET],ec_slave[4+AXIS_OFFSET]);
                ec_writemotordata(&ec_motor[5+AXIS_OFFSET],ec_slave[5+AXIS_OFFSET]);
            }
        }
        else if(circle3_run == MOTOR_START){
            MOTION_DOMAIN_WRITE_U16(domain_pd+ec_slave[4+AXIS_OFFSET]->ctrl_word, ec_motor[4+AXIS_OFFSET].controlword );
            MOTION_DOMAIN_WRITE_U8(domain_pd+ec_slave[4+AXIS_OFFSET]->mode_sel, 5);
            MOTION_DOMAIN_WRITE_U16(domain_pd+ec_slave[5+AXIS_OFFSET]->ctrl_word, ec_motor[5+AXIS_OFFSET].controlword );
            MOTION_DOMAIN_WRITE_U8(domain_pd+ec_slave[5+AXIS_OFFSET]->mode_sel, 5);
        } else if(circle3_run == MOTOR_RUN)
            circle3_run = MOTOR_START;
#endif
        clock_gettime(CLOCK_MONOTONIC, &dc_period);
        motion_servo_sync_dc(master->master, TIMESPEC2NS(dc_period));
#ifdef MEASURE_TIMING
        clock_gettime(CLOCK_MONOTONIC, &send_startTime);
#endif
        motion_servo_send_process(master->master, domain);
#ifdef MEASURE_TIMING
        clock_gettime(CLOCK_MONOTONIC, &send_endTime);
#endif

#ifdef MEASURE_TIMING
        clock_gettime(CLOCK_MONOTONIC, &endTime);
#endif
#ifdef SHARE_MEM
        if(cycle_counter > 1){
            memset(mem_buffer,0,BUF_READ_SIZE);
#ifdef MEASURE_TIMING
            write_buf_int64(mem_buffer,period_ns);
            write_buf_int64(mem_buffer+8,max_cycle_persec);
            write_buf_int64(mem_buffer+16,max_jitter_persec);
            write_buf_int32(mem_buffer+24,cycle_counter);

#if defined(MOTOR_8AXIS) || defined(MOTOR_2AXIS)
            write_buf_int32(mem_buffer+28,circle_x);
            write_buf_int32(mem_buffer+32,circle_y);
#endif

            write_buf_int64(mem_buffer+36,min_cycle_time);
            write_buf_int64(mem_buffer+44,max_cycle_time);
            write_buf_int64(mem_buffer+52,min_jitter_time);
            write_buf_int64(mem_buffer+60,max_jitter_time);
            write_buf_int32(mem_buffer+68,cycle_counter_max_cycle);
            write_buf_int32(mem_buffer+72,cycle_counter_max_jitter);
            write_buf_int64(mem_buffer+76,receive_ns);
            write_buf_int64(mem_buffer+84,process_ns);
            write_buf_int64(mem_buffer+92,send_ns);
#endif
            //unsigned short int offset = {0x00, 0x40, 0x80, 0xC0, 0x100, 0x140, 0x180, 0x1C0};
            for(int i = 0; i < NUM_AXIS; i++)
            {
                write_sharemem_ctl_data(mem_buffer,i * 0x40,&ec_motor[i]);
            }

            memcpy(motor_ctl_buffer, (pthread_mutex_t *)(shm_addr+MOTOR_CTL_ADDRESS), MOTOR_CTL_BUF_SIZE);
            memset((pthread_mutex_t *)(shm_addr+MOTOR_CTL_ADDRESS), 0xff,MOTOR_CTL_BUF_SIZE);
            memcpy((pthread_mutex_t *)shm_addr, mem_buffer, BUF_READ_SIZE);
        }
        else
            memset((pthread_mutex_t *)shm_addr, 0, BUF_SIZE);
#ifdef MOTOR_CONTROL
        if(cycle_counter > 1000){
            /* motor start/stop */
#if defined(MOTOR_8AXIS) || defined(MOTOR_2AXIS)
            if(motor_ctl_buffer[0x01] == MOTOR_RUN)
                circle0_run = MOTOR_START;
            else if(motor_ctl_buffer[0x01] == MOTOR_STOP)
                circle0_run = MOTOR_STOP;
#endif
#if defined(MOTOR_8AXIS) || defined(MOTOR_6AXIS)
            if((ec_motor[0].gohome_history == GO_HOME_FINISH)&&(ec_motor[1].gohome_history == GO_HOME_FINISH))
            {
                if(motor_ctl_buffer[0x41] == MOTOR_RUN)
                    circle1_run = MOTOR_RUN;
                else if(motor_ctl_buffer[0x41] == MOTOR_STOP)
                    circle1_run = MOTOR_STOP;
            }
            if((ec_motor[2].gohome_history == GO_HOME_FINISH)&&(ec_motor[3].gohome_history == GO_HOME_FINISH))
            {
                if(motor_ctl_buffer[0x81] == MOTOR_RUN)
                    circle2_run = MOTOR_RUN;
                else if(motor_ctl_buffer[0x81] == MOTOR_STOP)
                    circle2_run = MOTOR_STOP;
            }
            if(motor_ctl_buffer[0xC1] == MOTOR_RUN)
                circle3_run = MOTOR_START;
            else if(motor_ctl_buffer[0xC1] == MOTOR_STOP)
                circle3_run = MOTOR_STOP;
#endif

#endif
        }
#endif

#ifdef MEASURE_TIMING
        if(measure_time != 0)
            if(cycle_counter >= measure_time)
                run = 0;
#endif
    }
#ifdef MEASURE_TIMING
    if(last_cycle_counter)
        avg_cycle_time = total_cycle_ns/last_cycle_counter;
    printf("*********************************************\n");
    printf("average cycle time  %10.3f\n", (float)avg_cycle_time/1000);
    printf("cycle counter       %10d\n", last_cycle_counter);
    printf("cycle time          %10.3f ... %10.3f\n", (float)min_cycle_time/1000, (float)max_cycle_time/1000);
    printf("jitter time         %10.3f ... %10.3f\n", (float)min_jitter_time/1000, (float)max_jitter_time/1000);
    printf("*********************************************\n");
#endif
    return NULL;
}

/****************************************************************************
 * Signal handler
 ***************************************************************************/
void signal_handler(int sig)
{
    run = 0;
    close_signal = 1000000/CYCLE_US; /* 1s */
}

static void getOptions(int argc, char**argv)
{
    int index;
    static struct option longOptions[] = {
        //name          has_arg                flag     val
        {"velocity",    required_argument,     NULL,    'v'},
        {"eni",         required_argument,     NULL,    'n'},
        {"help",        no_argument,           NULL,    'h'},
        {}
    };
    do {
        index = getopt_long(argc, argv, "v:n:h", longOptions, NULL);
        switch(index){
            case 'v':
                set_tar_vel = atof(optarg);
                if (set_tar_vel > 50.0) {
                    set_tar_vel = 50.0;
                }
                printf("Velocity: %f circle per second \n", set_tar_vel);
                break;
            case 'n':
                if (eni_file) {
                    free(eni_file);
                    eni_file = NULL;
                }
                eni_file = malloc(strlen(optarg)+1);
                if (eni_file) {
                    memset(eni_file, 0, strlen(optarg)+1);
                    memmove(eni_file, optarg, strlen(optarg)+1);
                    printf("Using %s\n", eni_file);
                }
                break;
            case 'h':
                printf("Global options:\n");
                printf("    --velocity  -v  Set target velocity(circle/s). Max:50.0 \n");
                printf("    --eni       -n  Specify ENI/XML file\n");
                printf("    --help      -h  Show this help.\n");
                if (eni_file) {
                    free(eni_file);
                    eni_file = NULL;
                }
                exit(0);
                break;
        }
    } while(index != -1);
}


/****************************************************************************
 * Main function
 ***************************************************************************/
int main(int argc, char *argv[])
{

    struct timespec dc_period;
    
    getOptions(argc,argv);
    data_init();
    axis_circle_init();
    signal(SIGTERM, signal_handler);
    signal(SIGINT, signal_handler);
    mlockall(MCL_CURRENT | MCL_FUTURE);

    /* Create master by ENI*/
    if (!eni_file) {
        printf("Error: Unspecify ENI/XML file\n");
        exit(0);
    }
    master = motion_servo_master_create(eni_file);
    free(eni_file);
    eni_file = NULL;
    if (master == NULL) {
        return -1;
    }

    /* Motion domain create */
    if (motion_servo_domain_entry_register(master, &domain)) {
        goto End;
    }

    if (!motion_servo_driver_register(master, domain)) {
        goto End;
    }

    motion_servo_set_send_interval(master);
    
    /*Configuring DC signal*/
    motion_servo_register_dc(master);

    /* Set the initial master time and select a slave to use as the DC
     * reference clock, otherwise pass NULL to auto select the first capable
     * slave. Note: This can be used whether the master or the ref slave will
     * be used as the systems master DC clock
    */
    clock_gettime(CLOCK_MONOTONIC, &dc_period);

    /* Attention: The initial application time is also used for phase
     * calcuation for the SYNC0/1 interrupts. Please be sure to call it at
     * the correct phase to the realtime cycle
    */
    motion_master_set_application_time(master, TIMESPEC2NS(dc_period));

    for(int i = 0; i < NUM_AXIS; i++)
    {
        motion_servo_slave_config_sdo8(master, 0, slave_pos[i], 0x6060, 0x00, MODE_CSP);
        motion_servo_slave_config_sdo16(master, 0, slave_pos[i], 0x2002, 0x03, 1);
    }

    if (motion_servo_master_activate(master->master)) {
        printf("fail to activate master\n");
        goto End;
    }

    domain_pd = motion_servo_domain_data(domain);
    if (!domain_pd) {
        printf("fail to get domain data\n");
        goto End;
    }

    domain_size = motion_servo_domain_size(domain);
    /* get the offset value of each item in slave data*/
    motion_servo_data_offset(master);

#ifdef SHARE_MEM
    if(sharemem_init() == -1)
        return -1;
#endif

    /* Create cyclic RT-thread */
    pthread_attr_t thattr;
    pthread_attr_init(&thattr);
    pthread_attr_setdetachstate(&thattr, PTHREAD_CREATE_JOINABLE);
    if (pthread_create(&cyclic_thread, &thattr, &my_thread, NULL)) {
        fprintf(stderr, "pthread_create cyclic task failed\n");
        pthread_attr_destroy(&thattr);
        goto End;
    }
    while (run || close_signal != 0)
        sched_yield();

    pthread_join(cyclic_thread, NULL);

    for(int i = 0; i < NUM_AXIS; i++)
    {
        motion_servo_slave_config_sdo16(master, 0, slave_pos[i], 0x6040, 0x00, 0x100);
    }

#ifdef SHARE_MEM
    if (shmdt(shm_addr) == -1){
        printf("shmdt error!\n");
        exit(1);
    }
#endif

    pthread_attr_destroy(&thattr);

    motion_servo_master_release(master);
    return 0;
End:
    motion_servo_master_release(master);
    return -1;
}

/****************************************************************************/
